"""
URL routing for the resume_pipeline app.

Included from config/urls.py under the /api/ prefix:
    urlpatterns = [
        path("api/", include("resume_pipeline.urls")),
    ]

Endpoints:
    POST /api/applications/<uuid:pk>/run/        → RunPipelineView
    GET  /api/applications/<uuid:pk>/score/      → ApplicationScoreView
    POST /api/applications/<uuid:pk>/reviews/    → HumanReviewCreateView
"""

from django.http import JsonResponse
from django.urls import path

from resume_pipeline.views import ApplicationScoreView, HumanReviewCreateView, RunPipelineView


def health_check(request):
    """Lightweight liveness probe for Docker and smoke tests."""
    return JsonResponse({"status": "ok"})


app_name = "resume_pipeline"

urlpatterns = [
    path("health/", health_check, name="health"),
    path(
        "applications/<uuid:pk>/run/",
        RunPipelineView.as_view(),
        name="application-run-pipeline",
    ),
    path(
        "applications/<uuid:pk>/score/",
        ApplicationScoreView.as_view(),
        name="application-score",
    ),
    path(
        "applications/<uuid:pk>/reviews/",
        HumanReviewCreateView.as_view(),
        name="human-review-create",
    ),
]
