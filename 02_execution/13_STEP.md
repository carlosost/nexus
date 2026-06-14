Now the production and local settings:Also need a health endpoint — check if it exists:Now update `pytest.ini` to add coverage flags and the `integration` marker:Also add `requirements.txt` with all V2 dependencies since it was missing:**Task 60 — Sandbox verification**`ResumeParser` doesn't accept `audit_logger` injection — fix it to enable clean testing:The test is correct — I need to add `audit_logger` injection to `ResumeParser.__init__`:Now run the sandbox verification for the full M7 integration flow:All 7 tests pass. M7 Integration & Demo Hardening is complete. Here's the status across the full V2 plan:

**What just passed in sandbox:**
- `ResumeParser` now accepts `audit_logger` injection — consistent with how `observability` is handled
- Full pass path (Alice): 3 stages executed, rubric=0.800, final=0.711
- Full fail path (Carol): short-circuits at `hard_gate`, LLM never called, `final_score=0.0`
- Latency records emitted for all 3 stages on the pass path
- `score_computed` audit event carries `model_name` and all 3 `component_scores`
- `pipeline_short_circuited` fires on the fail path; `score_computed` does not

**What runs on your machine (requires the full stack):**
```bash
# Unit + integration suite with coverage
pytest tests/ features/ --cov --cov-report=html

# Docker smoke test (after docker compose up -d)
bash scripts/smoke_test.sh
```

The full milestone chain M0.5 → M0.6 → M1 → M2 → M3 → M4 → M5 → M6 → M7 is done.