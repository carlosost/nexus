Now read models.py and rubric_protocol.py to ground the implementation:Good. I have what I need. The `WEIGHTS` in `RubricScore` are authoritative. `normalized_score = weighted_sum / 5.0` (all scores at 3.5 → 0.70, which exactly matches the `StubRubricEvaluator.DEFAULT_NORMALIZED_SCORE` — confirming the formula). Let's build M3.Now write the implementation:Now write the prompt templates (the system prompt lives in the module but externalize it too):The justification string has 9 words — one short of the threshold. Fix the unit tests and verification script to use ≥10-word justifications:Now fix the feature file and BDD step (which also uses the same check) and re-run verification:Now write the BDD step definitions to close the outer loop:**M3 complete.** All 18 verification assertions pass. Key design decisions:

- `normalized_score = weighted_sum / 5.0` — maps [1,5] → [0.2, 1.0]. All scores at 3.5 → **0.70**, which exactly matches `StubRubricEvaluator.DEFAULT_NORMALIZED_SCORE` (intentional cross-check).
- `evidence_quality` = fraction of criteria with ≥10 words in LLM justification. Clean, testable, meaningful.
- Parse fallback: malformed/empty LLM response → `FALLBACK_SCORE=3.0` for all criteria → `normalized_score=0.60`, `evidence_quality=0.0`.
- `RubricEvaluator` satisfies `RubricEvaluatorProtocol` via structural subtyping — orchestrator requires no changes.
- `LLMBackendProtocol` is swappable: `MockLLMBackend` in tests → drop in `OpenAIBackend` or `AnthropicBackend` for production.

One milestone remaining: **M6 — Human-in-the-Loop UI** (React frontend). Ready to start?