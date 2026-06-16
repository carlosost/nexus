"""
Inner-loop unit tests for resume_pipeline/ingestion/word_converter.py — M8.

These tests are written BEFORE the implementation exists (TDD red phase).
The LibreOffice subprocess call is fully mocked — no real `soffice` binary
is required to run this suite, in dev, CI, or this sandbox.

Run: pytest tests/unit/test_word_converter.py -m unit
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# convert_word_to_pdf — happy path
# ---------------------------------------------------------------------------

class TestConvertWordToPdfHappyPath:

    @pytest.fixture(autouse=True)
    def import_module(self):
        from resume_pipeline.ingestion import word_converter
        self.mod = word_converter

    def test_returns_pdf_bytes_on_success(self, tmp_path):
        fake_pdf_bytes = b"%PDF-1.4 fake pdf content"

        def fake_run(cmd, *args, **kwargs):
            # Locate the --outdir argument and write a fake output PDF there,
            # named after the input file with a .pdf extension — mirrors what
            # `soffice --headless --convert-to pdf` actually does on disk.
            outdir_idx = cmd.index("--outdir") + 1
            outdir = cmd[outdir_idx]
            input_path = cmd[-1]
            import os
            stem = os.path.splitext(os.path.basename(input_path))[0]
            with open(os.path.join(outdir, f"{stem}.pdf"), "wb") as f:
                f.write(fake_pdf_bytes)
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with patch.object(self.mod.subprocess, "run", side_effect=fake_run):
            result = self.mod.convert_word_to_pdf(b"fake docx bytes", "resume.docx")

        assert result == fake_pdf_bytes

    def test_works_for_legacy_doc_extension(self, tmp_path):
        fake_pdf_bytes = b"%PDF-1.4 legacy doc"

        def fake_run(cmd, *args, **kwargs):
            outdir_idx = cmd.index("--outdir") + 1
            outdir = cmd[outdir_idx]
            input_path = cmd[-1]
            import os
            stem = os.path.splitext(os.path.basename(input_path))[0]
            with open(os.path.join(outdir, f"{stem}.pdf"), "wb") as f:
                f.write(fake_pdf_bytes)
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with patch.object(self.mod.subprocess, "run", side_effect=fake_run):
            result = self.mod.convert_word_to_pdf(b"fake doc bytes", "resume.doc")

        assert result == fake_pdf_bytes

    def test_invokes_soffice_with_headless_convert_to_pdf(self):
        captured_cmd = {}

        def fake_run(cmd, *args, **kwargs):
            captured_cmd["cmd"] = cmd
            outdir_idx = cmd.index("--outdir") + 1
            outdir = cmd[outdir_idx]
            input_path = cmd[-1]
            import os
            stem = os.path.splitext(os.path.basename(input_path))[0]
            with open(os.path.join(outdir, f"{stem}.pdf"), "wb") as f:
                f.write(b"%PDF-1.4")
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with patch.object(self.mod.subprocess, "run", side_effect=fake_run):
            self.mod.convert_word_to_pdf(b"bytes", "resume.docx")

        cmd = captured_cmd["cmd"]
        assert "--headless" in cmd
        assert "--convert-to" in cmd
        assert "pdf" in cmd

    def test_cleans_up_temp_directory_on_success(self):
        created_dirs = []

        def fake_run(cmd, *args, **kwargs):
            outdir_idx = cmd.index("--outdir") + 1
            outdir = cmd[outdir_idx]
            created_dirs.append(outdir)
            input_path = cmd[-1]
            import os
            stem = os.path.splitext(os.path.basename(input_path))[0]
            with open(os.path.join(outdir, f"{stem}.pdf"), "wb") as f:
                f.write(b"%PDF-1.4")
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with patch.object(self.mod.subprocess, "run", side_effect=fake_run):
            self.mod.convert_word_to_pdf(b"bytes", "resume.docx")

        import os
        for d in created_dirs:
            assert not os.path.exists(d), f"Temp dir {d} was not cleaned up"


# ---------------------------------------------------------------------------
# convert_word_to_pdf — failure handling
# ---------------------------------------------------------------------------

class TestConvertWordToPdfFailures:

    @pytest.fixture(autouse=True)
    def import_module(self):
        from resume_pipeline.ingestion import word_converter
        self.mod = word_converter

    def test_nonzero_exit_code_raises_word_conversion_error(self):
        with patch.object(
            self.mod.subprocess,
            "run",
            return_value=MagicMock(returncode=1, stdout=b"", stderr=b"soffice: error"),
        ):
            with pytest.raises(self.mod.WordConversionError):
                self.mod.convert_word_to_pdf(b"corrupt bytes", "resume.docx")

    def test_timeout_raises_word_conversion_error(self):
        with patch.object(
            self.mod.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="soffice", timeout=30),
        ):
            with pytest.raises(self.mod.WordConversionError):
                self.mod.convert_word_to_pdf(b"bytes", "resume.docx")

    def test_missing_output_file_after_success_exit_raises(self):
        # soffice reports success but never actually writes the output file —
        # must not be silently treated as success.
        with patch.object(
            self.mod.subprocess,
            "run",
            return_value=MagicMock(returncode=0, stdout=b"", stderr=b""),
        ):
            with pytest.raises(self.mod.WordConversionError):
                self.mod.convert_word_to_pdf(b"bytes", "resume.docx")

    def test_cleans_up_temp_directory_on_failure(self):
        created_dirs = []

        def fake_run(cmd, *args, **kwargs):
            outdir_idx = cmd.index("--outdir") + 1
            created_dirs.append(cmd[outdir_idx])
            return MagicMock(returncode=1, stdout=b"", stderr=b"boom")

        with patch.object(self.mod.subprocess, "run", side_effect=fake_run):
            with pytest.raises(self.mod.WordConversionError):
                self.mod.convert_word_to_pdf(b"bytes", "resume.docx")

        import os
        for d in created_dirs:
            assert not os.path.exists(d), f"Temp dir {d} was not cleaned up"

    def test_error_message_is_informative(self):
        with patch.object(
            self.mod.subprocess,
            "run",
            return_value=MagicMock(returncode=1, stdout=b"", stderr=b"soffice: cannot open file"),
        ):
            with pytest.raises(self.mod.WordConversionError) as exc_info:
                self.mod.convert_word_to_pdf(b"bytes", "resume.docx")
        assert "resume.docx" in str(exc_info.value) or "convert" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# is_word_document — extension / content-type detection helper
# ---------------------------------------------------------------------------

class TestIsWordDocument:

    @pytest.fixture(autouse=True)
    def import_module(self):
        from resume_pipeline.ingestion import word_converter
        self.mod = word_converter

    def _file(self, name: str, content_type: str):
        f = MagicMock()
        f.name = name
        f.content_type = content_type
        return f

    def test_docx_extension_is_word(self):
        f = self._file("resume.docx", "application/octet-stream")
        assert self.mod.is_word_document(f) is True

    def test_doc_extension_is_word(self):
        f = self._file("resume.doc", "application/octet-stream")
        assert self.mod.is_word_document(f) is True

    def test_docx_content_type_is_word(self):
        f = self._file("upload.bin", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert self.mod.is_word_document(f) is True

    def test_doc_content_type_is_word(self):
        f = self._file("upload.bin", "application/msword")
        assert self.mod.is_word_document(f) is True

    def test_pdf_is_not_word(self):
        f = self._file("resume.pdf", "application/pdf")
        assert self.mod.is_word_document(f) is False

    def test_unrelated_type_is_not_word(self):
        f = self._file("resume.txt", "text/plain")
        assert self.mod.is_word_document(f) is False
