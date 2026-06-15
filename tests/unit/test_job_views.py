"""
Inner-loop unit tests for Job API views.

Strategy:
  - All views exercised through DRF's APIRequestFactory.
  - Job ORM model patched at resume_pipeline.views.Job.
  - parse_job_markdown patched at resume_pipeline.views.parse_job_markdown.
  - embed_job_sections patched at resume_pipeline.views.embed_job_sections.
  - No DB, no network, no real parser execution.

Run:
  pytest tests/unit/test_job_views.py -m unit
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory

pytestmark = pytest.mark.unit

FACTORY = APIRequestFactory()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job_mock(**overrides):
    """Return a minimal Job mock matching JobDetailSerializer expectations."""
    job = MagicMock()
    job.id               = overrides.get("id", uuid.uuid4())
    job.title            = overrides.get("title", "Senior Backend Engineer")
    job.description      = overrides.get("description", "Detailed description.")
    job.requirements_raw = overrides.get("requirements_raw", {})
    job.must_haves       = overrides.get("must_haves", {})
    job.created_at       = overrides.get("created_at", "2024-01-15T12:00:00Z")
    job.updated_at       = overrides.get("updated_at", "2024-01-15T12:00:00Z")
    return job


VALID_MARKDOWN_BODY = {"raw_markdown": "# My Job\n\n## Description\nDetails here.\n"}

MOCK_JOB_SPEC = MagicMock()
MOCK_JOB_SPEC.title            = "My Job"
MOCK_JOB_SPEC.description      = "Details here."
MOCK_JOB_SPEC.requirements_raw = {}
MOCK_JOB_SPEC.must_haves       = {}
MOCK_JOB_SPEC.to_model_kwargs.return_value = {
    "title":            "My Job",
    "description":      "Details here.",
    "requirements_raw": {},
    "must_haves":       {},
}


# ---------------------------------------------------------------------------
# TestJobListCreateView
# ---------------------------------------------------------------------------

class TestJobListCreateView:

    def _post(self, body: dict):
        from resume_pipeline.views import JobListCreateView
        request = FACTORY.post("/api/jobs/", data=body, format="json")
        return JobListCreateView.as_view()(request)

    def test_valid_markdown_returns_201(self):
        with (
            patch("resume_pipeline.views.parse_job_markdown", return_value=MOCK_JOB_SPEC),
            patch("resume_pipeline.views.Job") as MockJob,
            patch("resume_pipeline.views.embed_job_sections"),
        ):
            MockJob.objects.create.return_value = _make_job_mock()
            resp = self._post(VALID_MARKDOWN_BODY)
        assert resp.status_code == 201

    def test_response_contains_id_field(self):
        with (
            patch("resume_pipeline.views.parse_job_markdown", return_value=MOCK_JOB_SPEC),
            patch("resume_pipeline.views.Job") as MockJob,
            patch("resume_pipeline.views.embed_job_sections"),
        ):
            MockJob.objects.create.return_value = _make_job_mock()
            resp = self._post(VALID_MARKDOWN_BODY)
        assert "id" in resp.data

    def test_blank_raw_markdown_returns_400(self):
        resp = self._post({"raw_markdown": ""})
        assert resp.status_code == 400
        assert "raw_markdown" in resp.data

    def test_missing_raw_markdown_key_returns_400(self):
        resp = self._post({})
        assert resp.status_code == 400

    def test_parser_job_parse_error_returns_422(self):
        from resume_pipeline.ingestion.job_parser import JobParseError
        with patch("resume_pipeline.views.parse_job_markdown",
                   side_effect=JobParseError("title", "Missing H1")):
            resp = self._post(VALID_MARKDOWN_BODY)
        assert resp.status_code == 422
        assert "title" in resp.data

    def test_parser_error_does_not_call_job_create(self):
        from resume_pipeline.ingestion.job_parser import JobParseError
        with (
            patch("resume_pipeline.views.parse_job_markdown",
                  side_effect=JobParseError("title", "Missing H1")),
            patch("resume_pipeline.views.Job") as MockJob,
        ):
            self._post(VALID_MARKDOWN_BODY)
        MockJob.objects.create.assert_not_called()

    def test_embed_job_sections_called_after_create(self):
        with (
            patch("resume_pipeline.views.parse_job_markdown", return_value=MOCK_JOB_SPEC),
            patch("resume_pipeline.views.Job") as MockJob,
            patch("resume_pipeline.views.embed_job_sections") as mock_embed,
        ):
            created_job = _make_job_mock()
            MockJob.objects.create.return_value = created_job
            self._post(VALID_MARKDOWN_BODY)
        mock_embed.assert_called_once_with(created_job)

    def test_embed_timeout_still_returns_201(self):
        """Embedding failure must NOT fail the HTTP response."""
        with (
            patch("resume_pipeline.views.parse_job_markdown", return_value=MOCK_JOB_SPEC),
            patch("resume_pipeline.views.Job") as MockJob,
            patch("resume_pipeline.views.embed_job_sections",
                  side_effect=TimeoutError("Embedding service unreachable")),
        ):
            MockJob.objects.create.return_value = _make_job_mock()
            resp = self._post(VALID_MARKDOWN_BODY)
        assert resp.status_code == 201

    def test_duplicate_title_returns_409(self):
        from django.db import IntegrityError
        with (
            patch("resume_pipeline.views.parse_job_markdown", return_value=MOCK_JOB_SPEC),
            patch("resume_pipeline.views.Job") as MockJob,
        ):
            MockJob.objects.create.side_effect = IntegrityError("unique constraint")
            resp = self._post(VALID_MARKDOWN_BODY)
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# TestJobDetailView
# ---------------------------------------------------------------------------

class TestJobDetailView:

    def _get(self, pk: str):
        from resume_pipeline.views import JobDetailView
        request = FACTORY.get(f"/api/jobs/{pk}/")
        return JobDetailView.as_view()(request, pk=pk)

    def _delete(self, pk: str):
        from resume_pipeline.views import JobDetailView
        request = FACTORY.delete(f"/api/jobs/{pk}/")
        return JobDetailView.as_view()(request, pk=pk)

    def test_get_existing_job_returns_200(self):
        pk = str(uuid.uuid4())
        with patch("resume_pipeline.views.get_object_or_404",
                   return_value=_make_job_mock(id=pk)):
            resp = self._get(pk)
        assert resp.status_code == 200

    def test_get_response_contains_required_fields(self):
        pk = str(uuid.uuid4())
        with patch("resume_pipeline.views.get_object_or_404",
                   return_value=_make_job_mock(id=pk)):
            resp = self._get(pk)
        for field in ("id", "title", "description", "must_haves"):
            assert field in resp.data, f"'{field}' missing from response"

    def test_delete_returns_204(self):
        pk = str(uuid.uuid4())
        job = _make_job_mock(id=pk)
        with patch("resume_pipeline.views.get_object_or_404", return_value=job):
            resp = self._delete(pk)
        assert resp.status_code == 204

    def test_delete_calls_job_delete(self):
        pk = str(uuid.uuid4())
        job = _make_job_mock(id=pk)
        with patch("resume_pipeline.views.get_object_or_404", return_value=job):
            self._delete(pk)
        job.delete.assert_called_once()
