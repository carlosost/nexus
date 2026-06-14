Milestone 4 complete. Here's what was built and the key decisions.

---

**Outer loop** — `pipeline_orchestration.feature` has 13 scenarios across five groups: gate-fail short-circuit, gate-pass full path, gate-unknown continuation, observability record counts, and `stages_executed` structure assertions. Every business rule from the execution plan has a scenario enforcing it.

**Inner loop** — `test_pipeline.py` has 42 tests across eight classes. A few worth calling out explicitly:

- `TestGateFailShortCircuit.test_semantic_evaluator_not_called_on_gate_fail` — uses `assert_not_called()` on the mock, not just inspecting the result. This is the right level of assertion: it proves the gate is actually a circuit breaker, not just that the final score happened to be 0.
- `TestOrchestratorObservability.test_observability_records_cleared_between_runs` — clears the `obs` instance between two runs and checks the second run produces exactly 3 records. Without this, accumulated records could silently corrupt latency dashboards.
- `TestOrchestratorAuditLogging` — uses `caplog` to assert on the structured JSON content of log lines, not just that logging was called. This makes the audit contract explicit.

**Implementation** — three modules:

`rubric_protocol.py` defines `RubricEvaluatorProtocol` (a `@runtime_checkable` Protocol) and `StubRubricEvaluator`. The orchestrator depends on the protocol — M3's `LLMRubricEvaluator` drops in without changing the orchestrator at all. The stub returns deliberately non-perfect scores (0.70 / 0.65) to avoid masking formula bugs that would vanish if every input were 1.0.

`orchestrator.py` uses a `_timed()` helper rather than `@pipeline_observability.instrument()` on the injected evaluators. This is intentional: decorating a mock's method would replace the mock with a wrapper, breaking `assert_called_once()` assertions in the unit tests.

`orchestration_steps.py` uses call-spy wrappers (not `MagicMock`) on the real evaluators so the Gherkin `was executed` steps work against the actual HardGateEvaluator and StubRubricEvaluator. The `PipelineOrchestrator` in the BDD step context runs real logic, not mocks — the BDD suite is a genuine integration check, while the unit tests mock everything.

**Current pipeline state across all milestones:**

```
M1 Hard Gate    ✅  HardGateEvaluator, FinalScoreCalculator
M2 Semantic     ✅  RRF, EmbeddingClient, SemanticMatchEvaluator, HybridSearchEngine
M4 Orchestrator ✅  PipelineOrchestrator, RubricProtocol, StubRubricEvaluator
M5 API          ← next (per priority order)
M3 Rubric       ← parallel with M5 once orchestrator interface is stable
M6 UI           ← last
```