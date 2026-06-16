"""
URL routing for the resume_pipeline app.

Included from config/urls.py under the /api/ prefix:
    urlpatterns = [
        path("api/", include("resume_pipeline.urls")),
    ]

Collection endpoints (list + create):
    GET  /api/jobs/                           → list all jobs
    POST /api/jobs/                           → create a job
    GET  /api/candidates/                     → list all candidates
    POST /api/candidates/                     → create a candidate (PDF upload)
    GET  /api/applications/                   → list all applications (with scores)
    POST /api/applications/                   → associate job + candidate

Detail endpoints (get / delete):
    GET    /api/jobs/<uuid>/                  → full job record
    DELETE /api/jobs/<uuid>/                  → hard-delete (cascades to Applications)
    GET    /api/candidates/<uuid>/            → full candidate record (with resume_parsed)
    DELETE /api/candidates/<uuid>/            → hard-delete (cascades to Applications)
    DELETE /api/applications/<uuid>/          → remove application record

Per-application pipeline actions:
    POST /api/applications/<uuid>/run/        → trigger pipeline evaluation
    GET  /api/applications/<uuid>/score/      → fetch AI score card
    POST /api/applications/<uuid>/reviews/    → submit human review decision

Utility:
    GET  /api/health/                         → Docker liveness probe
"""

from django.http import JsonResponse
from django.urls import path

from resume_pipeline.views import (
    ApplicationDetailView,
    ApplicationListCreateView,
    ApplicationScoreView,
    CandidateDetailView,
    CandidateListCreateView,
    DashboardStatsView,
    HumanReviewCreateView,
    JobDetailView,
    JobListCreateView,
    RunPipelineView,
)


def health_check(request):
    """Lightweight liveness probe for Docker and smoke tests."""
    return JsonResponse({"status": "ok"})


app_name = "resume_pipeline"

urlpatterns = [
    # ── Utility ───────────────────────────────────────────────────────────────
    path("health/",            health_check,           name="health"),
    path("dashboard/stats/",   DashboardStatsView.as_view(), name="dashboard-stats"),

    # ── Resource collections (list + create) ──────────────────────────────────
    path("jobs/",         JobListCreateView.as_view(),         name="job-list-create"),
    path("candidates/",   CandidateListCreateView.as_view(),   name="candidate-list-create"),
    path("applications/", ApplicationListCreateView.as_view(), name="application-list-create"),

    # ── Resource detail (get / patch / delete) ─────────────────────────────────
    path("jobs/<uuid:pk>/",         JobDetailView.as_view(),         name="job-detail"),
    path("candidates/<uuid:pk>/",   CandidateDetailView.as_view(),   name="candidate-detail"),
    path("applications/<uuid:pk>/", ApplicationDetailView.as_view(), name="application-detail"),

    # ── Per-application pipeline actions ──────────────────────────────────────
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
