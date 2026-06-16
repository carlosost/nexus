"""
DRF Serializers for the Resume Pipeline API.

Serializer responsibilities:
  Dashboard / list views (read-only):
    - ApplicationListSerializer  — table row: candidate, job, status, score
    - JobListSerializer          — dropdown option: id + title
    - CandidateListSerializer    — dropdown option: id + name + email

  Creation forms (write):
    - ApplicationCreateSerializer — links an existing Job to an existing Candidate
    - CandidateCreateSerializer   — creates a Candidate from name + email + PDF upload

  Review workflow:
    - HumanReviewSerializer      — validates override decision + reason
    - ApplicationScoreSerializer — read-only score card for the reviewer UI
    - RubricBreakdownSerializer  — per-competency scores nested in score card

Override reason enforcement rule (encoded as a serializer-level validator):
  Decision in {override_pass, override_fail} → override_reason must be
  non-empty and non-whitespace. This is checked BEFORE the view touches
  the DB — a 400 is returned immediately on failure.
"""

from __future__ import annotations

from rest_framework import serializers

from resume_pipeline.models import Application, Candidate, FinalScore, HumanReview, Job, RubricScore


# ---------------------------------------------------------------------------
# Job — list + create
# ---------------------------------------------------------------------------

class JobListSerializer(serializers.ModelSerializer):
    """Lightweight read-only projection for dropdown and table use."""

    class Meta:
        model = Job
        fields = "__all__"


class JobDetailSerializer(serializers.ModelSerializer):
    """
    Full projection returned by GET /api/jobs/<id>/.
    Also accepts PATCH payloads — all fields are optional on update.
    """

    class Meta:
        model = Job
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class JobMarkdownInputSerializer(serializers.Serializer):
    """
    Accepts a raw Markdown string for the POST /api/jobs/ endpoint.
    Validation is limited to presence/non-blank; structural parsing is handled
    by parse_job_markdown() in the view so field-level errors can be returned.
    """
    raw_markdown = serializers.CharField(
        min_length=1,
        error_messages={"min_length": "raw_markdown must not be blank."},
    )


# ---------------------------------------------------------------------------
# Candidate — list + create
# ---------------------------------------------------------------------------

class CandidateListSerializer(serializers.ModelSerializer):
    """Lightweight read-only projection for dropdown and table use."""

    class Meta:
        model = Candidate
        fields = ["id", "name", "email", "created_at"]


class CandidateDetailSerializer(serializers.ModelSerializer):
    """
    Full projection returned by GET /api/candidates/<id>/.
    PATCH accepts name and email only — resume_parsed is immutable after ingestion.
    """

    class Meta:
        model = Candidate
        fields = ["id", "name", "email", "resume_parsed", "created_at"]
        read_only_fields = ["id", "resume_parsed", "created_at"]

    def validate_email(self, value: str) -> str:
        """On update, allow keeping the same email but reject duplicates on other records."""
        qs = Candidate.objects.filter(email=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "A candidate with this email address already exists."
            )
        return value


class CandidateCreateSerializer(serializers.Serializer):
    """
    Creates a Candidate from a resume upload — PDF, or Word (.doc / .docx).

    Word uploads are converted to PDF server-side (LibreOffice headless, see
    resume_pipeline/ingestion/word_converter.py) before ResumeParser ever
    sees them, so the parsing stage stays PDF-only and unaware of the
    original upload format. The PDF (original or converted) is parsed by
    ResumeParser (pymupdf primary / pdfplumber fallback) and the resulting
    section dict is stored in resume_parsed. Raw text is stored in
    resume_raw for audit / reprocessing purposes.

    Accepts multipart/form-data:
        name        string   — candidate's full name
        email       string   — unique contact email
        resume_pdf  file     — PDF or Word resume (validated: content_type,
                               extension, max 10 MB). The field name stays
                               resume_pdf for backward API compatibility even
                               though it now also accepts Word documents.
    """
    name       = serializers.CharField(max_length=255)
    email      = serializers.EmailField()
    resume_pdf = serializers.FileField()

    #: PDF content-types — unchanged from the original PDF-only behavior.
    _PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}

    def validate_resume_pdf(self, file):
        from resume_pipeline.ingestion.word_converter import (
            WORD_CONTENT_TYPES,
            WORD_EXTENSIONS,
        )

        allowed_content_types = self._PDF_CONTENT_TYPES | WORD_CONTENT_TYPES
        allowed_extensions = (".pdf",) + WORD_EXTENSIONS

        ct = getattr(file, "content_type", "")
        name_lower = file.name.lower()
        if ct not in allowed_content_types and not name_lower.endswith(allowed_extensions):
            raise serializers.ValidationError(
                "Only PDF or Word (.doc, .docx) files are accepted."
            )
        if file.size > 10 * 1024 * 1024:  # 10 MB — applies to the original upload
            raise serializers.ValidationError("Resume file must be smaller than 10 MB.")
        return file

    def validate_email(self, value: str) -> str:
        if Candidate.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "A candidate with this email address already exists."
            )
        return value

    def create(self, validated_data: dict) -> Candidate:
        from resume_pipeline.ingestion.parser import ResumeParser

        pdf_file = validated_data["resume_pdf"]
        pdf_bytes = pdf_file.read()

        # Parse: extract raw text + section dict
        parser = ResumeParser()
        try:
            parsed = parser.parse(pdf_bytes)
        except Exception:
            # Graceful degradation: store raw bytes as text, empty sections
            parsed = {}

        raw_text = parsed.pop("_raw_text", "") or ""

        return Candidate.objects.create(
            name=validated_data["name"],
            email=validated_data["email"],
            resume_raw=raw_text,
            resume_parsed=parsed,
        )


# ---------------------------------------------------------------------------
# Application — list + create
# ---------------------------------------------------------------------------

class ApplicationListSerializer(serializers.ModelSerializer):
    """
    Table-row projection returned by GET /api/applications/.

    Includes denormalized candidate / job fields so the dashboard table
    never requires N+1 requests to show name and job title.
    """
    candidate_name  = serializers.CharField(source="candidate.name",  read_only=True)
    candidate_email = serializers.CharField(source="candidate.email", read_only=True)
    job_title       = serializers.CharField(source="job.title",       read_only=True)
    final_score     = serializers.SerializerMethodField()
    is_evaluated_via_fallback = serializers.SerializerMethodField()

    class Meta:
        model  = Application
        fields = [
            "id",
            "candidate_name",
            "candidate_email",
            "job_title",
            "status",
            "final_score",
            "is_evaluated_via_fallback",
            "created_at",
            "updated_at",
        ]

    def get_final_score(self, obj: Application) -> float | None:
        try:
            return obj.final_score.score
        except Exception:
            return None

    def get_is_evaluated_via_fallback(self, obj: Application) -> bool:
        try:
            return obj.rubric_score.is_evaluated_via_fallback
        except Exception:
            return False


class ApplicationCreateSerializer(serializers.Serializer):
    """
    Links an existing Job to an existing Candidate, creating an Application.

    Uses get_or_create so re-submitting the same pair is idempotent (returns
    the existing record with HTTP 200 rather than a 409 conflict).
    """
    job_id       = serializers.UUIDField()
    candidate_id = serializers.UUIDField()

    def validate(self, data: dict) -> dict:
        try:
            data["job"] = Job.objects.get(pk=data["job_id"])
        except Job.DoesNotExist:
            raise serializers.ValidationError({"job_id": "Job not found."})
        try:
            data["candidate"] = Candidate.objects.get(pk=data["candidate_id"])
        except Candidate.DoesNotExist:
            raise serializers.ValidationError({"candidate_id": "Candidate not found."})
        return data

    def create(self, validated_data: dict) -> tuple[Application, bool]:
        app, created = Application.objects.get_or_create(
            job=validated_data["job"],
            candidate=validated_data["candidate"],
        )
        return app, created


# ---------------------------------------------------------------------------
# Rubric breakdown (nested, read-only)
# ---------------------------------------------------------------------------

class RubricBreakdownSerializer(serializers.Serializer):
    """
    Per-competency scores exposed to the reviewer UI.

    Nested inside ApplicationScoreSerializer so the reviewer sees
    the full rubric picture, not just the normalized composite.
    Only the five raw 1–5 criterion scores are included here;
    normalized_score and evidence_quality live at the top-level score card.
    """
    core_skills = serializers.FloatField(read_only=True)
    relevant_experience = serializers.FloatField(read_only=True)
    scope_impact = serializers.FloatField(read_only=True)
    domain_alignment = serializers.FloatField(read_only=True)
    education_certs = serializers.FloatField(read_only=True)


# ---------------------------------------------------------------------------
# Application score card (read-only)
# ---------------------------------------------------------------------------

class ApplicationScoreSerializer(serializers.Serializer):
    """
    Full AI score card surfaced to the human reviewer.

    All fields are read-only — the score card is a view, not an input form.
    """
    application_id = serializers.UUIDField(read_only=True, source="application.id")
    final_score = serializers.FloatField(read_only=True, source="score")
    confidence = serializers.FloatField(read_only=True, allow_null=True)
    gate_passed = serializers.BooleanField(read_only=True)
    gate_outcome = serializers.SerializerMethodField(read_only=True)
    semantic_score = serializers.SerializerMethodField(read_only=True)
    rubric_score = serializers.SerializerMethodField(read_only=True)
    rubric_breakdown = serializers.SerializerMethodField(read_only=True)

    def get_gate_outcome(self, obj: FinalScore) -> str:
        try:
            return obj.application.gate_result.outcome
        except Exception:
            return "unknown"

    def get_semantic_score(self, obj: FinalScore) -> float | None:
        try:
            return obj.application.semantic_match.rrf_score
        except Exception:
            return None

    def get_rubric_score(self, obj: FinalScore) -> float | None:
        try:
            return obj.application.rubric_score.normalized_score
        except Exception:
            return None

    def get_rubric_breakdown(self, obj: FinalScore) -> dict | None:
        try:
            rubric: RubricScore = obj.application.rubric_score
            return RubricBreakdownSerializer(rubric).data
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Human Review (write — POST /api/applications/{id}/reviews/)
# ---------------------------------------------------------------------------

#: Decisions that legally require a non-empty reason for auditability.
OVERRIDE_DECISIONS = {
    HumanReview.Decision.OVERRIDE_PASS,
    HumanReview.Decision.OVERRIDE_FAIL,
}


class HumanReviewSerializer(serializers.Serializer):
    """
    Input serializer for creating a human review decision.

    Validation contract:
        - reviewer_email: required, valid email format.
        - decision: required, one of HumanReview.Decision choices.
        - override_reason: required and non-blank when decision is
          override_pass or override_fail; ignored (but accepted) otherwise.
    """
    reviewer_email = serializers.EmailField(required=True)
    decision = serializers.ChoiceField(
        choices=HumanReview.Decision.choices,
        required=True,
    )
    override_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        trim_whitespace=False,  # trimming is done in validate() so we can catch whitespace
    )

    def validate(self, data: dict) -> dict:
        """Cross-field validation: enforce reason for override decisions."""
        decision = data.get("decision", "")
        reason = data.get("override_reason", "").strip()

        if decision in OVERRIDE_DECISIONS and not reason:
            raise serializers.ValidationError(
                {
                    "override_reason": (
                        f"A non-empty reason is required for '{decision}' decisions. "
                        "This is mandatory for audit compliance."
                    )
                }
            )

        # Normalize: store stripped reason in validated data.
        data["override_reason"] = reason
        return data
