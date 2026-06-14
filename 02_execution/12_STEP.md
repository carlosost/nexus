Now I have everything. M4 re-verification has three concrete tasks: update the orchestrator default, add `model_name` to `log_score_computed`, and write the integration test. Let me create tasks and execute:**Task 53 — Update orchestrator default + add `model_name` to audit**Now update the `__init__` default and `log_score_computed` call:Now add `model_name` to the `log_score_computed` call in the orchestrator:Now update `log_score_computed` in `logging_module.py` to accept `model_name`:**Task 54 — Integration test****Task 55 — Sandbox verification**M4 re-verification complete. Here's what was done:

**Files changed:**

`resume_pipeline/pipeline/orchestrator.py` — default `rubric_evaluator` is now `RubricEvaluator(make_rubric_backend())` instead of `StubRubricEvaluator()`. Added `model_name` extraction from `self._rubric._llm.model_name` and passes it to `log_score_computed`.

`resume_pipeline/logging_module.py` — `log_score_computed()` now accepts optional `model_name` and `retry_count` fields (non-breaking addition).

`tests/integration/__init__.py` + `tests/integration/test_orchestrator_integration.py` — 16 mock-LLM tests (always run) + 4 real-LLM tests (skipped unless `LLM_BACKEND=openai|anthropic`). Covers:
- Pass path executes all 3 stages in order
- LLM backend is actually called (not StubRubricEvaluator)
- `score_computed` audit event includes `model_name`
- Fail path short-circuits after `hard_gate`, LLM never called
- Default orchestrator uses `RubricEvaluator`, not `StubRubricEvaluator`

**Sandbox verified:** `stages_executed=['hard_gate', 'semantic_match', 'rubric']`, `rubric_score=0.800`, `final_score=0.698`, `model_name='mock-llm-v1'` in audit log, fail path LLM calls = 0.

**Current milestone status:** M0.5 ✅ M0.6 ✅ M1 ✅ M2 ✅ M3 ✅ M4 ✅ M5 ✅ M6 ✅ — next is M7 Integration & Demo Hardening.