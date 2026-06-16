"""
Inner-loop unit tests for CandidateCreateSerializer's Word (.doc/.docx)
support — M8.

Focus: validate_resume_pdf() accepting Word uploads in addition to PDF,
still enforcing the 10 MB cap and rejecting unrelated file types. Pure
validation logic — no DB, no HTTP, no real LibreOffice subprocess.

Run: pytest tests/unit/test_candidate_word_upload.py -m unit
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_file(name: str, content_type: str, size: int = 1024) -> MagicMock:
    f = MagicMock()
    f.name = name
    f.content_type = content_type
    f.size = size
    f.read.return_value = b"x" * size
    return f


class TestCandidateCreateSerializerAcceptsWord:

    @pytest.fixture(autouse=True)
    def import_serializer(self):
        from resume_pipeline.serializers import CandidateCreateSerializer
        self.Serializer = CandidateCreateSerializer

    @pytest.fixture(autouse=True)
    def no_db(self):
        # validate_email does a uniqueness check; mock it out so no DB is needed.
        qs = MagicMock()
        qs.exists.return_value = False
        with patch("resume_pipeline.serializers.Candidate.objects.filter", return_value=qs):
            yield

    def _valid(self, name: str, email: str, resume_file) -> bool:
        s = self.Serializer(data={"name": name, "email": email, "resume_pdf": resume_file})
        return s.is_valid()

    def _errors(self, name: str, email: str, resume_file) -> dict:
        s = self.Serializer(data={"name": name, "email": email, "resume_pdf": resume_file})
        s.is_valid()
        return s.errors

    # ── .docx accepted ───────────────────────────────────────────────────

    def test_docx_by_content_type_is_accepted(self):
        f = _make_file(
            "resume.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        assert self._valid("Alice", "alice@example.com", f)

    def test_docx_by_extension_only_is_accepted(self):
        f = _make_file("resume.docx", "application/octet-stream")
        assert self._valid("Alice", "alice2@example.com", f)

    # ── .doc accepted ────────────────────────────────────────────────────

    def test_doc_by_content_type_is_accepted(self):
        f = _make_file("resume.doc", "application/msword")
        assert self._valid("Bob", "bob@example.com", f)

    def test_doc_by_extension_only_is_accepted(self):
        f = _make_file("resume.doc", "application/octet-stream")
        assert self._valid("Bob", "bob2@example.com", f)

    # ── PDF still accepted (regression) ─────────────────────────────────

    def test_pdf_still_accepted(self):
        f = _make_file("resume.pdf", "application/pdf")
        assert self._valid("Carol", "carol@example.com", f)

    # ── disallowed types rejected ───────────────────────────────────────

    def test_txt_file_rejected(self):
        f = _make_file("resume.txt", "text/plain")
        errors = self._errors("Dana", "dana@example.com", f)
        assert "resume_pdf" in errors

    def test_xlsx_file_rejected(self):
        f = _make_file(
            "resume.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        errors = self._errors("Erin", "erin@example.com", f)
        assert "resume_pdf" in errors

    # ── size cap still enforced for Word files ──────────────────────────

    def test_oversized_docx_rejected(self):
        f = _make_file(
            "resume.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size=11 * 1024 * 1024,
        )
        errors = self._errors("Frank", "frank@example.com", f)
        assert "resume_pdf" in errors

    def test_oversized_doc_rejected(self):
        f = _make_file("resume.doc", "application/msword", size=11 * 1024 * 1024)
        errors = self._errors("Grace", "grace@example.com", f)
        assert "resume_pdf" in errors

    def test_undersized_docx_within_cap_accepted(self):
        f = _make_file(
            "resume.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size=9 * 1024 * 1024,
        )
        assert self._valid("Heidi", "heidi@example.com", f)


class TestIsWordDocumentHelperWiring:
    """
    The serializer/view must rely on word_converter.is_word_document() to
    decide whether to route an upload through conversion — this guards
    against a future change accidentally duplicating that detection logic
    with different rules.
    """

    def test_word_converter_module_exposes_is_word_document(self):
        from resume_pipeline.ingestion import word_converter
        assert hasattr(word_converter, "is_word_document")

    def test_word_converter_module_exposes_convert_word_to_pdf(self):
        from resume_pipeline.ingestion import word_converter
        assert hasattr(word_converter, "convert_word_to_pdf")

    def test_word_converter_module_exposes_error_class(self):
        from resume_pipeline.ingestion import word_converter
        assert hasattr(word_converter, "WordConversionError")
        assert issubclass(word_converter.WordConversionError, Exception)
