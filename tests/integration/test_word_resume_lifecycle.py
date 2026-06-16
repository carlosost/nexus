"""
Integration tests for Word (.doc / .docx) resume ingestion — M8.

Strategy:
  - Real Django ORM against SQLite (config.settings.test).
  - Real APIClient hitting POST /api/candidates/.
  - convert_word_to_pdf() is stubbed — no real LibreOffice binary is
    required in CI or this dev sandbox, exactly like embed_job_sections()
    is stubbed in tests/integration/test_job_lifecycle.py.
  - ResumeParser is NOT stubbed: it degrades gracefully on the fake PDF
    bytes the stub returns, exercising the real (already-tested) parsing
    path end to end.

Run:
  pytest tests/integration/test_word_resume_lifecycle.py -m integration
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from resume_pipeline.ingestion.word_converter import WordConversionError
from resume_pipeline.models import Candidate

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


def _docx_upload(name: str = "resume.docx"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        name,
        b"PK\x03\x04 fake docx bytes",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _doc_upload(name: str = "resume.doc"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        name, b"\xd0\xcf\x11\xe0 fake legacy doc bytes", content_type="application/msword"
    )


def _pdf_upload(name: str = "resume.pdf"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, b"%PDF-1.4 fake pdf bytes", content_type="application/pdf")


# ---------------------------------------------------------------------------
# Successful Word conversion → Candidate persisted
# ---------------------------------------------------------------------------

class TestWordResumeCreatesCandidate:

    def test_docx_upload_creates_candidate(self, db, api_client):
        with patch(
            "resume_pipeline.views.convert_word_to_pdf",
            return_value=b"%PDF-1.4 converted from docx",
        ) as mock_convert:
            resp = api_client.post(
                "/api/candidates/",
                data={
                    "name": "Alice Johnson",
                    "email": "alice.docx@example.com",
                    "resume_pdf": _docx_upload(),
                },
                format="multipart",
            )

        assert resp.status_code == 201, resp.data
        assert Candidate.objects.filter(email="alice.docx@example.com").exists()
        mock_convert.assert_called_once()

    def test_legacy_doc_upload_creates_candidate(self, db, api_client):
        with patch(
            "resume_pipeline.views.convert_word_to_pdf",
            return_value=b"%PDF-1.4 converted from doc",
        ) as mock_convert:
            resp = api_client.post(
                "/api/candidates/",
                data={
                    "name": "Bob Singh",
                    "email": "bob.doc@example.com",
                    "resume_pdf": _doc_upload(),
                },
                format="multipart",
            )

        assert resp.status_code == 201, resp.data
        assert Candidate.objects.filter(email="bob.doc@example.com").exists()
        mock_convert.assert_called_once()

    def test_converted_pdf_bytes_are_fed_to_the_parser(self, db, api_client):
        """The candidate is created using the CONVERTED bytes, not the raw Word bytes."""
        with patch(
            "resume_pipeline.views.convert_word_to_pdf",
            return_value=b"%PDF-1.4\nExperience\nSenior Engineer at Acme 2020-2024\n",
        ):
            resp = api_client.post(
                "/api/candidates/",
                data={
                    "name": "Carol Diaz",
                    "email": "carol.docx@example.com",
                    "resume_pdf": _docx_upload(),
                },
                format="multipart",
            )

        assert resp.status_code == 201, resp.data
        candidate = Candidate.objects.get(email="carol.docx@example.com")
        # resume_raw / resume_parsed should reflect whatever ResumeParser
        # extracted from the CONVERTED pdf bytes — not raise, not be None.
        assert candidate.resume_raw is not None


# ---------------------------------------------------------------------------
# Conversion failure handling — no orphan Candidate rows
# ---------------------------------------------------------------------------

class TestWordConversionFailureHandling:

    def test_conversion_failure_returns_400_and_creates_no_candidate(self, db, api_client):
        with patch(
            "resume_pipeline.views.convert_word_to_pdf",
            side_effect=WordConversionError("soffice exited with code 1"),
        ):
            resp = api_client.post(
                "/api/candidates/",
                data={
                    "name": "Dana Lee",
                    "email": "dana.fail@example.com",
                    "resume_pdf": _docx_upload(),
                },
                format="multipart",
            )

        assert resp.status_code == 400
        assert "resume_pdf" in resp.data
        assert not Candidate.objects.filter(email="dana.fail@example.com").exists()

    def test_conversion_timeout_returns_400_and_creates_no_candidate(self, db, api_client):
        with patch(
            "resume_pipeline.views.convert_word_to_pdf",
            side_effect=WordConversionError("Conversion timed out after 30s."),
        ):
            resp = api_client.post(
                "/api/candidates/",
                data={
                    "name": "Erin Walsh",
                    "email": "erin.timeout@example.com",
                    "resume_pdf": _docx_upload(),
                },
                format="multipart",
            )

        assert resp.status_code == 400
        assert "resume_pdf" in resp.data
        assert not Candidate.objects.filter(email="erin.timeout@example.com").exists()


# ---------------------------------------------------------------------------
# Regression — existing PDF path unaffected
# ---------------------------------------------------------------------------

class TestPdfUploadRegression:

    def test_pdf_upload_still_works_and_skips_conversion(self, db, api_client):
        with patch("resume_pipeline.views.convert_word_to_pdf") as mock_convert:
            resp = api_client.post(
                "/api/candidates/",
                data={
                    "name": "Frank Otieno",
                    "email": "frank.pdf@example.com",
                    "resume_pdf": _pdf_upload(),
                },
                format="multipart",
            )

        assert resp.status_code == 201, resp.data
        assert Candidate.objects.filter(email="frank.pdf@example.com").exists()
        mock_convert.assert_not_called()

    def test_disallowed_file_type_rejected_without_invoking_converter(self, db, api_client):
        from django.core.files.uploadedfile import SimpleUploadedFile

        with patch("resume_pipeline.views.convert_word_to_pdf") as mock_convert:
            resp = api_client.post(
                "/api/candidates/",
                data={
                    "name": "Grace Kim",
                    "email": "grace.txt@example.com",
                    "resume_pdf": SimpleUploadedFile(
                        "resume.txt", b"plain text resume", content_type="text/plain"
                    ),
                },
                format="multipart",
            )

        assert resp.status_code == 400
        assert "resume_pdf" in resp.data
        mock_convert.assert_not_called()
        assert not Candidate.objects.filter(email="grace.txt@example.com").exists()
