Good — all files are in place. Let me run the unit tests to confirm they're in the right "failing for the right reason" state (the implementation is there in this case, so they should pass — let me verify the tests actually run correctly):All logic verified. Let me also spot-check the keyword and certification handlers:Here's what was built and the key design decisions behind each piece.

---

**EXECUTION_PLAN.md** — Six milestones, each structured as outer BDD spec → inner unit tests → implementation → exit criterion. The priority sequence at the bottom (M1 → M2 → M4 → M5 → M3 → M6) is deliberate: get a working end-to-end pipeline with the two heaviest algorithmic stages before touching LLM rubric scoring, which can run in parallel once the orchestrator interface is stable.

---

**Backend Architecture**

`models.py` encodes nine entities across the full pipeline lifecycle. A few structural choices worth calling out:

- `Application.Status` has `gate_unknown` as a distinct state — unknown is not the same as pending, and the orchestrator needs to route it differently from a pass.
- `SectionEmbedding` uses `models.JSONField` as a portability shim in tests; the production migration swaps this for `pgvector.django.VectorField(dimensions=1536)` with a `CREATE EXTENSION IF NOT EXISTS vector` prerequisite.
- `RubricScore` carries the weights as a class-level constant dict (`WEIGHTS`) so the normalization formula is co-located with the data, not scattered into a utility module.
- `HumanReview.override_reason` is `blank=True` at the DB layer — enforcement is at the serializer (API) layer, which is the right place: it lets `approve`/`reject` decisions skip the reason while `override_pass`/`override_fail` require it.

**Observability** (`observability.py`) is a decorator factory + context manager pair with a swappable `sink`. In tests, inject a collecting sink and assert on `obs.get_records()`. In production, swap the sink for a Prometheus counter or a Datadog client — zero changes to pipeline business logic.

**Audit Logging** (`logging_module.py`) emits one JSON line per event to a named logger (`pipeline.audit`). Route it to a separate log stream in production. Every gate transition, LLM divergence, and human override has a typed method with explicit kwargs — no raw dict construction at call sites.

---

**First Double-Loop Step**

`hard_gate.feature` covers 13 scenarios across all three outcome branches plus the two precedence rules (FAIL > UNKNOWN > PASS, empty criteria → UNKNOWN) and the final score integration. This is the full contractual surface for Stage 1 — nothing in the implementation can legitimately break these without a scenario catching it.

`hard_gate_steps.py` delegates completely to the domain objects — no logic in the steps themselves. The table parser handles the simplified Gherkin table format used across scenarios.

`test_hard_gate.py` has 36 unit tests across five classes. The two worth highlighting:

- `test_empty_criteria_is_unknown` — this is a trap. An empty must-haves dict returning `PASS` would silently approve every candidate when a job is misconfigured. The test encodes the rule that silence is not consent.
- `test_invalid_weights_raise_on_construction` — `FinalScoreWeights` is a frozen dataclass that validates in `__post_init__`. This makes a misconfigured weight set a startup failure, not a silent calculation error in production.