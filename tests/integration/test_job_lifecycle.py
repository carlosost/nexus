"""
Integration tests for the Job CRUD lifecycle and embedding pipeline.

Strategy:
  - Real Django ORM against SQLite (config.settings.test).
  - External embedding API stubbed — no network calls.
  - Verifies that: DB rows are created/updated/deleted correctly, cascade
    behaviours remove related rows, and embed_job_sections() is called at
    the right lifecycle points.

Run:
  pytest tests/integration/test_job_lifecycle.py -m integration
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from resume_pipeline.models import Job, JobSectionEmbedding

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def valid_markdown():
    return """\
# Senior Backend Engineer

## Description
We are looking for a Senior Backend Engineer with deep Python and Django
experience to lead backend development of our data platform.

## Requirements
### Required Skills
- Python
- Django
- PostgreSQL
- REST APIs
### Preferred Skills
- Redis
- Docker
- Kubernetes
### Minimum Experience
5 years

## Must Haves
### min_experience
type: years_experience
minimum_years: 5
### python_required
type: keyword_presence
keywords: Python
sections: skills, experience
### django_required
type: keyword_presence
keywords: Django
sections: skills, experience
"""


@pytest.fixture
def created_job(db, valid_markdown, api_client):
    """POST the valid markdown and return the response body as a dict."""
    with patch("resume_pipeline.views.embed_job_sections"):
        resp = api_client.post(
            "/api/jobs/",
            data={"raw_markdown": valid_markdown},
            format="json",
        )
    assert resp.status_code == 201
    return resp.data


# ---------------------------------------------------------------------------
# TestJobCreationPersistence
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestJobCreationPersistence:
    """Verify DB row matches parsed Markdown fields from JOB_SPEC."""

    def test_job_row_exists_after_create(self, created_job):
        assert Job.objects.filter(id=created_job["id"]).exists()

    def test_title_persisted_correctly(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        assert job.title == "Senior Backend Engineer"

    def test_description_persisted_correctly(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        assert "data platform" in job.description

    def test_required_skills_in_requirements_raw(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        assert "Python" in job.requirements_raw["required_skills"]
        assert "Django" in job.requirements_raw["required_skills"]

    def test_minimum_experience_years_is_integer(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        assert job.requirements_raw["minimum_experience_years"] == 5

    def test_must_haves_min_experience_persisted(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        assert job.must_haves["min_experience"]["minimum_years"] == 5

    def test_must_haves_python_required_sections(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        sections = job.must_haves["python_required"]["sections"]
        assert "skills" in sections
        assert "experience" in sections

    def test_created_at_is_populated(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        assert job.created_at is not None


# ---------------------------------------------------------------------------
# TestEmbeddingPipelineIntegration
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEmbeddingPipelineIntegration:
    """Verify embedding calls fire at the correct lifecycle points."""

    def test_embed_called_once_on_create(self, db, valid_markdown, api_client):
        with patch("resume_pipeline.views.embed_job_sections") as mock_embed:
            api_client.post(
                "/api/jobs/",
                data={"raw_markdown": valid_markdown},
                format="json",
            )
        mock_embed.assert_called_once()

    def test_embed_receives_the_persisted_job_instance(self, db, valid_markdown, api_client):
        with patch("resume_pipeline.views.embed_job_sections") as mock_embed:
            resp = api_client.post(
                "/api/jobs/",
                data={"raw_markdown": valid_markdown},
                format="json",
            )
        called_with_job = mock_embed.call_args[0][0]
        assert str(called_with_job.id) == resp.data["id"]

    def test_embed_not_called_on_delete(self, db, created_job, api_client):
        job_id = created_job["id"]
        with patch("resume_pipeline.views.embed_job_sections") as mock_embed:
            api_client.delete(f"/api/jobs/{job_id}/")
        mock_embed.assert_not_called()

    def test_embed_timeout_does_not_fail_create(self, db, valid_markdown, api_client):
        with patch("resume_pipeline.views.embed_job_sections",
                   side_effect=TimeoutError("Embedding service unreachable")):
            resp = api_client.post(
                "/api/jobs/",
                data={"raw_markdown": valid_markdown},
                format="json",
            )
        assert resp.status_code == 201
        # Job record must exist despite the embedding failure
        assert Job.objects.filter(id=resp.data["id"]).exists()

    def test_job_section_embeddings_created_by_embedder(self, db, valid_markdown, api_client):
        """
        The real embed_job_sections() creates JobSectionEmbedding rows.
        Test with the actual embedder but a stubbed embedding API call.
        """
        STUB_VECTOR = [0.0] * 1536
        with patch(
            "resume_pipeline.pipeline.job_embedder._call_embedding_api",
            return_value=STUB_VECTOR,
        ):
            resp = api_client.post(
                "/api/jobs/",
                data={"raw_markdown": valid_markdown},
                format="json",
            )
        job = Job.objects.get(id=resp.data["id"])
        embeddings = JobSectionEmbedding.objects.filter(job=job)
        # At minimum: title, description, requirements, must_haves
        assert embeddings.count() >= 4

    def test_patch_replaces_existing_section_embeddings(self, db, valid_markdown, api_client):
        STUB_VECTOR = [0.0] * 1536
        with patch(
            "resume_pipeline.pipeline.job_embedder._call_embedding_api",
            return_value=STUB_VECTOR,
        ):
            resp = api_client.post(
                "/api/jobs/",
                data={"raw_markdown": valid_markdown},
                format="json",
            )
            job_id = resp.data["id"]
            count_before = JobSectionEmbedding.objects.filter(job_id=job_id).count()
            api_client.patch(
                f"/api/jobs/{job_id}/",
                data={"description": "Completely rewritten description."},
                format="json",
            )
        count_after = JobSectionEmbedding.objects.filter(job_id=job_id).count()
        # Row count should not balloon — upsert semantics (get_or_create + update)
        assert count_after == count_before


# ---------------------------------------------------------------------------
# TestCascadeDeleteCleanup — zero orphan vectors
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCascadeDeleteCleanup:
    """Deleting a Job must leave no orphan rows in any related table."""

    def test_job_section_embeddings_deleted_on_job_delete(
        self, db, valid_markdown, api_client
    ):
        STUB_VECTOR = [0.0] * 1536
        with patch(
            "resume_pipeline.pipeline.job_embedder._call_embedding_api",
            return_value=STUB_VECTOR,
        ):
            resp = api_client.post(
                "/api/jobs/",
                data={"raw_markdown": valid_markdown},
                format="json",
            )
        job_id = resp.data["id"]
        assert JobSectionEmbedding.objects.filter(job_id=job_id).count() > 0

        api_client.delete(f"/api/jobs/{job_id}/")

        # Explicit assertion — not relying solely on CASCADE
        assert JobSectionEmbedding.objects.filter(job_id=job_id).count() == 0

    def test_job_row_deleted(self, db, created_job, api_client):
        job_id = created_job["id"]
        api_client.delete(f"/api/jobs/{job_id}/")
        assert not Job.objects.filter(id=job_id).exists()

    def test_get_after_delete_returns_404(self, db, created_job, api_client):
        job_id = created_job["id"]
        api_client.delete(f"/api/jobs/{job_id}/")
        resp = api_client.get(f"/api/jobs/{job_id}/")
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_404_no_side_effects(self, db, api_client):
        phantom_id = str(uuid.uuid4())
        resp = api_client.delete(f"/api/jobs/{phantom_id}/")
        assert resp.status_code == 404
        # Nothing was deleted — count is still 0
        assert Job.objects.count() == 0
