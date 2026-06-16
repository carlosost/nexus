"""
M8 — Word (.doc / .docx) → PDF conversion via LibreOffice headless.

Why LibreOffice headless and not a pure-Python library:

  Legacy `.doc` is a binary OLE2 format and `.docx` is a zipped XML format —
  rendering either to a faithful PDF requires a real layout engine, not just
  a file-format reader. `python-docx` only reads/writes `.docx` structure,
  it cannot rasterize/paginate to PDF. `docx2pdf` shells out to either MS
  Word (Windows) or AppleScript-driven Word (macOS) — neither exists on a
  headless Linux container. Commercial options (Aspose.Words) require a
  paid license to remove watermarking. LibreOffice headless
  (`soffice --headless --convert-to pdf`) is the standard, free, scriptable
  answer to this exact problem on Linux, and is what `unoconv` and similar
  "Python libraries" wrap internally anyway — so we call it directly via
  `subprocess` instead of adding an indirection layer with the same
  dependency.

This module mirrors the existing ingestion backend pattern
(`pymupdf_backend.py` / `pdfplumber_backend.py`): the subprocess call is
isolated in its own function so unit tests can patch `subprocess.run`
without ever invoking a real `soffice` binary.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

#: Word extensions accepted for conversion.
WORD_EXTENSIONS = (".doc", ".docx")

#: Word content-types accepted for conversion.
WORD_CONTENT_TYPES = {
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

#: Hard ceiling on conversion time — protects the request from a hung
#: LibreOffice process (e.g. a corrupt file that triggers an internal hang).
CONVERSION_TIMEOUT_SECONDS = 30


class WordConversionError(Exception):
    """Raised when a Word document cannot be converted to PDF."""


def is_word_document(file) -> bool:
    """
    True if *file* (a Django UploadedFile-like object exposing `.name` and
    `.content_type`) looks like a Word document by extension or content-type.
    """
    name = getattr(file, "name", "") or ""
    content_type = getattr(file, "content_type", "") or ""
    return name.lower().endswith(WORD_EXTENSIONS) or content_type in WORD_CONTENT_TYPES


def _run_soffice_conversion(input_path: str, outdir: str) -> subprocess.CompletedProcess:
    """
    Isolated subprocess invocation — patched directly in unit tests via
    `patch.object(word_converter.subprocess, "run", ...)` so no real
    LibreOffice installation is required to exercise this module's logic.
    """
    cmd = [
        "soffice",
        "--headless",
        "--norestore",
        "--convert-to",
        "pdf",
        "--outdir",
        outdir,
        input_path,
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        timeout=CONVERSION_TIMEOUT_SECONDS,
    )


def convert_word_to_pdf(file_bytes: bytes, original_filename: str) -> bytes:
    """
    Convert a Word document's raw bytes to PDF bytes using LibreOffice
    headless.

    LibreOffice needs a real file on disk (it cannot read from stdin), so
    *file_bytes* is written to a temp file preserving the original
    extension, converted into a sibling temp directory, then read back.
    The whole temp directory is always cleaned up, success or failure.

    Args:
        file_bytes: raw bytes of the uploaded .doc/.docx file.
        original_filename: the upload's original filename — only its
            extension is used, to give LibreOffice the right format hint.

    Returns:
        PDF bytes.

    Raises:
        WordConversionError: on a non-zero soffice exit code, a timeout, or
            a missing output file despite a "successful" exit code.
    """
    ext = os.path.splitext(original_filename)[1].lower() or ".docx"
    tmpdir = tempfile.mkdtemp(prefix="word_convert_")

    try:
        input_path = os.path.join(tmpdir, f"input{ext}")
        with open(input_path, "wb") as f:
            f.write(file_bytes)

        try:
            result = _run_soffice_conversion(input_path, tmpdir)
        except subprocess.TimeoutExpired as exc:
            raise WordConversionError(
                f"Conversion of '{original_filename}' timed out after "
                f"{CONVERSION_TIMEOUT_SECONDS}s."
            ) from exc

        if result.returncode != 0:
            stderr = getattr(result, "stderr", b"") or b""
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            raise WordConversionError(
                f"Could not convert '{original_filename}' to PDF "
                f"(soffice exited with code {result.returncode}): {stderr}".strip()
            )

        output_path = os.path.join(tmpdir, "input.pdf")
        if not os.path.exists(output_path):
            raise WordConversionError(
                f"Conversion of '{original_filename}' reported success but "
                "produced no output PDF."
            )

        with open(output_path, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
