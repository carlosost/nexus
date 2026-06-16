# M8 — Word Document (.doc / .docx) Resume Ingestion

## Goal

`POST /api/candidates/` currently accepts PDF resumes only. Extend it (backend
+ frontend) to also accept Microsoft Word documents — both legacy `.doc` and
modern `.docx`. A Word upload is converted server-side to PDF *before* it
enters the existing `ResumeParser` pipeline, so every downstream stage (PDF
parsing, section detection, Hard Gate, Semantic Match, Rubric Scoring) is
completely unaware that the original file wasn't a PDF.

## Decisions

* **Formats accepted:** `.doc` and `.docx` (in addition to existing `.pdf`).
* **Conversion engine:** LibreOffice headless (`soffice --headless --convert-to
  pdf`), invoked as a subprocess from a new, dependency-isolated module. No
  pure-Python library converts both legacy `.doc` (a binary OLE2 format) and
  `.docx` to PDF with real fidelity on Linux without shelling out to an office
  suite — `docx2pdf` requires MS Word/AppleScript (Windows/Mac only),
  `python-docx` can't render to PDF at all, and commercial libraries
  (Aspose) are non-free. LibreOffice headless is the de facto open-source
  standard for this exact problem and already runs in our Linux/Docker
  runtime.
* **API surface:** keep the existing multipart field name `resume_pdf` for
  backward compatibility with the frontend and existing tests — broaden its
  *accepted* extensions/content-types rather than renaming it.
* **Conversion failure handling:** a `WordConversionError` surfaces as a
  `400` with a field-level `resume_pdf` error — mirroring how malformed PDFs
  already degrade gracefully (empty `resume_parsed`) rather than crashing the
  request. Unlike the PDF case, a conversion failure IS a hard validation
  error (a `.docx` that LibreOffice can't open is not a resume we can score
  at all), so it's caught at `create()` time and raised as a
  `ValidationError`, not swallowed.
* **No async/Celery:** conversion runs synchronously inside the request,
  consistent with the rest of this pipeline (no task queue exists in this
  codebase yet). A 30-second subprocess timeout bounds worst-case latency.

## New module: `resume_pipeline/ingestion/word_converter.py`

```
WordConversionError(Exception)
convert_word_to_pdf(file_bytes: bytes, original_filename: str) -> bytes
```

* Writes `file_bytes` to a temp file preserving the original extension
  (LibreOffice needs a real file path — it can't read stdin).
* Shells out to `soffice --headless --convert-to pdf --outdir <tmpdir>
  <tmpfile>` via a `_run_soffice_conversion()` helper isolated exactly the
  way `job_embedder._call_embedding_api()` is isolated — so unit tests patch
  the subprocess call, never invoking real LibreOffice.
* Raises `WordConversionError` on: non-zero exit code, `TimeoutExpired`
  (30s), or a missing output PDF file after a "successful" exit.
* Always cleans up its temp directory, even on failure.

## Backend changes

* `resume_pipeline/serializers.py` — `CandidateCreateSerializer`:
  * `validate_resume_pdf`: extend allowed content-types
    (`application/msword`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`)
    and extensions (`.doc`, `.docx`); same 10 MB cap applies to the original
    upload.
  * `create()`: if the upload is a Word document, call
    `convert_word_to_pdf()` and feed the resulting PDF bytes into
    `ResumeParser.parse()` exactly where PDF bytes are fed in today; on
    `WordConversionError`, raise `serializers.ValidationError({"resume_pdf": ...})`.
* `Dockerfile` — add `libreoffice` to the runtime image's `apt-get install`
  list (next to `libpq5`, `curl`).

## Frontend changes

* `frontend/src/components/CandidateIngestionModal.jsx`:
  * `accept` attribute → `.pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  * Client-side extension check extended to `.pdf` / `.doc` / `.docx`.
  * Label copy: "Resume PDF" → "Resume (PDF or Word)".
* `frontend/src/api/client.js` — no functional change (already a generic
  multipart upload); docstring updated.

## Test plan

### Outer loop (BDD)

* `features/word_resume_ingestion.feature` — new scenarios:
  1. Valid `.docx` upload → converted → `201`, Candidate persisted.
  2. Valid `.doc` upload → converted → `201`, Candidate persisted.
  3. Word file LibreOffice can't convert → `400`, field error on
     `resume_pdf`, no Candidate row created.
  4. Conversion subprocess times out → `400`, graceful failure, no orphan
     Candidate row.
  5. Existing PDF upload path is unaffected (regression guard).
  6. Disallowed file type (e.g. `.txt`) still rejected with `400`.
  7. Oversized Word file (> 10 MB) still rejected before conversion is
     attempted (cheap rejection, no subprocess spawned).
* `features/steps/word_resume_ingestion_steps.py` — step definitions,
  mocked ORM + mocked `convert_word_to_pdf`, same pattern as
  `job_lifecycle_steps.py`.

### Inner loop (TDD, unit)

* `tests/unit/test_word_converter.py` — `convert_word_to_pdf()` in isolation:
  happy path, non-zero exit code, timeout, missing output file, temp-dir
  cleanup on both success and failure.
* `tests/unit/test_candidate_word_upload.py` — `CandidateCreateSerializer`
  in isolation: accepts `.docx`/`.doc` by extension and by content-type,
  still rejects unsupported types, calls `convert_word_to_pdf` only for
  Word uploads (never for PDF), surfaces `WordConversionError` as a 400
  under the `resume_pdf` key.

### Integration

* `tests/integration/test_word_resume_lifecycle.py` — real Django ORM
  against SQLite, `convert_word_to_pdf` mocked (no real LibreOffice
  required in CI/dev sandbox), `POST /api/candidates/` with `.docx` and
  `.doc` fixtures, asserts the Candidate row and `resume_parsed` exist.

### Frontend unit

* `frontend/src/__tests__/CandidateIngestionModal.test.jsx` — extend
  existing suite: accepts `.docx`/`.doc` selections, rejects unsupported
  extensions client-side, label reflects the new copy.

### E2E

* `frontend/e2e/word_resume_ingestion.spec.js` — Playwright, API mocked via
  `page.route()`: upload a `.docx` fixture → candidate appears in the list;
  upload a file that the (mocked) backend rejects with `400` → inline error
  shown; existing `.pdf` upload still works end-to-end (regression).

## Execution order

1. Outer BDD spec (`word_resume_ingestion.feature`) — red.
2. Inner unit tests (`test_word_converter.py`, `test_candidate_word_upload.py`) — red.
3. Implement `word_converter.py`, update `serializers.py`, update `Dockerfile`.
4. Step definitions for the feature file — green.
5. Integration test (`test_word_resume_lifecycle.py`).
6. Frontend: update `CandidateIngestionModal.jsx`, extend its unit test.
7. E2E spec (`word_resume_ingestion.spec.js`).
8. Verify: AST/syntax-check every new/changed file; confirm scenario count;
   confirm no regressions to the existing PDF-only test assertions.
