"""
M0.5 — Primary PDF extraction backend using PyMuPDF (fitz).

PyMuPDF is the fastest, most reliable parser for standard (clean-layout) PDFs.
If extraction yields fewer than MIN_VIABLE_CHARS characters after stripping
whitespace, ResumeParser will automatically fall back to PdfplumberBackend.
"""

from __future__ import annotations

# fitz (PyMuPDF) is imported lazily inside extract_text so that this module
# is importable in environments where pymupdf is not yet installed, and so that
# unit tests can patch "fitz.open" before fitz is actually called.
#   pip install pymupdf

from resume_pipeline.ingestion.parser import ParseError


class PyMuPDFBackend:
    """Extract plain text from a PDF using PyMuPDF (fitz)."""

    MIN_VIABLE_CHARS: int = 50

    def extract_text(self, filepath: str) -> tuple[str, int]:
        """
        Open *filepath* with fitz, concatenate page text, close the document.

        Returns:
            (text, page_count) — joined by newline, page count as int.

        Raises:
            ParseError: if fitz raises any exception.
        """
        try:
            import fitz  # noqa: PLC0415 — lazy import by design
            doc = fitz.open(filepath)
            try:
                pages = [page.get_text() for page in doc]
                page_count = len(doc)
                text = "\n".join(pages)
                return text, page_count
            finally:
                doc.close()
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError(
                f"PyMuPDF failed to parse '{filepath}': {exc}"
            ) from exc

    def is_viable(self, text: str) -> bool:
        """
        Return True iff the extracted text has at least MIN_VIABLE_CHARS
        non-whitespace characters. Whitespace-only extraction signals a
        scanned image PDF or multi-column layout that fitz cannot parse.
        """
        return len(text.strip()) >= self.MIN_VIABLE_CHARS
