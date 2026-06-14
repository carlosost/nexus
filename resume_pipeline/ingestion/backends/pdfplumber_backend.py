"""
M0.5 — Fallback PDF extraction backend using pdfplumber.

pdfplumber handles multi-column and table-heavy layouts that PyMuPDF mis-parses.
It is only invoked when PyMuPDFBackend.is_viable() returns False.
"""

from __future__ import annotations

# pdfplumber is imported lazily inside extract_text so that this module is
# importable before pdfplumber is installed, and so that unit tests can patch
# "pdfplumber.open" before it is actually called.
#   pip install pdfplumber

from resume_pipeline.ingestion.parser import ParseError


class PdfplumberBackend:
    """Extract plain text from a PDF using pdfplumber."""

    def extract_text(self, filepath: str) -> tuple[str, int]:
        """
        Open *filepath* with pdfplumber, join per-page text, return result.

        pdfplumber returns None for pages that have no extractable text (e.g.
        image-only pages). Those pages are skipped silently.

        Returns:
            (text, page_count) — text joined by newline, page_count = total pages.

        Raises:
            ParseError: if pdfplumber raises any exception.
        """
        try:
            import pdfplumber  # noqa: PLC0415 — lazy import by design
            with pdfplumber.open(filepath) as pdf:
                pages = [p.extract_text() for p in pdf.pages]
                page_count = len(pages)
                text = "\n".join(p for p in pages if p is not None)
                return text, page_count
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError(
                f"pdfplumber failed to parse '{filepath}': {exc}"
            ) from exc
