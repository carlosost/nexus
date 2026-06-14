# Carlos

evaluate built plan bellow:

```markdown
# Execution Plan V2 — Resume Evaluation Pipeline
# PATCH DOCUMENT — builds on EXECUTION_PLAN.md without overwriting it

> **Version:** 2.0 | **Author:** Principal Staff Engineer | **Date:** 2026-06-13
> **Hard Deadline:** 2026-06-19 (6 days from today)
> **Status baseline:** M1 ✅ M2 ✅ M3 ✅(mock-LLM) M4 ✅ M5 ✅ M6 ✅

---

## What Changed From V1

| # | Change | Reason |
|---|--------|--------|
| 1 | **Added M0.5** — Document Ingestion (PyMuPDF + spaCy) | PDF text extraction was missing; downstream stages assumed pre-parsed JSON |
| 2 | **Added M0.6** — Database Seeding (1 Job + 3 Candidates) | App must be demonstrable on `docker compose up` with no manual setup |
| 3 | **Fixed dependency order** | V1 had M4 (Orchestrator) before M3 (Rubric), which is logically impossible — the Orchestrator calls `RubricEvaluator.evaluate()`, so M3 must be production-ready first |
| 4 | **Upgraded M3** — Real LLM integration | `MockLLMBackend` is test-only; production needs OpenAI/Anthropic with `instructor` + Pydantic schema + `tenacity` retry |
| 5 | **Telemetry contract** explicit per milestone | V1 mentioned observability only in M2/M3; V2 mandates `@obs.instrument` + `audit_logger` hooks for **every** stage including ingestion |

### Corrected Priority Order (V2)

```
M0.5 Ingestion → M0.6 Seeding → M1 Hard Gate → M2 Semantic Match
  → M3 Rubric (real LLM) → M4 Orchestrator → M5 API → M6 UI
```

V1 had: `M1 → M2 → M4 → M5 → M3 → M6` ← M4 before M3 was a structural error.

---

## Deadline Schedule (June 13–19)

| Day | Milestone | Time-box | Status |
|-----|-----------|----------|--------|
| Jun 13 | **M0.5** — Document Ingestion | 8 h | 🔴 Not started |
| Jun 14 AM | **M0.6** — Database Seeding | 4 h | 🔴 Not started |
| Jun 14 PM–15 | **M3 (update)** — Real LLM + Pydantic/Instructor | 8 h | 🟡 Mock done; needs upgrade |
| Jun 15 PM | **M4 (re-verify)** — Orchestrator wires real M3 | 2 h | 🟡 Done with mock; re-verify with real |
| Jun 16 | **Integration** — Full pipeline smoke test, Docker | 8 h | 🔴 Not started |
| Jun 17 | **Hardening** — Error paths, retry limits, logging completeness | 6 h | 🔴 Not started |
| Jun 18 | **QA + Demo prep** — Seed data verified, Cypress e2e clean | 6 h | 🔴 Not started |
| Jun 19 | **Buffer + Delivery** — Final build, tag v1.0.0 | — | deadline |

---

## Methodology Contract (All Milestones)

### Double-Loop TDD — Strict

```
Step 1  Write Gherkin scenario → pytest-bdd FAILS (no step definitions)
Step 2  Write step definition stubs → scenario FAILS (no implementation)
Step 3  Write inner unit test → pytest FAILS (no module)
Step 4  Write minimal production code → inner test GREEN
Step 5  Iterate until outer BDD scenario GREEN
Step 6  Refactor under green
```

**No production code may be written before Steps 1–3 produce red.**
This applies to every milestone including M0.5, M0.6, and the M3 upgrade.

### Telemetry Contract (Non-Negotiable)

Every pipeline stage must satisfy both of these:

**Observability (latency):**
```python
# For class-level stages — instrument at construction time
self.evaluate = pipeline_observability.instrument("stage_name")(self._evaluate_impl)

# For function-level stages — use context manager
with pipeline_observability.timed("document_ingestion"):
    result = backend.extract_text(filepath)
```

**Audit logging (state transitions):**
```python
# On stage entry
audit_logger.log_pipeline_stage_started(stage="document_ingestion", application_id=...)

# On stage exit
audit_logger.log_pipeline_stage_completed(stage="document_ingestion", status=..., latency_ms=...)

# On fallback
audit_logger.log_parser_fallback(primary="pymupdf", fallback="pdfplumber", reason=...)

# On failure
audit_logger.log_document_parse_failed(filepath=..., error=str(e))
```

Assertion in every test suite: `caplog` / `_AuditCapturingHandler` confirms events were emitted.

---

## Milestone 0 — Toolchain & Docker Scaffolding ✅

*(Unchanged from V1. Assumed complete.)*

Add to `requirements.txt` for V2 additions:
```
pymupdf>=1.23.0          # fitz — primary PDF parser
spacy>=3.7.0             # section header detection
pdfplumber>=0.10.0       # fallback for multi-column layouts
instructor>=0.6.0        # Pydantic-enforced LLM structured output
tenacity>=8.2.0          # retry logic for LLM API calls
factory-boy>=3.3.0       # model factories for M0.6 seeding
```

---

## Milestone 0.5 — Document Ingestion Pipeline 🔴 NEW

**Goal:** Convert raw PDF/text resume files into structured, section-labelled JSON before any pipeline stage consumes them. No downstream stage should ever receive raw bytes or unstructured text.

**Time-box:** 8 hours (June 13)
**Fallback:** If spaCy section detection is incomplete by hour 6, ship regex-based section splitter and file a tech-debt ticket. PyMuPDF extraction is non-negotiable.

### Module Layout

```
resume_pipeline/ingestion/
  __init__.py
  parser.py              # ResumeParser — orchestrates backends + detector
  backends/
    __init__.py
    pymupdf_backend.py   # primary: fitz.open() → page.get_text()
    pdfplumber_backend.py  # fallback: multi-column, table-heavy layouts
  section_detector.py    # spaCy NLP → maps headings to canonical sections
```

### Key Data Contracts

```python
class ParseStatus(str, Enum):
    OK           = "ok"
    FALLBACK     = "fallback_used"   # pdfplumber was invoked
    FAILED       = "failed"          # unrecoverable error, no exception raised

@dataclass
class ParsedDocument:
    raw_text:    str
    sections:    dict[str, str]   # {"experience": "...", "skills": "..."}
    parser_used: str              # "pymupdf" | "pdfplumber"
    status:      ParseStatus
    page_count:  int
    char_count:  int
```

### Fallback Trigger

`PyMuPDFBackend.MIN_VIABLE_CHARS = 50`. If extracted text has fewer characters after stripping whitespace, `ResumeParser` silently falls back to `PdfplumberBackend`, emits a `parser_fallback` audit event, and sets `status = ParseStatus.FALLBACK`.

### Outer Loop — BDD Specification

Write `features/document_ingestion.feature` (see full file below in this document).

Run `pytest features/document_ingestion.feature` → **RED** (no step definitions). Correct.

### Inner Loop — Unit Tests

Write `tests/unit/test_ingestion.py` (see first failing tests below in this document).

Tests to cover:
- `PyMuPDFBackend.extract_text()` returns `(str, int)` — text + page count
- `PyMuPDFBackend.is_viable(text)` returns `False` for text with < 50 chars
- `PdfplumberBackend.extract_text()` returns non-empty string for multi-column fixture
- `SectionDetector.detect(text)` returns dict with canonical section keys
- `SectionDetector` returns empty dict for text with no recognisable headers — no crash
- `ResumeParser.parse()` uses PyMuPDF by default
- `ResumeParser.parse()` falls back to pdfplumber when PyMuPDF returns < 50 chars
- `ResumeParser.parse()` returns `status=FAILED` (not exception) on corrupted file
- `ParsedDocument.char_count` equals `len(raw_text)`
- Observability: `pipeline_observability._records` contains `stage="document_ingestion"` after parse
- Audit: `parser_fallback` event emitted when fallback is triggered
- Audit: `document_parse_failed` event emitted on parse failure

Run `pytest tests/unit/test_ingestion.py` → **RED** (`ModuleNotFoundError: resume_pipeline.ingestion`). Correct.

### Implementation Order

1. `resume_pipeline/ingestion/backends/pymupdf_backend.py` — `PyMuPDFBackend`
2. `resume_pipeline/ingestion/backends/pdfplumber_backend.py` — `PdfplumberBackend`
3. `resume_pipeline/ingestion/section_detector.py` — `SectionDetector` (spaCy matcher)
4. `resume_pipeline/ingestion/parser.py` — `ResumeParser` wiring both backends + detector
5. `features/steps/ingestion_steps.py` — step definitions (drives outer loop GREEN)

### Telemetry Integration

```python
class ResumeParser:
    def parse(self, filepath: str) -> ParsedDocument:
        with pipeline_observability.timed("document_ingestion"):
            audit_logger.log_pipeline_stage_started("document_ingestion", filepath=filepath)
            try:
                text, page_count = self._primary.extract_text(filepath)
                parser_used = "pymupdf"
                if not self._primary.is_viable(text):
                    audit_logger.log_parser_fallback("pymupdf", "pdfplumber", "low_char_count")
                    text, page_count = self._fallback.extract_text(filepath)
                    parser_used = "pdfplumber"
                    status = ParseStatus.FALLBACK
                else:
                    status = ParseStatus.OK
                sections = self._detector.detect(text)
                doc = ParsedDocument(raw_text=text, sections=sections,
                                     parser_used=parser_used, status=status,
                                     page_count=page_count, char_count=len(text))
                audit_logger.log_pipeline_stage_completed("document_ingestion", status=status)
                return doc
            except Exception as e:
                audit_logger.log_document_parse_failed(filepath=filepath, error=str(e))
                return ParsedDocument(raw_text="", sections={}, parser_used="none",
                                      status=ParseStatus.FAILED, page_count=0, char_count=0)
```

**Exit criterion:** All unit tests green. All BDD scenarios green. `coverage report` > 90% on `ingestion/`.

---

## Milestone 0.6 — Database Seeding 🔴 NEW

**Goal:** `python manage.py seed_demo` populates the database with 1 Job + 3 Candidates so reviewers can demo the full pipeline with zero manual data entry on first boot.

**Time-box:** 4 hours (June 14 AM)
**Fallback:** If management command is complex, ship a `fixtures/demo.json` Django fixture and `loaddata` in the Dockerfile entrypoint.

### Seed Data Spec

**Job — "Senior Backend Engineer":**
```python
Job(
    title="Senior Backend Engineer",
    requirements_raw={
        "required_skills": ["Python", "Django", "PostgreSQL", "REST APIs"],
        "preferred_skills": ["Redis", "Docker", "Kubernetes"],
        "minimum_experience_years": 5,
    },
    must_haves={
        "min_experience": {"type": "years_experience", "minimum_years": 5},
        "python_required": {"type": "keyword_presence",
                            "keywords": ["Python"], "sections": ["skills", "experience"]},
        "django_required": {"type": "keyword_presence",
                            "keywords": ["Django"], "sections": ["skills", "experience"]},
    },
)
```

**Candidate A — Strong Match** (gate: pass, expected high score):
Resume sections include 7 years Python/Django, AWS cert, measurable impact statements.

**Candidate B — Borderline** (gate: pass, expected mid score):
4.9 years experience (rounds to pass), Python present, Django absent → gate UNKNOWN on Django keyword.

**Candidate C — Hard Fail** (gate: fail, final score: 0.0):
2 years experience only. No Django keyword. Resume seeded to trigger short-circuit.

### Outer Loop — BDD Specification

`features/database_seeding.feature`:
- Running `seed_demo` creates exactly 1 Job record
- Running `seed_demo` creates exactly 3 Candidate records
- Running `seed_demo` twice is idempotent (no duplicates)
- Candidate C has gate outcome `fail` when evaluated
- Candidate A has final score > 0.70 when pipeline runs

### Inner Loop — Unit Tests

`tests/unit/test_seed_data.py`:
- Factory-boy factories produce valid model instances
- `CandidateFactory.build()` passes Django model validation
- `JobFactory.must_haves` validates against `HardGateEvaluator`
- Seed data YAML/fixture is valid JSON (parse test, no DB required)

### Telemetry Integration

Seed command emits a single structured log line on completion:
```json
{"ts": "...", "event": "demo_seed_completed",
 "jobs_created": 1, "candidates_created": 3, "idempotent": false}
```

**Exit criterion:** `python manage.py seed_demo && pytest tests/integration/test_seed.py` green.

---

## Milestone 1 — Hard Gate ✅ COMPLETE

*(No changes from V1. All tests green. See `features/hard_gate.feature`, `tests/unit/test_hard_gate.py`.)*

**Telemetry status:** `audit_logger.log_gate_transition()` implemented. ✅

---

## Milestone 2 — Semantic Match & Hybrid Search ✅ COMPLETE

*(No changes from V1. All tests green.)*

**Telemetry status:** `@pipeline_observability.instrument("semantic_match")` wraps `SemanticMatchEvaluator.evaluate()`. ✅

---

## Milestone 3 — Rubric Scoring 🟡 UPGRADE REQUIRED

**Current state:** Fully implemented with `MockLLMBackend`. All unit + BDD tests green.
**Required upgrade:** Replace `MockLLMBackend` with real LLM backend using `instructor` + Pydantic schema enforcement + `tenacity` retry logic.

**Time-box:** 8 hours (June 14 PM – June 15)
**Fallback:** If Anthropic/OpenAI API is unavailable in the deployment environment, `LLMBackendProtocol` means `MockLLMBackend` drops back in with zero orchestrator changes. Gate the swap on an env var: `LLM_BACKEND=openai|anthropic|mock`.

### What Changes in M3

Only `resume_pipeline/pipeline/rubric_score.py` is modified. `RubricEvaluatorProtocol`, `RubricResult`, orchestrator, API, and UI are **untouched**.

### Pydantic Schema (replaces raw JSON parsing)

```python
from pydantic import BaseModel, Field, model_validator

class RubricScoreResponse(BaseModel):
    """Strict schema enforced by instructor on every LLM call."""
    scores: dict[str, int] = Field(
        description="Raw scores 1-5 for each criterion"
    )
    justifications: dict[str, str] = Field(
        description="Per-criterion evidence citation from the resume"
    )

    @model_validator(mode="after")
    def validate_criteria(self) -> "RubricScoreResponse":
        required = {"core_skills", "relevant_experience",
                    "scope_impact", "domain_alignment", "education_certs"}
        missing = required - set(self.scores.keys())
        if missing:
            raise ValueError(f"Missing criteria in scores: {missing}")
        for k, v in self.scores.items():
            if not (1 <= v <= 5):
                raise ValueError(f"Score for '{k}' must be 1-5, got {v}")
        return self
```

### Real LLM Backends

```python
class OpenAIRubricBackend:
    """
    Uses instructor.from_openai() to enforce RubricScoreResponse schema.
    Retries on RateLimitError and APITimeoutError with exponential backoff.
    """
    def __init__(self, model: str = "gpt-4o-mini", max_retries: int = 3):
        import instructor, openai
        self._client = instructor.from_openai(openai.OpenAI())
        self._model = model
        self._max_retries = max_retries

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=20),
        retry=tenacity.retry_if_exception_type(
            (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)
        ),
        reraise=True,
    )
    def complete(self, system_prompt: str, user_prompt: str) -> RubricScoreResponse:
        return self._client.chat.completions.create(
            model=self._model,
            response_model=RubricScoreResponse,
            max_retries=self._max_retries,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

    @property
    def model_name(self) -> str:
        return self._model


class AnthropicRubricBackend:
    """Drop-in alternative. Uses instructor.from_anthropic()."""
    def __init__(self, model: str = "claude-haiku-4-5-20251001", max_retries: int = 3):
        import instructor, anthropic
        self._client = instructor.from_anthropic(anthropic.Anthropic())
        self._model = model
        self._max_retries = max_retries

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=20),
        retry=tenacity.retry_if_exception_type(Exception),
        reraise=True,
    )
    def complete(self, system_prompt: str, user_prompt: str) -> RubricScoreResponse:
        return self._client.messages.create(
            model=self._model,
            response_model=RubricScoreResponse,
            max_tokens=1024,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
        )

    @property
    def model_name(self) -> str:
        return self._model
```

### Backend Factory (env-var driven)

```python
def make_rubric_backend(backend: str | None = None) -> LLMBackendProtocol:
    """
    Instantiates the correct backend based on LLM_BACKEND env var.
    Allows zero-change swapping between providers and mock.
    """
    backend = backend or os.environ.get("LLM_BACKEND", "mock")
    if backend == "openai":
        return OpenAIRubricBackend(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    if backend == "anthropic":
        return AnthropicRubricBackend(model=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"))
    return MockLLMBackend("")  # test / offline environments
```

### New Inner-Loop Unit Tests (M3 Upgrade)

Add to `tests/unit/test_rubric.py`:
- `RubricScoreResponse` raises `ValidationError` when criterion score is 0 (below 1)
- `RubricScoreResponse` raises `ValidationError` when criterion score is 6 (above 5)
- `RubricScoreResponse` raises `ValidationError` when a required criterion is absent
- `make_rubric_backend("openai")` returns an instance satisfying `LLMBackendProtocol`
- `make_rubric_backend("anthropic")` returns an instance satisfying `LLMBackendProtocol`
- `make_rubric_backend("mock")` returns `MockLLMBackend`
- `OpenAIRubricBackend.complete()` retries on `RateLimitError` (mock the openai client)
- After 3 retries, exception propagates (tenacity reraise=True)

### Telemetry Integration (upgrade)

Add `model_name` to every `StructuredAuditLogger.log_score_computed()` call:
```python
audit_logger.log_score_computed(
    application_id=...,
    normalized_score=result.normalized_score,
    evidence_quality=result.evidence_quality,
    model_name=self._llm.model_name,  # ← new field
    retry_count=...,                   # ← new field (from tenacity stats)
)
```

**Exit criterion:** `LLM_BACKEND=mock pytest` fully green. `LLM_BACKEND=openai pytest -m integration` green against real API (CI uses OPENAI_API_KEY secret).

---

## Milestone 4 — Pipeline Orchestration 🟡 RE-VERIFY REQUIRED

**Current state:** Complete with `StubRubricEvaluator`. Must be re-verified once M3 real LLM backend is live.

**Time-box:** 2 hours (June 15 PM) — re-verification only, no new implementation.
**Fallback:** None needed. `RubricEvaluatorProtocol` structural subtyping means `StubRubricEvaluator` and `RubricEvaluator` are interchangeable. If real M3 is not ready, orchestrator stays on stub for demo — functionally complete.

### Re-verification Checklist

- [ ] Replace `StubRubricEvaluator` with `RubricEvaluator(make_rubric_backend())` in integration test
- [ ] Run `pytest tests/unit/test_pipeline.py` — all 42 tests green (no changes expected)
- [ ] Run `LLM_BACKEND=openai pytest tests/integration/test_orchestrator_integration.py -m integration`
- [ ] Confirm `stages_executed` includes `["hard_gate", "semantic_match", "rubric"]` for pass path
- [ ] Confirm `model_name` appears in audit log for rubric stage

**Exit criterion:** Integration test with real LLM green. Zero regressions in unit tests.

---

## Milestone 5 — Human-in-the-Loop API ✅ COMPLETE

*(No changes from V1. All tests green.)*

**Telemetry status:** `audit_logger.log_human_override()` implemented. ✅
**Remaining:** Add `model_name` and `retry_count` to `ApplicationScoreSerializer` output (non-breaking field addition, 30 min).

---

## Milestone 6 — Human-in-the-Loop UI ✅ COMPLETE

*(No changes from V1. All React components and Cypress e2e tests complete.)*

---

## Milestone 7 — Integration & Demo Hardening 🔴 NEW

**Goal:** Full pipeline runs end-to-end from PDF upload → parsed resume → gate → semantic → rubric → final score → API → UI. No mocks in the hot path.

**Time-box:** 8 hours (June 16)
**Fallback:** If full e2e is unstable, demo the pipeline in two halves (ingestion → DB, then DB → UI) and fix integration offline.

### Tasks

- [ ] Docker Compose: add `python manage.py seed_demo` to entrypoint
- [ ] `tests/integration/test_full_pipeline.py` — end-to-end with real PDF fixture + real LLM (marked `@pytest.mark.integration @pytest.mark.slow`)
- [ ] Smoke test script: `scripts/smoke_test.sh` — curl the score API, assert HTTP 200
- [ ] `LLM_BACKEND` env var threaded through Docker Compose
- [ ] Verify `pipeline.audit` log output in Docker logs (structured JSON lines)
- [ ] `pytest --cov --cov-report=html` — generate coverage report, confirm > 85% project-wide

### Telemetry Completeness Audit

Confirm every stage emits both a latency record and an audit event:

| Stage | `@instrument` / `timed()` | Audit event |
|-------|--------------------------|-------------|
| document_ingestion | `timed("document_ingestion")` | `document_parsed` / `parser_fallback` / `document_parse_failed` |
| hard_gate | `timed("hard_gate")` | `gate_transition` × N criteria |
| semantic_match | `instrument("semantic_match")` | — (latency only; no state transition) |
| rubric | `instrument("rubric")` | `score_computed` |
| final_score | `timed("final_score")` | `pipeline_short_circuited` (on FAIL) or `score_computed` |
| human_review | — (sync HTTP) | `human_override` |

**Exit criterion:** `scripts/smoke_test.sh` exits 0. Docker Compose brings up a working app in < 60 s from cold start.

---

## Architecture Constraints (V2 Additions)

*(All V1 constraints remain unchanged and non-negotiable.)*

| Constraint | V2 Decision |
|---|---|
| PDF parsing primary | `PyMuPDF` (fitz) — fastest, most reliable for clean layouts |
| PDF parsing fallback | `pdfplumber` — triggered only when `char_count < 50` after PyMuPDF extraction |
| Section detection | `spaCy` `PhraseMatcher` over canonical header list — not LLM |
| LLM schema enforcement | `instructor` + Pydantic `BaseModel` — no raw JSON parsing in production |
| LLM retry | `tenacity` with exponential backoff — max 3 attempts, reraise after exhaustion |
| LLM backend selection | `LLM_BACKEND` env var: `openai` \| `anthropic` \| `mock` |
| Demo data | 1 Job + 3 Candidates seeded by `manage.py seed_demo` — idempotent |
| Dependency order | M3 (Rubric) strictly before M4 (Orchestrator) |

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| spaCy model download blocked in CI | Medium | Medium | Bundle `en_core_web_sm` in Docker image; pin version |
| OpenAI rate limit during integration tests | High | Low | `LLM_BACKEND=mock` for unit/BDD; real calls only in `@pytest.mark.integration` |
| pdfplumber import collision with PyMuPDF | Low | Low | Isolated in `PdfplumberBackend` class; not imported at module level |
| tenacity exhaustion in demo | Low | High | Demo uses seed data with cached embeddings; LLM call only needed once per candidate |
| June 19 deadline slip | Medium | High | M0.5 and M3-upgrade are the only uncommitted work; everything else is green |

---
# Gemini

### Architectural Assessment & Structural Review

Your Execution Plan V2 is a **Staff-to-Principal level document**. It demonstrates structural maturity, handles dependency resolution correctly, and establishes rigid, verifiable software boundaries. By moving the `Rubric Evaluator (M3)` ahead of the `Orchestrator (M4)`, you have successfully eliminated the fake integration test pattern identified in V1.

Additionally, the concrete data contracts (`ParsedDocument`, `ParseStatus`) and the explicit environment-variable routing for the LLM backends provide exactly the kind of deterministic execution needed for an engineering assignment.

However, from an execution and timeline risk standpoint, there are subtle flaws, hidden testing gotchas, and gaps in your telemetry contract that could compromise your submission.

---

### Critical Structural & Operational Gaps

#### 1. The `pytest-bdd` Parameterization Trap (M0.5 Ingestion)

Your data contract specifies that `ParsedDocument` passes a dictionary of sections: `{"experience": "...", "skills": "..."}`.

* **The Trap:** Mapping unstructured, extracted PDF text to these sections using a `spaCy` `PhraseMatcher` inside a BDD context is notoriously difficult to test cleanly without parameterized Gherkin data tables.
* If your BDD step definitions don't explicitly pass structured multi-line text strings or table fixtures, your feature files will become bloated and unreadable. You must ensure your `document_ingestion.feature` utilizes Gherkin data tables to feed clean text variations into your step definitions.

#### 2. The Idempotency Blindspot in Database Seeding (M0.6)

Your plan states that `seed_demo` is idempotent (running it twice will not cause duplicates), and that it utilizes `factory-boy`.

* **The Gotcha:** Django models with relationship structures (`Candidate` $\rightarrow$ `Application` $\rightarrow$ `SectionEmbedding`) will naturally throw `IntegrityError` exceptions or duplicate related objects when standard `factory_boy` factories are run repeatedly on an existing database state.
* To achieve actual idempotency for your demo, your seed management command cannot rely on simple factory generation. It must implement explicit `.get_or_create()` lookups or use `factory.PostGeneration` hooks with hardcoded natural keys (such as an email address or slug).

#### 3. The Telemetry Overwrite Hazard

Your Telemetry Contract enforces class-level instrumentation at construction time:

```python
self.evaluate = pipeline_observability.instrument("stage_name")(self._evaluate_impl)

```

* **The Problem:** Reassigning class methods dynamically at instantiation breaks Python's method binding and overrides the object instances' reference metadata. This will break standard `pytest` mocking frameworks (like `unittest.mock.patch.object`) when you try to isolate or spy on these methods downstream.
* **The Fix:** You should use the standard decorator pattern directly on the class methods at the definition layer, rather than overriding instances inside `__init__`.

---

### Updated Code Artifacts & Testing Scaffolding

To unlock your execution of **Milestone 0.5 (Document Ingestion Pipeline)** under strict Double-Loop TDD constraints, here are your actual, failing test stubs, feature files, and step definition code blocks.

#### 1. The Gherkin Feature File

This file utilizes Gherkin Data Tables to cleanly isolate behavioral expectations, including fallback conditions and section extractions.

```gherkin
# features/document_ingestion.feature
Feature: Document Ingestion Pipeline
  As an AI Resume Reviewer System
  I want to parse raw PDF resumes into structured text and sections
  So that downstream processing blocks can evaluate the data cleanly

  Scenario: Successful primary extraction via PyMuPDF with structured headers
    Given a resume PDF "clean_profile.pdf" containing viable text
    And the document contains the following structural sections:
      | section_name | content_sample                              |
      | experience   | Senior Python Developer at Meez for 6 years |
      | skills       | Django, PostgreSQL, AWS, Docker             |
    When the ingestion pipeline processes "clean_profile.pdf"
    Then the parsed status should be "ok"
    And the parsed document should contain the exact canonical sections extracted

  Scenario: Automatic fallback to pdfplumber on low-character count
    Given a layout-heavy resume PDF "complex_layout.pdf"
    And PyMuPDF extracts fewer than 50 characters from the document
    When the ingestion pipeline processes "complex_layout.pdf"
    Then the system should trigger a parser fallback event
    And the parsed status should be "fallback_used"
    And the total character count should match the fallback text length

```

#### 2. The BDD Step Definition Scaffolding (`pytest-bdd`)

This file maps the outer loop scenarios directly to your system's entrypoints, implementing your exact telemetry assertions via `caplog`.

```python
# features/steps/ingestion_steps.py
import pytest
from pytest_bdd import given, when, then, scenarios, parsers
from resume_pipeline.ingestion.parser import ResumeParser, ParseStatus

scenarios("../document_ingestion.feature")

@pytest.fixture
def context():
    return {}

@given("a resume PDF \"clean_profile.pdf\" containing viable text")
def setup_clean_pdf(context, monkeypatch):
    context["filepath"] = "mock_media/clean_profile.pdf"
    # Mock primary backend behavior to return valid text length
    monkeypatch.setattr(
        "resume_pipeline.ingestion.backends.pymupdf_backend.PyMuPDFBackend.extract_text",
        lambda self, fp: ("Experience:\nSenior Python Developer at Meez for 6 years.\nSkills:\nDjango, PostgreSQL.", 2)
    )

@given("the document contains the following structural sections:")
def setup_structural_sections(context, step):
    # Extracts the Gherkin data table rows into context
    context["expected_sections"] = {row["section_name"]: row["content_sample"] for row in step.hashes}

@given("a layout-heavy resume PDF \"complex_layout.pdf\"")
def setup_complex_pdf(context, monkeypatch):
    context["filepath"] = "mock_media/complex_layout.pdf"
    monkeypatch.setattr(
        "resume_pipeline.ingestion.backends.pymupdf_backend.PyMuPDFBackend.extract_text",
        lambda self, fp: ("Empty", 1)  # Under 50 character limit
    )
    monkeypatch.setattr(
        "resume_pipeline.ingestion.backends.pdfplumber_backend.PdfplumberBackend.extract_text",
        lambda self, fp: ("Multi-column full text data extracted via fallback pipeline.", 1)
    )

@given("PyMuPDF extracts fewer than 50 characters from the document")
def assert_low_char_count(context):
    pass # Managed by the monkeypatch initialization step

@when(parsers.parse("the ingestion pipeline processes \"{filename}\""))
def process_ingestion(context, filename):
    parser = ResumeParser()
    context["result"] = parser.parse(context["filepath"])

@then("the parsed status should be \"ok\"")
def assert_status_ok(context):
    assert context["result"].status == ParseStatus.OK

@then("the parsed status should be \"fallback_used\"")
def assert_status_fallback(context):
    assert context["result"].status == ParseStatus.FALLBACK

@then("the parsed document should contain the exact canonical sections extracted")
def assert_canonical_sections(context):
    assert "experience" in context["result"].sections
    assert "skills" in context["result"].sections

@then("the system should trigger a parser fallback event")
def verify_fallback_telemetry(context, caplog):
    # Structural assertion proving the audit logger executed correctly
    assert any("parser_fallback" in record.message for record in caplog.records)

@then("the total character count should match the fallback text length")
def verify_char_count(context):
    assert context["result"].char_count == len(context["result"].raw_text)

```

#### 3. The Failing Inner-Loop Unit Test Case (`pytest`)

This unit test asserts against code boundaries that do not exist yet. Running this will generate an expected `ModuleNotFoundError` or `AttributeError`, satisfying Step 3 of your Double-Loop methodology contract.

```python
# tests/unit/test_ingestion.py
import pytest
from resume_pipeline.ingestion.backends.pymupdf_backend import PyMuPDFBackend
from resume_pipeline.ingestion.parser import ResumeParser, ParseStatus

def test_pymupdf_backend_detects_low_character_viability():
    """
    Inner loop technical test validating the mathematical boundary condition
    for triggering layout-sensitive fallback processing.
    """
    backend = PyMuPDFBackend()
    
    short_text = "   Valid text but way too short   "  # Length 34 characters stripped
    long_text = "This string exceeds fifty characters to pass the initial validation gateway step."
    
    assert backend.is_viable(short_text) is False
    assert backend.is_viable(long_text) is True

def test_parser_runtime_exception_handling_emits_failed_status(monkeypatch):
    """
    Technical validation checking that file corruption mutations safely
    gracefully exit into structural states instead of throwing uncaught exceptions.
    """
    monkeypatch.setattr(
        "resume_pipeline.ingestion.backends.pymupdf_backend.PyMuPDFBackend.extract_text",
        self_raising_exception
    )
    
    parser = ResumeParser()
    result = parser.parse("mock_media/corrupted.pdf")
    
    assert result.status == ParseStatus.FAILED
    assert result.char_count == 0
    assert result.sections == {}

def self_raising_exception(*args, **kwargs):
    raise IOError("File signature not recognized or stream is corrupted.")

```

---

### Step-by-Step Risk Mitigation Plan

To guarantee that your velocity does not stall out on the engineering execution of the upcoming phases, make sure you integrate these changes into your workflow:

```
[M0.5 Ingestion] ───► [M0.6 Seeding via .get_or_create()] ───► [M3 Upgrade via Pydantic]

```

1. **For Milestone 0.5 (Ingestion):** If your `spaCy` text mapping strategy misses headings due to unexpected casing layouts or spaces, immediately abandon advanced semantic parsing and fallback to a deterministic regex pattern string splitter (`re.split(r'(?i)\b(experience|skills|education)\b', text)`). Keep moving.
2. **For Milestone 0.6 (Seeding):** Force all model instances generated inside `seed_demo` to clear out previous data states using `.delete()` sequences at the top of the execution block. This guarantees a clean, predictable context every time the reviewer boots up `docker compose`.
3. **For Milestone 3 (LLM Upgrade):** Ensure your `instructor` client uses `gpt-4o-mini` or `claude-3-5-haiku` to dramatically limit latency cycles and test suite duration. Keep the retry threshold strictly set to 3 attempts with `tenacity` to prevent infinite hangs during runtime check routines.

---
# Carlos

Given your plan review, write a prompt to use in Claude CoWork to review the plan and cover the gaps or mitigate the risks raised

---
# Gemini

Here is a precise, copy-and-paste prompt you can feed directly into your Claude CoWork thread to address the exact structural risks, parsing complexities, and testing traps we just identified.

---

**Copy and paste the text below into your Claude CoWork thread:**

```markdown
Act as a Principal Staff Engineer. We need to audit and refine our `execution_plan_v2.md` before we begin writing code. While the milestone structure and architectural boundaries are correct, a deep-dive risk assessment has surfaced three critical execution gaps that will cause our Double-Loop TDD test suite to stall or break.

We need to patch these risks directly into our V2 plan. Please update the plan and output it as a code block for `execution_plan_v2.md` addressing the following engineering realities:

1. **The pytest-bdd Parameterization Trap (Milestone 0.5):** Mapping unstructured PDF text to canonical sections via spaCy is highly variable. If we write naive BDD scenarios, our features will become unreadable or brittle. We must explicitly mandate that `features/document_ingestion.feature` utilizes Gherkin Data Tables to pass structured multi-line text strings and layout variations into our step definitions.

2. **The Idempotency Factory-Boy Blindspot (Milestone 0.6):** Our plan states that `seed_demo` must be idempotent, but it relies on `factory-boy`. Running standard factories twice on highly relational schemas (Jobs -> Candidates -> Applications -> Embeddings) will trigger IntegrityErrors or duplicate records. Update the strategy: the seeding script must strictly use Django's `.get_or_create()` with natural unique keys (like emails/slugs), or use an explicit data purging step (`Model.objects.all().delete()`) at the very beginning of the command execution block.

3. **The Telemetry Method-Binding Hazard (Telemetry Contract):** The current contract suggests patching methods at construction time (`self.evaluate = pipeline_observability.instrument(...)`). This dynamically breaks Python's method binding and reference metadata, making it incredibly painful to use `unittest.mock.patch.object` in downstream tests. Update the Telemetry Contract to enforce the standard decorator pattern directly on class methods at the definition layer (`@pipeline_observability.instrument("stage_name")`), rather than overriding instances in `__init__`.

**Your Task:**
1. Generate the updated, bulletproof version of `execution_plan_v2.md` inside a markdown block. Ensure these specific testing and execution safety measures are woven into Milestones 0.5, 0.6, and the Telemetry Contract.
2. Provide the first complete `features/document_ingestion.feature` utilizing a Gherkin Data Table for structural section mapping, along with its matching `pytest-bdd` step definitions showing how to extract data from that table cleanly.

Let's tighten this execution loop so our test suite remains reliable and fast.

```