"""
Resume Pipeline API Views.

Dashboard endpoints:
    GET  /api/applications/                   → ApplicationListCreateView (list)
    POST /api/applications/                   → ApplicationListCreateView (create)
    GET  /api/jobs/                           → JobListCreateView (list)
    POST /api/jobs/                           → JobListCreateView (create)
    GET  /api/candidates/                     → CandidateListCreateView (list)
    POST /api/candidates/                     → CandidateListCreateView (create)

Per-application endpoints:
    POST /api/applications/<uuid:pk>/run/     → RunPipelineView
    GET  /api/applications/<uuid:pk>/score/   → ApplicationScoreView
    POST /api/applications/<uuid:pk>/reviews/ → HumanReviewCreateView

Authentication note:
    These endpoints assume authentication is handled by Django REST Framework's
    configured DEFAULT_AUTHENTICATION_CLASSES. For the initial API milestone,
    basic token auth is sufficient. JWT can be wired in later.
"""

from __future__ import annotations

import datetime
import os
import tempfile

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db import IntegrityError

from resume_pipeline.ingestion.job_parser import JobParseError, parse_job_markdown
from resume_pipeline.ingestion.parser import ResumeParser
from resume_pipeline.ingestion.word_converter import (
    WordConversionError,
    convert_word_to_pdf,
    is_word_document,
)
from resume_pipeline.pipeline.rubric_score import LLMBackendNotConfiguredError
from resume_pipeline.models import Application, Candidate, FinalScore, HumanReview, Job, RubricScore
from resume_pipeline.pipeline.job_embedder import embed_job_sections
from resume_pipeline.serializers import (
    ApplicationCreateSerializer,
    ApplicationListSerializer,
    ApplicationScoreSerializer,
    CandidateCreateSerializer,
    CandidateDetailSerializer,
    CandidateListSerializer,
    HumanReviewSerializer,
    JobDetailSerializer,
    JobListSerializer,
    JobMarkdownInputSerializer,
)
from resume_pipeline.logging_module import audit_logger
from resume_pipeline.observability import pipeline_observability
from resume_pipeline.services import PipelineService, ReviewService


# ---------------------------------------------------------------------------
# Jobs — list + create (structured JSON, not Markdown)
# ---------------------------------------------------------------------------

class JobListCreateView(APIView):
    """
    GET  /api/jobs/  → list of all jobs (all fields)
    POST /api/jobs/

    Accepts a title and description raw Markdown job specification and creates a Job record:
      1. Validates that raw_markdown is non-empty (400 on blank).
      2. Parses the Markdown with parse_job_markdown() (422 on JobParseError).
      3. Creates the Job row (409 on duplicate title).
      4. Calls embed_job_sections() — TimeoutError is swallowed so that
         embedding latency never fails the HTTP response.

    Request body (application/json):
        { "description": "# Job Title\\n\\n## Description\\n..." }

    Response 201 (application/json):
        { "id": "<uuid>", "title": "...", "created_at": "..." }
    """

    def get(self, request: Request) -> Response:
        with pipeline_observability.timed("job_list_query"):
            jobs = Job.objects.order_by("-created_at")
        return Response(JobListSerializer(jobs, many=True).data)

    def post(self, request: Request) -> Response:
        raw_markdown = request.data.get("raw_markdown", "")
        audit_logger.log_job_create_started(markdown_length=len(raw_markdown))

        serializer = JobMarkdownInputSerializer(data=request.data)
        if not serializer.is_valid():
            audit_logger.log_job_create_failed(
                "validation_error",
                detail=str(serializer.errors),
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        with pipeline_observability.timed("job_markdown_parse"):
            try:
                job_spec = parse_job_markdown(serializer.validated_data["raw_markdown"])
            except JobParseError as exc:
                audit_logger.log_job_create_failed(
                    "parse_error",
                    field_key=exc.field_key,
                    detail=exc.detail,
                )
                return Response(
                    {exc.field_key: [exc.detail]},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

        with pipeline_observability.timed("job_db_create"):
            try:
                job = Job.objects.create(**job_spec.to_model_kwargs())
            except IntegrityError:
                audit_logger.log_job_create_failed(
                    "duplicate_title",
                    field_key="title",
                    detail=job_spec.title,
                )
                return Response(
                    {"detail": "A job with this title already exists."},
                    status=status.HTTP_409_CONFLICT,
                )

        audit_logger.log_job_created(job_id=str(job.id), title=job.title)

        with pipeline_observability.timed("job_embed"):
            try:
                embed_job_sections(job)
            except Exception:
                # Embedding failure must never block the HTTP response.
                pass

        return Response(JobDetailSerializer(job).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

class CandidateListCreateView(APIView):
    """
    GET  /api/candidates/  → list of all candidates (id, name, email, created_at)
    POST /api/candidates/  → create a candidate from a resume upload

    POST body (multipart/form-data):
        name        string
        email       string
        resume_pdf  file   (PDF, .doc, or .docx — max 10 MB)

    Word uploads (.doc / .docx) are converted to PDF server-side via
    LibreOffice headless (resume_pipeline.ingestion.word_converter) before
    being handed to ResumeParser — the parsing stage is unchanged and stays
    PDF-only. A conversion failure (corrupt file, timeout) surfaces as a 400
    with a field-level error on resume_pdf, same shape as any other
    validation error.
    """

    parser_classes = [JSONParser, MultiPartParser]

    def get(self, request: Request) -> Response:
        with pipeline_observability.timed("candidate_list_query"):
            candidates = Candidate.objects.order_by("-created_at")
        return Response(CandidateListSerializer(candidates, many=True).data)

    def post(self, request: Request) -> Response:
        name = request.data.get("name", "")
        audit_logger.log_candidate_create_started(name=name)

        serializer = CandidateCreateSerializer(data=request.data)
        if not serializer.is_valid():
            audit_logger.log_candidate_create_failed(
                "validation_error",
                detail=str(serializer.errors),
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data
        upload = validated["resume_pdf"]
        pdf_bytes = upload.read()

        if is_word_document(upload):
            with pipeline_observability.timed("candidate_word_to_pdf_conversion"):
                try:
                    pdf_bytes = convert_word_to_pdf(pdf_bytes, upload.name)
                except WordConversionError as exc:
                    audit_logger.log_candidate_create_failed(
                        "word_conversion_failed",
                        field_key="resume_pdf",
                        detail=str(exc),
                    )
                    return Response(
                        {"resume_pdf": [str(exc)]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        with pipeline_observability.timed("candidate_pdf_parse"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            try:
                doc = ResumeParser().parse(tmp_path)
            finally:
                os.unlink(tmp_path)

        with pipeline_observability.timed("candidate_db_create"):
            try:
                candidate = Candidate.objects.create(
                    name=validated["name"],
                    email=validated["email"],
                    resume_raw=doc.raw_text,
                    resume_parsed=doc.sections,
                )
            except IntegrityError:
                audit_logger.log_candidate_create_failed(
                    "duplicate_email",
                    field_key="email",
                    detail=validated["email"],
                )
                return Response(
                    {"detail": "A candidate with this email address already exists."},
                    status=status.HTTP_409_CONFLICT,
                )

        audit_logger.log_candidate_created(
            candidate_id=str(candidate.id),
            name=candidate.name,
        )
        return Response(CandidateListSerializer(candidate).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Applications — list + create
# ---------------------------------------------------------------------------

class ApplicationListCreateView(APIView):
    """
    GET  /api/applications/  → table rows with candidate, job, status, score
    POST /api/applications/  → associate an existing Job with an existing Candidate

    POST body (application/json):
        { "job_id": "<uuid>", "candidate_id": "<uuid>" }

    Returns HTTP 200 when the pair already exists (idempotent get_or_create).
    Returns HTTP 201 on first creation.
    """

    def get(self, request: Request) -> Response:
        with pipeline_observability.timed("application_list_query"):
            apps = (
                Application.objects
                .select_related("candidate", "job", "final_score", "rubric_score")
                .order_by("-created_at")
            )
        return Response(ApplicationListSerializer(apps, many=True).data)

    def post(self, request: Request) -> Response:
        job_id       = str(request.data.get("job_id", ""))
        candidate_id = str(request.data.get("candidate_id", ""))
        audit_logger.log_application_create_started(
            job_id=job_id, candidate_id=candidate_id
        )

        serializer = ApplicationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            audit_logger.log_application_create_failed(
                "validation_error",
                detail=str(serializer.errors),
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        with pipeline_observability.timed("application_get_or_create"):
            app, created = serializer.create(serializer.validated_data)

        if created:
            audit_logger.log_application_created(
                application_id=str(app.id),
                job_id=str(app.job_id),
                candidate_id=str(app.candidate_id),
            )
        else:
            audit_logger.log_application_already_exists(
                application_id=str(app.id),
                job_id=str(app.job_id),
                candidate_id=str(app.candidate_id),
            )

        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(ApplicationListSerializer(app).data, status=http_status)


# ---------------------------------------------------------------------------
# Jobs — detail (GET / DELETE)
# ---------------------------------------------------------------------------

class JobDetailView(APIView):
    """
    GET    /api/jobs/<uuid:pk>/   → full job record (title, description, must_haves)
    DELETE /api/jobs/<uuid:pk>/   → hard-delete; cascades to Applications via FK
    """

    def get(self, request: Request, pk: str) -> Response:
        job = get_object_or_404(Job, pk=pk)
        return Response(JobDetailSerializer(job).data)

    def delete(self, request: Request, pk: str) -> Response:
        job = get_object_or_404(Job, pk=pk)
        job.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Candidates — detail (GET / DELETE)
# ---------------------------------------------------------------------------

class CandidateDetailView(APIView):
    """
    GET    /api/candidates/<uuid:pk>/   → full candidate record (with resume_parsed)
    DELETE /api/candidates/<uuid:pk>/   → hard-delete; cascades to Applications via FK
    """

    def get(self, request: Request, pk: str) -> Response:
        candidate = get_object_or_404(Candidate, pk=pk)
        return Response(CandidateDetailSerializer(candidate).data)

    def delete(self, request: Request, pk: str) -> Response:
        candidate = get_object_or_404(Candidate, pk=pk)
        candidate.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Applications — detail (DELETE only)
# ---------------------------------------------------------------------------

class ApplicationDetailView(APIView):
    """
    DELETE /api/applications/<uuid:pk>/

    Removes the Application and all related pipeline stage records (cascade).
    The associated Job and Candidate records are NOT deleted.
    """

    def delete(self, request: Request, pk: str) -> Response:
        application = get_object_or_404(Application, pk=pk)
        application.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Pipeline trigger
# ---------------------------------------------------------------------------

class RunPipelineView(APIView):
    """
    POST /api/applications/<uuid:pk>/run/

    Runs the 4-stage evaluation pipeline synchronously for the given application
    and returns the result. Existing stage results are overwritten on each call.
    """

    _service = PipelineService()

    def post(self, request: Request, pk: str) -> Response:
        application = get_object_or_404(
            Application.objects.select_related("candidate", "job"), pk=pk
        )
        try:
            with pipeline_observability.timed("pipeline_run", application_id=str(application.id)):
                result = self._service.run(application)
        except LLMBackendNotConfiguredError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "code": "llm_not_configured",
                    "hint": "Set LLM_BACKEND=openai or LLM_BACKEND=anthropic with the corresponding API key.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(result, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Score card
# ---------------------------------------------------------------------------

class ApplicationScoreView(APIView):
    """
    GET /api/applications/<uuid:pk>/score/

    Returns the full AI score card for a reviewer to inspect before deciding.
    Only available for applications that have a FinalScore record (i.e. scored).
    """

    def get(self, request: Request, pk: str) -> Response:
        application = get_object_or_404(Application, pk=pk)
        final_score = get_object_or_404(FinalScore, application=application)
        serializer = ApplicationScoreSerializer(final_score)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Human review creation
# ---------------------------------------------------------------------------

class HumanReviewCreateView(APIView):
    """
    POST /api/applications/<uuid:pk>/reviews/

    Creates a HumanReview record, transitions Application.status, and logs
    override events to the audit trail.

    Request body:
        {
            "reviewer_email": "alice@company.com",
            "decision": "override_pass",
            "override_reason": "Strong portfolio"   # required for override_* decisions
        }
    """

    _service = ReviewService()

    def post(self, request: Request, pk: str) -> Response:
        application = get_object_or_404(Application, pk=pk)

        serializer = HumanReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data

        try:
            final_score_obj = application.final_score
            ai_score = final_score_obj.score
            confidence = final_score_obj.confidence
        except FinalScore.DoesNotExist:
            ai_score = 0.0
            confidence = None

        review = HumanReview.objects.create(
            application=application,
            reviewer_email=validated["reviewer_email"],
            decision=validated["decision"],
            override_reason=validated.get("override_reason", ""),
            ai_score_at_review=ai_score,
            confidence_at_review=confidence,
        )

        self._service.process_review(application, review)

        return Response(
            {
                "id": str(review.id),
                "reviewer_email": review.reviewer_email,
                "decision": review.decision,
                "override_reason": review.override_reason,
                "ai_score_at_review": review.ai_score_at_review,
                "reviewed_at": review.reviewed_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

class DashboardStatsView(APIView):
    """
    GET /api/dashboard/stats/

    Single aggregation endpoint that powers the Dashboard telemetry section.
    Returns totals, status distribution, job-execution funnel (last 24 h),
    and a 7-day LLM resilience time series.

    All queries are read-only and touch only indexed columns, so they are
    safe to call on every Dashboard mount without caching.
    """

    # Status label map — defines canonical display order for the donut chart.
    _STATUS_LABELS: dict[str, str] = {
        "pending":      "Pending",
        "gate_failed":  "Gate Failed",
        "gate_unknown": "Gate Unknown",
        "gate_passed":  "Gate Passed",
        "scored":       "Scored",
        "under_review": "Under Review",
        "approved":     "Approved",
        "rejected":     "Rejected",
    }

    def get(self, request: Request) -> Response:
        _t0 = timezone.now()
        with pipeline_observability.timed("dashboard_stats_total"):
            now = _t0
            cutoff_7d  = now - datetime.timedelta(days=7)
            cutoff_24h = now - datetime.timedelta(hours=24)

            # ── Totals ────────────────────────────────────────────────────────
            with pipeline_observability.timed("dashboard_stats_totals"):
                total_applications = Application.objects.count()
                total_candidates   = Candidate.objects.count()
                total_jobs         = Job.objects.count()

                active_jobs = Application.objects.filter(
                    status__in=["pending", "gate_passed", "gate_unknown"]
                ).count()

                total_scored = RubricScore.objects.count()
                if total_scored:
                    primary_count    = RubricScore.objects.filter(is_evaluated_via_fallback=False).count()
                    llm_success_rate = round(primary_count / total_scored * 100, 1)
                else:
                    llm_success_rate = 100.0

            # ── Application status distribution ───────────────────────────────
            with pipeline_observability.timed("dashboard_stats_status_distribution"):
                status_counts = {
                    row["status"]: row["count"]
                    for row in Application.objects.values("status").annotate(count=Count("id"))
                }
                status_distribution = [
                    {"status": s, "label": label, "count": status_counts.get(s, 0)}
                    for s, label in self._STATUS_LABELS.items()
                ]

            # ── Job execution funnel — last 24 h ──────────────────────────────
            with pipeline_observability.timed("dashboard_stats_job_funnel"):
                recent_qs = Application.objects.filter(updated_at__gte=cutoff_24h)

                job_execution_funnel = [
                    {
                        "status": "completed",
                        "label": "Completed",
                        "count": recent_qs.filter(
                            status__in=["scored", "approved", "rejected", "under_review"]
                        ).count(),
                    },
                    {
                        "status": "running",
                        "label": "Running",
                        "count": recent_qs.filter(
                            status__in=["pending", "gate_passed", "gate_unknown"]
                        ).count(),
                    },
                    {
                        "status": "failed",
                        "label": "Failed",
                        "count": recent_qs.filter(status="gate_failed").count(),
                    },
                    {
                        "status": "fallback",
                        "label": "Retrying via Fallback",
                        "count": recent_qs.filter(
                            rubric_score__is_evaluated_via_fallback=True
                        ).count(),
                    },
                ]

            # ── LLM resilience — last 7 days ──────────────────────────────────
            with pipeline_observability.timed("dashboard_stats_llm_resilience"):
                dates = [
                    (now - datetime.timedelta(days=i)).date()
                    for i in range(6, -1, -1)
                ]

                daily_qs = (
                    RubricScore.objects
                    .filter(application__updated_at__gte=cutoff_7d)
                    .annotate(date=TruncDate("application__updated_at"))
                    .values("date", "is_evaluated_via_fallback")
                    .annotate(count=Count("id"))
                )

                daily_map: dict[str, dict[str, int]] = {}
                for row in daily_qs:
                    key = str(row["date"])
                    if key not in daily_map:
                        daily_map[key] = {"primary": 0, "fallback": 0}
                    if row["is_evaluated_via_fallback"]:
                        daily_map[key]["fallback"] = row["count"]
                    else:
                        daily_map[key]["primary"] = row["count"]

                llm_resilience = [
                    {
                        "date":     str(d),
                        "primary":  daily_map.get(str(d), {}).get("primary", 0),
                        "fallback": daily_map.get(str(d), {}).get("fallback", 0),
                    }
                    for d in dates
                ]

        total_latency_ms = (timezone.now() - _t0).total_seconds() * 1000
        audit_logger.log_dashboard_stats_fetched(
            applications=total_applications,
            candidates=total_candidates,
            jobs=total_jobs,
            active_jobs=active_jobs,
            llm_success_rate=llm_success_rate,
            latency_ms=total_latency_ms,
        )

        return Response(
            {
                "totals": {
                    "applications":     total_applications,
                    "candidates":       total_candidates,
                    "jobs":             total_jobs,
                    "active_jobs":      active_jobs,
                    "llm_success_rate": llm_success_rate,
                },
                "application_status_distribution": status_distribution,
                "job_execution_funnel":            job_execution_funnel,
                "llm_resilience": {
                    "time_series": llm_resilience,
                },
            }
        )
