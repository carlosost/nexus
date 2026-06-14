**Step 1 — Outer loop: new BDD scenarios (→ RED)****Step 2 — Inner loop: failing unit tests**Both inner-loop tests go red. Now implement:**Step 3 — Implementation**Now add `RubricScoreResponse`, the real backends, and the factory after `MockLLMBackend`:Now update `_parse_response` to handle `RubricScoreResponse` objects from real backends:Now verify the implementation in sandbox:Pydantic isn't in the sandbox (no pip access). Verify the non-Pydantic logic by stubbing it:Need to defer the `instructor`/`openai`/`anthropic` imports out of `__init__` — lazy init on first call:Now verify the retry logic with a mocked openai client:**Step 4 — Complete step definitions for new BDD scenarios**Now do a final structural check — verify the step definitions parse correctly and the import chain is clean:M3 upgrade complete. Here's what was added:

**`features/rubric_score.feature`** — 10 new scenarios covering `RubricScoreResponse` validation, `make_rubric_backend()` factory for all three backends, OpenAI retry-then-succeed, retry exhaustion with reraise, and evaluator acceptance of Pydantic objects directly.

**`tests/unit/test_rubric.py`** — 4 new test classes: `TestRubricScoreResponse` (7 tests), `TestMakeRubricBackend` (10 tests), `TestOpenAIRubricBackendRetry` (3 tests), `TestRubricEvaluatorWithPydanticResponse` (3 tests).

**`resume_pipeline/pipeline/rubric_score.py`** — added:
- `RubricScoreResponse` (Pydantic `BaseModel` with `model_validator` enforcing all 5 criteria and scores 1-5)
- `OpenAIRubricBackend` with fully lazy imports and `tenacity` retry on `RateLimitError`/`APITimeoutError`/`APIConnectionError`
- `AnthropicRubricBackend` with same pattern
- `make_rubric_backend()` factory (explicit arg → `LLM_BACKEND` env var → `"mock"`)
- `_parse_response()` updated to detect `RubricScoreResponse` objects and unwrap them directly, keeping the existing string-JSON path intact for `MockLLMBackend` backward compatibility

**`features/steps/rubric_steps.py`** — 17 new step definitions wired to all new scenarios.

**Current milestone status:** M0.5 ✅ M0.6 ✅ M1 ✅ M2 ✅ M3 ✅ — next is M4 re-verification (wire real M3 backend into orchestrator integration test).