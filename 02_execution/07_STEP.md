Now confirm the tests fail on import exactly as intended:All four deliverables are locked in. Here's what was produced and why each decision was made.

---

**`execution_plan_v2.md`** — patches the original without touching it. Five structural changes from V1:

The dependency order fix is the most critical correction. V1 had `M4 → M3` which is logically impossible — the Orchestrator calls `RubricEvaluator.evaluate()`, so the rubric stage must be production-ready first. The corrected chain is `M0.5 → M0.6 → M1 → M2 → M3 → M4 → M5 → M6`. The two completed milestones that ran out of order (M4 was built before M3's real LLM backend) are flagged for re-verification.

For real LLM integration in M3, the plan specifies `instructor` wrapping either `openai.OpenAI()` or `anthropic.Anthropic()`, with a `RubricScoreResponse` Pydantic model that validates every criterion score is in [1, 5] and all five criteria are present. A `make_rubric_backend()` factory reads the `LLM_BACKEND` env var, so `MockLLMBackend` stays active in all unit and BDD tests — zero test suite changes required.

Time-boxes are tight but achievable: M0.5 in 8 hours today, M0.6 in 4 hours tomorrow, M3 LLM upgrade in 8 hours, re-verify M4 in 2 hours, leaving two full days of buffer before June 19.

---

**`document_ingestion.feature`** — 14 scenarios covering the full outer loop contract: PyMuPDF primary path, spaCy section detection (including case-insensitivity and structureless text), pdfplumber fallback trigger and audit event, both failure modes (corrupt file and missing file), observability latency records on success and failure, and the audit event ordering constraint (`document_ingestion_started` before `document_parsed`).

---

**`ingestion_steps.py`** — every step raises `NotImplementedError` with an explicit instruction for what to do next. This is intentional: the stubs give pytest-bdd the step signatures it needs to recognise the scenarios, but produce the correct red state (NotImplementedError rather than "step not found"). The import block is commented out and annotated explaining exactly why it stays commented out until the inner tests are green.

---

**`test_ingestion.py`** — 38 unit tests in five classes. The critical red state is confirmed: `No module named 'resume_pipeline.ingestion'` on import. The tests are written against the interface contracts, not the implementation, so they survive internal refactoring. Key design decisions baked in as test assertions: `MIN_VIABLE_CHARS = 50`, `ParseError` raised by backends (not raw exceptions), `ResumeParser` accepts injectable backends and observability so tests never touch real PDFs, `char_count == len(raw_text)` enforced at the data contract level, and both latency records and audit JSON events are verified independently.