"""
Resume Pipeline API Views.

Endpoints:
    POST /api/applications/<uuid:pk>/run/
         → Triggers the 4-stage pipeline for the application synchronously.
         → 200 with pipeline result on success.
         → 404 if application does not exist.

    GET  /api/applications/<uuid:pk>/score/
         → Returns the AI score card (ApplicationScoreSerializer).
         → 404 if the application has no FinalScore yet (not yet scored).

    POST /api/applications/<uuid:pk>/reviews/
         → Creates a HumanReview, transitions Application.status, logs overrides.
         → 400 if override decision is missing a reason (serializer validation).
         → 404 if application does not exist.
         → 201 on success with the created review data.

Authentication note:
    These endpoints assume authentication is handled by Django REST Framework's
    configured DEFAULT_AUTHENTICATION_CLASSES. For the initial API milestone,
    basic token auth is sufficient. JWT can be wired in later.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from resume_pipeline.models import Application, FinalScore, HumanReview
from resume_pipeline.serializers import ApplicationScoreSerializer, HumanReviewSerializer
from resume_pipeline.services import PipelineService, ReviewService


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
        result = self._service.run(application)
        return Response(result, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Score card
# ---------------------------------------------------------------------------

class ApplicationScoreView(APIView):
    """
    GET /api/applications/<uuid:pk>/score/

    Returns the full AI score card for a reviewer to inspect before deciding.
    Only accessible for applications that have completed the scoring pipeline
    (i.e., have a FinalScore record).
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
            "decision": "override_pass",           # or approve / reject / override_fail
            "override_reason": "Strong portfolio"  # required for override_* decisions
        }

    Response (201):
        {
            "id": "<uuid>",
            "reviewer_email": "alice@company.com",
            "decision": "override_pass",
            "override_reason": "Strong portfolio",
            "ai_score_at_review": 0.82,
            "reviewed_at": "2026-06-13T10:00:00Z"
        }
    """

    _service = ReviewService()

    def post(self, request: Request, pk: str) -> Response:
        application = get_object_or_404(Application, pk=pk)

        # Validate input — enforces override_reason rule and email format.
        serializer = HumanReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data

        # Fetch current score for the audit snapshot.
        try:
            final_score_obj = application.final_score
            ai_score = final_score_obj.score
            confidence = final_score_obj.confidence
        except FinalScore.DoesNotExist:
            ai_score = 0.0
            confidence = None

        # Persist the review.
        review = HumanReview.objects.create(
            application=application,
            reviewer_email=validated["reviewer_email"],
            decision=validated["decision"],
            override_reason=validated.get("override_reason", ""),
            ai_score_at_review=ai_score,
            confidence_at_review=confidence,
        )

        # Apply status transition + audit logging.
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
