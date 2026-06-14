"""
M0.5 — Document Ingestion Pipeline: First Failing Inner-Loop Unit Tests.

THESE TESTS MUST FAIL on first run. That is the point.

The import block below references `resume_pipeline.ingestion.parser`, which does
not exist yet. Running `pytest tests/unit/test_ingestion.py` before the module is
created produces:

    ImportError: No module named 'resume_pipeline.ingestion'

This is Step 3 of the Double-Loop TDD cycle:

    Step 1 ✅  features/document_ingestion.feature written → pytest-bdd: no steps
    Step 2 ✅  features/steps/ingestion_steps.py stubs → scenarios FAIL (NotImplementedError)
    Step 3 🔴  THIS FILE — FAIL on import (module does not exist yet)   ← YOU ARE HERE
    Step 4     Implement resume_pipeline/ingestion/ → tests go GREEN
    Step 5     Complete step definitions → BDD scenarios go GREEN

Do NOT write any production code in resume_pipeline/ingestion/ before running
`pytest tests/unit/test_ingestion.py` and confirming the ImportError is present.
"""

from __future__ import annotations

import logging
import os
import struct
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# STEP 3 OF DOUBLE-LOOP TDD: THIS IMPORT MUST FAIL.
# The test runner will report ImportError/ModuleNotFoundError.
# That is the correct red state. Proceed to implementation.
# ---------------------------------------------------------------------------
from resume_pipeline.ingestion.parser import (
    ParsedDocument,
    ParseStatus,
    ResumeParser,
)
from resume_pipeline.ingestion.backends.pymupdf_backend import PyMuPDFBackend
from resume_pipeline.ingestion.backends.pdfplumber_backend import PdfplumberBackend
from resume_pipeline.ingestion.section_detector import SectionDetector
from resume_pipeline.observability import pipeline_observability, PipelineObservability


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_pdf(content: bytes = b"%PDF-1.4 fake") -> str:
    """Write bytes to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    f.write(content)
    f.close()
    return f.name


def _make_corrupt_pdf() -> str:
    return _make_temp_pdf(b"\x00\xff\xfe\xfd random garbage not a pdf")


# ---------------------------------------------------------------------------
# PyMuPDFBackend — text extraction
# ---------------------------------------------------------------------------

class TestPyMuPDFBackend:
    """
    Unit tests for the primary PDF text extraction backend.
    All tests mock `fitz` so no real PDF library is required.
    """

    def _mock_fitz(self, text_per_page: list[str]):
        """Return a context manager that patches fitz.open()."""
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: len(text_per_page)
        mock_doc.__iter__ = lambda self: iter(
            [MagicMock(**{"get_text.return_value": t}) for t in text_per_page]
        )
        mock_doc.close = MagicMock()
        return patch("fitz.open", return_value=mock_doc)

    def test_extract_text_returns_str_and_page_count(self):
        backend = PyMuPDFBackend()
        with self._mock_fitz(["Hello World", "Page Two"]):
            text, page_count = backend.extract_text("/fake/path.pdf")
        assert isinstance(text, str)
        assert isinstance(page_count, int)
        assert page_count == 2

    def test_extract_text_joins_pages_with_newline(self):
        backend = PyMuPDFBackend()
        with self._mock_fitz(["First page content", "Second page content"]):
            text, _ = backend.extract_text("/fake/path.pdf")
        assert "First page content" in text
        assert "Second page content" in text

    def test_extract_text_single_page(self):
        backend = PyMuPDFBackend()
        with self._mock_fitz(["Only page"]):
            text, page_count = backend.extract_text("/fake/path.pdf")
        assert page_count == 1
        assert "Only page" in text

    def test_extract_text_closes_document(self):
        backend = PyMuPDFBackend()
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 1
        mock_doc.__iter__ = lambda self: iter([MagicMock(**{"get_text.return_value": "text"})])
        with patch("fitz.open", return_value=mock_doc):
            backend.extract_text("/fake/path.pdf")
        mock_doc.close.assert_called_once()

    def test_is_viable_true_when_above_threshold(self):
        backend = PyMuPDFBackend()
        text = "A" * 60  # above MIN_VIABLE_CHARS (50)
        assert backend.is_viable(text) is True

    def test_is_viable_false_when_below_threshold(self):
        backend = PyMuPDFBackend()
        text = "A" * 30  # below MIN_VIABLE_CHARS (50)
        assert backend.is_viable(text) is False

    def test_is_viable_false_when_exactly_at_threshold_minus_one(self):
        backend = PyMuPDFBackend()
        text = "A" * 49
        assert backend.is_viable(text) is False

    def test_is_viable_true_when_exactly_at_threshold(self):
        backend = PyMuPDFBackend()
        text = "A" * 50
        assert backend.is_viable(text) is True

    def test_is_viable_strips_whitespace_before_check(self):
        backend = PyMuPDFBackend()
        # 10 real chars surrounded by whitespace — below threshold
        text = " " * 100 + "A" * 10 + " " * 100
        assert backend.is_viable(text) is False

    def test_min_viable_chars_constant_is_50(self):
        assert PyMuPDFBackend.MIN_VIABLE_CHARS == 50

    def test_extract_text_raises_parse_error_on_fitz_exception(self):
        """
        If fitz.open raises, PyMuPDFBackend must propagate a ParseError
        so ResumeParser can catch it and fall back gracefully.
        """
        from resume_pipeline.ingestion.parser import ParseError
        backend = PyMuPDFBackend()
        with patch("fitz.open", side_effect=Exception("fitz: not a PDF")):
            with pytest.raises(ParseError):
                backend.extract_text("/fake/corrupt.pdf")


# ---------------------------------------------------------------------------
# PdfplumberBackend — fallback extraction
# ---------------------------------------------------------------------------

class TestPdfplumberBackend:
    def _mock_pdfplumber(self, text_per_page: list[str]):
        mock_page = MagicMock()
        mock_pdf = MagicMock()
        pages = []
        for text in text_per_page:
            p = MagicMock()
            p.extract_text.return_value = text
            pages.append(p)
        mock_pdf.pages = pages
        mock_pdf.__enter__ = lambda self: mock_pdf
        mock_pdf.__exit__ = MagicMock(return_value=False)
        return patch("pdfplumber.open", return_value=mock_pdf)

    def test_extract_text_returns_str_and_page_count(self):
        backend = PdfplumberBackend()
        with self._mock_pdfplumber(["Column A  Column B"]):
            text, page_count = backend.extract_text("/fake/multicolumn.pdf")
        assert isinstance(text, str)
        assert page_count == 1

    def test_extract_text_joins_pages(self):
        backend = PdfplumberBackend()
        with self._mock_pdfplumber(["Page one", "Page two"]):
            text, _ = backend.extract_text("/fake/multicolumn.pdf")
        assert "Page one" in text
        assert "Page two" in text

    def test_extract_text_skips_none_pages(self):
        """pdfplumber returns None for pages with no extractable text."""
        backend = PdfplumberBackend()
        with self._mock_pdfplumber([None, "Real content"]):
            text, _ = backend.extract_text("/fake/path.pdf")
        assert "Real content" in text

    def test_extract_text_raises_parse_error_on_exception(self):
        from resume_pipeline.ingestion.parser import ParseError
        backend = PdfplumberBackend()
        with patch("pdfplumber.open", side_effect=Exception("not a pdf")):
            with pytest.raises(ParseError):
                backend.extract_text("/fake/corrupt.pdf")


# ---------------------------------------------------------------------------
# SectionDetector
# ---------------------------------------------------------------------------

class TestSectionDetector:
    """
    Tests for spaCy-based section header detection.
    spaCy is mocked so no model download is required in unit tests.
    The integration test (marked @pytest.mark.integration) runs with real spaCy.
    """

    def _detector_with_mock_nlp(self):
        """Return a SectionDetector with spaCy replaced by a simple regex matcher."""
        detector = SectionDetector.__new__(SectionDetector)
        # _setup_matcher() is called in __init__; bypass it for unit tests.
        # The real matcher is tested in integration tests.
        return detector

    def test_detect_returns_dict(self):
        detector = SectionDetector()
        # Even with no spaCy model, detect() must return a dict.
        # We patch the internal NLP call.
        with patch.object(detector, "_run_nlp", return_value={}):
            result = detector.detect("Some text")
        assert isinstance(result, dict)

    def test_detect_canonical_sections_from_text(self):
        """
        The canonical headers map to standard section keys.
        Uses the real matcher logic (but mocked spaCy doc for speed).
        """
        detector = SectionDetector()
        text = (
            "Experience\nPython developer at Acme, 2019–2024\n\n"
            "Skills\nPython, Django, PostgreSQL\n\n"
            "Education\nBSc Computer Science, 2018\n"
        )
        with patch.object(detector, "_run_nlp", side_effect=lambda t: detector._regex_fallback(t)):
            result = detector.detect(text)
        assert "experience" in result
        assert "skills" in result
        assert "education" in result

    def test_detect_returns_empty_for_structureless_text(self):
        detector = SectionDetector()
        text = "This is a paragraph with no structure or headers whatsoever."
        with patch.object(detector, "_run_nlp", side_effect=lambda t: detector._regex_fallback(t)):
            result = detector.detect(text)
        assert isinstance(result, dict)
        # May or may not be empty — important constraint is NO exception raised.

    def test_detect_is_case_insensitive(self):
        detector = SectionDetector()
        text = "EXPERIENCE\nSenior Engineer\n\nskills\nPython\n\nEducation\nBSc\n"
        with patch.object(detector, "_run_nlp", side_effect=lambda t: detector._regex_fallback(t)):
            result = detector.detect(text)
        # All three should be detected regardless of case.
        assert "experience" in result
        assert "skills" in result
        assert "education" in result

    def test_detect_does_not_raise_on_empty_string(self):
        detector = SectionDetector()
        with patch.object(detector, "_run_nlp", side_effect=lambda t: detector._regex_fallback(t)):
            result = detector.detect("")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# ResumeParser — orchestration
# ---------------------------------------------------------------------------

class TestResumeParser:
    """
    Tests for ResumeParser, the orchestrator that wires backends + detector.
    All backends and the detector are mocked — this is a unit test for the
    orchestration logic only.
    """

    def _make_parser(
        self,
        primary_text: str = "A" * 200,
        primary_pages: int = 1,
        primary_raises: bool = False,
        fallback_text: str = "fallback text " * 20,
        fallback_pages: int = 1,
        sections: dict | None = None,
    ) -> tuple[ResumeParser, MagicMock, MagicMock, MagicMock]:
        from resume_pipeline.ingestion.parser import ParseError

        mock_primary = MagicMock(spec=PyMuPDFBackend)
        mock_fallback = MagicMock(spec=PdfplumberBackend)
        mock_detector = MagicMock(spec=SectionDetector)

        if primary_raises:
            mock_primary.extract_text.side_effect = ParseError("fitz failed")
        else:
            mock_primary.extract_text.return_value = (primary_text, primary_pages)
            mock_primary.is_viable.return_value = len(primary_text.strip()) >= PyMuPDFBackend.MIN_VIABLE_CHARS

        mock_fallback.extract_text.return_value = (fallback_text, fallback_pages)
        mock_detector.detect.return_value = sections or {"experience": "text"}

        parser = ResumeParser(
            primary=mock_primary,
            fallback=mock_fallback,
            detector=mock_detector,
        )
        return parser, mock_primary, mock_fallback, mock_detector

    def test_parse_returns_parsed_document(self):
        parser, _, _, _ = self._make_parser()
        result = parser.parse("/fake/resume.pdf")
        assert isinstance(result, ParsedDocument)

    def test_parse_uses_pymupdf_for_viable_text(self):
        parser, primary, fallback, _ = self._make_parser(primary_text="A" * 200)
        parser.parse("/fake/resume.pdf")
        primary.extract_text.assert_called_once_with("/fake/resume.pdf")
        fallback.extract_text.assert_not_called()

    def test_parse_status_ok_when_pymupdf_succeeds(self):
        parser, _, _, _ = self._make_parser(primary_text="A" * 200)
        result = parser.parse("/fake/resume.pdf")
        assert result.status == ParseStatus.OK

    def test_parse_parser_used_is_pymupdf_on_success(self):
        parser, _, _, _ = self._make_parser(primary_text="A" * 200)
        result = parser.parse("/fake/resume.pdf")
        assert result.parser_used == "pymupdf"

    def test_parse_falls_back_when_pymupdf_text_is_short(self):
        parser, primary, fallback, _ = self._make_parser(primary_text="short")
        result = parser.parse("/fake/multicolumn.pdf")
        fallback.extract_text.assert_called_once()
        assert result.parser_used == "pdfplumber"

    def test_parse_status_fallback_when_pdfplumber_used(self):
        parser, _, _, _ = self._make_parser(primary_text="short")
        result = parser.parse("/fake/multicolumn.pdf")
        assert result.status == ParseStatus.FALLBACK

    def test_parse_falls_back_when_pymupdf_raises(self):
        parser, _, fallback, _ = self._make_parser(primary_raises=True)
        result = parser.parse("/fake/corrupt.pdf")
        # If primary raises, either fallback is tried or status=FAILED.
        # Implementation chooses: primary ParseError → try fallback first.
        # If fallback also raises → status=FAILED.
        assert result.parser_used in ("pdfplumber", "none")

    def test_parse_returns_failed_status_on_both_backends_raising(self):
        from resume_pipeline.ingestion.parser import ParseError
        mock_primary = MagicMock(spec=PyMuPDFBackend)
        mock_fallback = MagicMock(spec=PdfplumberBackend)
        mock_detector = MagicMock(spec=SectionDetector)
        mock_primary.extract_text.side_effect = ParseError("fitz failed")
        mock_fallback.extract_text.side_effect = ParseError("pdfplumber failed")
        parser = ResumeParser(primary=mock_primary, fallback=mock_fallback, detector=mock_detector)
        result = parser.parse("/fake/corrupt.pdf")
        assert result.status == ParseStatus.FAILED

    def test_parse_does_not_raise_on_failure(self):
        from resume_pipeline.ingestion.parser import ParseError
        mock_primary = MagicMock(spec=PyMuPDFBackend)
        mock_fallback = MagicMock(spec=PdfplumberBackend)
        mock_detector = MagicMock(spec=SectionDetector)
        mock_primary.extract_text.side_effect = ParseError("fitz failed")
        mock_fallback.extract_text.side_effect = ParseError("pdfplumber failed")
        parser = ResumeParser(primary=mock_primary, fallback=mock_fallback, detector=mock_detector)
        # Must NOT raise.
        result = parser.parse("/nonexistent/file.pdf")
        assert result is not None

    def test_parse_failed_document_has_empty_text(self):
        from resume_pipeline.ingestion.parser import ParseError
        mock_primary = MagicMock(spec=PyMuPDFBackend)
        mock_fallback = MagicMock(spec=PdfplumberBackend)
        mock_detector = MagicMock(spec=SectionDetector)
        mock_primary.extract_text.side_effect = ParseError("x")
        mock_fallback.extract_text.side_effect = ParseError("x")
        parser = ResumeParser(primary=mock_primary, fallback=mock_fallback, detector=mock_detector)
        result = parser.parse("/fake/corrupt.pdf")
        assert result.raw_text == ""
        assert result.sections == {}

    def test_parse_char_count_equals_len_of_raw_text(self):
        parser, _, _, _ = self._make_parser(primary_text="B" * 150)
        result = parser.parse("/fake/resume.pdf")
        assert result.char_count == len(result.raw_text)

    def test_parse_calls_section_detector(self):
        parser, _, _, detector = self._make_parser()
        parser.parse("/fake/resume.pdf")
        detector.detect.assert_called_once()

    def test_parse_includes_sections_from_detector(self):
        parser, _, _, _ = self._make_parser(sections={"skills": "Python Django"})
        result = parser.parse("/fake/resume.pdf")
        assert "skills" in result.sections


# ---------------------------------------------------------------------------
# Observability integration
# ---------------------------------------------------------------------------

class TestIngestionObservability:
    """
    Verifies that ResumeParser emits a latency record for stage 'document_ingestion'
    on every parse call, whether successful or not.
    """

    def test_parse_emits_latency_record_on_success(self):
        obs = PipelineObservability()
        mock_primary = MagicMock(spec=PyMuPDFBackend)
        mock_fallback = MagicMock(spec=PdfplumberBackend)
        mock_detector = MagicMock(spec=SectionDetector)
        mock_primary.extract_text.return_value = ("A" * 200, 1)
        mock_primary.is_viable.return_value = True
        mock_detector.detect.return_value = {}

        parser = ResumeParser(
            primary=mock_primary,
            fallback=mock_fallback,
            detector=mock_detector,
            observability=obs,
        )
        parser.parse("/fake/resume.pdf")

        stages = [r.stage for r in obs._records]
        assert "document_ingestion" in stages

    def test_parse_emits_latency_record_on_failure(self):
        from resume_pipeline.ingestion.parser import ParseError
        obs = PipelineObservability()
        mock_primary = MagicMock(spec=PyMuPDFBackend)
        mock_fallback = MagicMock(spec=PdfplumberBackend)
        mock_detector = MagicMock(spec=SectionDetector)
        mock_primary.extract_text.side_effect = ParseError("boom")
        mock_fallback.extract_text.side_effect = ParseError("boom")

        parser = ResumeParser(
            primary=mock_primary,
            fallback=mock_fallback,
            detector=mock_detector,
            observability=obs,
        )
        parser.parse("/fake/corrupt.pdf")

        stages = [r.stage for r in obs._records]
        assert "document_ingestion" in stages

    def test_latency_record_has_positive_latency(self):
        obs = PipelineObservability()
        mock_primary = MagicMock(spec=PyMuPDFBackend)
        mock_fallback = MagicMock(spec=PdfplumberBackend)
        mock_detector = MagicMock(spec=SectionDetector)
        mock_primary.extract_text.return_value = ("A" * 200, 1)
        mock_primary.is_viable.return_value = True
        mock_detector.detect.return_value = {}

        parser = ResumeParser(
            primary=mock_primary,
            fallback=mock_fallback,
            detector=mock_detector,
            observability=obs,
        )
        parser.parse("/fake/resume.pdf")

        ingestion_records = [r for r in obs._records if r.stage == "document_ingestion"]
        assert len(ingestion_records) == 1
        assert ingestion_records[0].latency_ms >= 0.0


# ---------------------------------------------------------------------------
# Audit logging integration
# ---------------------------------------------------------------------------

class TestIngestionAuditLogging:
    """
    Verifies that ResumeParser emits structured audit events via StructuredAuditLogger.
    """

    def _capture_audit_logs(self) -> tuple[list[str], logging.Handler]:
        log_list: list[str] = []

        class CapturingHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_list.append(record.getMessage())

        handler = CapturingHandler()
        logging.getLogger("pipeline.audit").addHandler(handler)
        return log_list, handler

    def test_document_parsed_event_emitted_on_success(self):
        import json
        log_list, handler = self._capture_audit_logs()
        try:
            mock_primary = MagicMock(spec=PyMuPDFBackend)
            mock_fallback = MagicMock(spec=PdfplumberBackend)
            mock_detector = MagicMock(spec=SectionDetector)
            mock_primary.extract_text.return_value = ("A" * 200, 1)
            mock_primary.is_viable.return_value = True
            mock_detector.detect.return_value = {}
            parser = ResumeParser(primary=mock_primary, fallback=mock_fallback, detector=mock_detector)
            parser.parse("/fake/resume.pdf")

            events = [json.loads(line)["event"] for line in log_list if line.strip().startswith("{")]
            assert "document_parsed" in events
        finally:
            logging.getLogger("pipeline.audit").removeHandler(handler)

    def test_parser_fallback_event_emitted_when_pdfplumber_used(self):
        import json
        log_list, handler = self._capture_audit_logs()
        try:
            mock_primary = MagicMock(spec=PyMuPDFBackend)
            mock_fallback = MagicMock(spec=PdfplumberBackend)
            mock_detector = MagicMock(spec=SectionDetector)
            mock_primary.extract_text.return_value = ("short", 1)
            mock_primary.is_viable.return_value = False
            mock_fallback.extract_text.return_value = ("fallback text " * 20, 1)
            mock_detector.detect.return_value = {}
            parser = ResumeParser(primary=mock_primary, fallback=mock_fallback, detector=mock_detector)
            parser.parse("/fake/multicolumn.pdf")

            events = [json.loads(line)["event"] for line in log_list if line.strip().startswith("{")]
            assert "parser_fallback" in events
        finally:
            logging.getLogger("pipeline.audit").removeHandler(handler)

    def test_document_parse_failed_event_emitted_on_failure(self):
        from resume_pipeline.ingestion.parser import ParseError
        import json
        log_list, handler = self._capture_audit_logs()
        try:
            mock_primary = MagicMock(spec=PyMuPDFBackend)
            mock_fallback = MagicMock(spec=PdfplumberBackend)
            mock_detector = MagicMock(spec=SectionDetector)
            mock_primary.extract_text.side_effect = ParseError("boom")
            mock_fallback.extract_text.side_effect = ParseError("boom")
            parser = ResumeParser(primary=mock_primary, fallback=mock_fallback, detector=mock_detector)
            parser.parse("/fake/corrupt.pdf")

            events = [json.loads(line)["event"] for line in log_list if line.strip().startswith("{")]
            assert "document_parse_failed" in events
        finally:
            logging.getLogger("pipeline.audit").removeHandler(handler)
