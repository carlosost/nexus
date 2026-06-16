"""
M0.5 — Document Ingestion: Core parser module.

Exports:
    ParseError      — raised by backends on unrecoverable extraction failure
    ParseStatus     — enum: ok | fallback_used | failed
    ParsedDocument  — dataclass holding extraction result
    ResumeParser    — orchestrates backends + section detector + observability
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from resume_pipeline.logging_module import audit_logger as _default_audit_logger
from resume_pipeline.observability import (
    PipelineObservability,
    pipeline_observability as _default_obs,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ParseError(Exception):
    """Raised by a backend when PDF extraction fails unrecoverably."""


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

class ParseStatus(str, Enum):
    OK       = "ok"
    FALLBACK = "fallback_used"   # pdfplumber was invoked after PyMuPDF yielded < 50 chars
    FAILED   = "failed"          # both backends failed; no exception propagated


@dataclass
class ParsedDocument:
    raw_text:    str
    sections:    dict[str, str]   # {"experience": "...", "skills": "..."}
    parser_used: str              # "pymupdf" | "pdfplumber" | "none"
    status:      ParseStatus
    page_count:  int
    char_count:  int


# ---------------------------------------------------------------------------
# ResumeParser
# ---------------------------------------------------------------------------

class ResumeParser:
    """
    Orchestrates PDF text extraction and section detection.

    Dependency-injectable for unit testing:

        parser = ResumeParser(
            primary=mock_primary,
            fallback=mock_fallback,
            detector=mock_detector,
            observability=fresh_obs,
        )

    Production usage (all defaults):

        parser = ResumeParser()
        doc = parser.parse("/uploads/resume.pdf")
    """

    def __init__(
        self,
        primary=None,
        fallback=None,
        detector=None,
        observability: Optional[PipelineObservability] = None,
        audit_logger=None,
    ) -> None:
        # Lazy-import concrete classes so the module is importable even before
        # optional deps (fitz, pdfplumber, spacy) are installed in the environment.
        if primary is None:
            from resume_pipeline.ingestion.backends.pymupdf_backend import PyMuPDFBackend
            primary = PyMuPDFBackend()
        if fallback is None:
            from resume_pipeline.ingestion.backends.pdfplumber_backend import PdfplumberBackend
            fallback = PdfplumberBackend()
        if detector is None:
            from resume_pipeline.ingestion.section_detector import SectionDetector
            detector = SectionDetector()

        self._primary = primary
        self._fallback = fallback
        self._detector = detector
        self._obs = observability or _default_obs
        self._audit = audit_logger or _default_audit_logger

        from resume_pipeline.ingestion.experience_extractor import ExperienceExtractor
        self._experience_extractor = ExperienceExtractor()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, filepath: str) -> ParsedDocument:
        """
        Parse a PDF at *filepath* and return a :class:`ParsedDocument`.

        Never raises — on failure returns a document with ``status=FAILED``
        and empty ``raw_text`` / ``sections``.

        Telemetry:
            - Latency recorded via ``self._obs.timed("document_ingestion")``
            - Audit events: ``document_ingestion_started``, then one of
              ``document_parsed`` / ``document_parse_failed``
            - ``parser_fallback`` audit event emitted when pdfplumber is used
              due to low char count from the primary backend
        """
        with self._obs.timed("document_ingestion"):
            self._audit.log_pipeline_stage_started(
                "document_ingestion", filepath=filepath
            )
            try:
                text, page_count, parser_used, status = self._extract(filepath)
                sections = self._detector.detect(text)
                exp_value, exp_source = self._experience_extractor.extract(sections)
                if exp_value is not None:
                    sections["total_experience_years"] = exp_value
                    self._audit.log_experience_years_extracted(
                        value=exp_value, source=exp_source
                    )
                doc = ParsedDocument(
                    raw_text=text,
                    sections=sections,
                    parser_used=parser_used,
                    status=status,
                    page_count=page_count,
                    char_count=len(text),
                )
                self._audit.log_document_parsed(
                    filepath=filepath,
                    parser_used=parser_used,
                    char_count=doc.char_count,
                    page_count=page_count,
                    status=status.value,
                )
                return doc
            except Exception as exc:
                self._audit.log_document_parse_failed(
                    filepath=filepath, error=str(exc)
                )
                return ParsedDocument(
                    raw_text="",
                    sections={},
                    parser_used="none",
                    status=ParseStatus.FAILED,
                    page_count=0,
                    char_count=0,
                )

    # ------------------------------------------------------------------
    # Internal extraction logic
    # ------------------------------------------------------------------

    def _extract(self, filepath: str) -> tuple[str, int, str, ParseStatus]:
        """
        Returns (text, page_count, parser_used, status).
        Raises the last :class:`ParseError` if both backends fail.
        """
        try:
            text, page_count = self._primary.extract_text(filepath)
            if self._primary.is_viable(text):
                return text, page_count, "pymupdf", ParseStatus.OK

            # Primary succeeded but char count is too low — fall back.
            self._audit.log_parser_fallback(
                primary="pymupdf",
                fallback="pdfplumber",
                reason="low_char_count",
            )
            text, page_count = self._fallback.extract_text(filepath)
            return text, page_count, "pdfplumber", ParseStatus.FALLBACK

        except ParseError:
            # Primary raised — try fallback before declaring failure.
            text, page_count = self._fallback.extract_text(filepath)
            return text, page_count, "pdfplumber", ParseStatus.FALLBACK
