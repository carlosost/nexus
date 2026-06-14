# Execution Plan: Resume Evaluation Pipeline

> Principal Staff Engineer review. Structured around **Double-Loop TDD** — BDD outer loop (pytest-bdd / Gherkin) drives business specifications; pytest inner loop drives unit-level correctness. No production logic is written without a failing inner test that is itself driven by a failing outer specification.

---

## Milestone 0 — Toolchain & Docker Scaffolding

**Goal:** Zero-friction local environment. Every subsequent milestone runs `docker compose up` and `pytest`.

### Tasks

- `docker-compose.yml`: PostgreSQL 16 + pgvector extension, Django app service, optional pgAdmin
- `requirements.txt`: `django`, `psycopg2-binary`, `pgvector`, `openai`, `pytest`, `pytest-bdd`, `pytest-django`, `factory-boy`, `coverage`
- Django project init: `django-admin startproject config .` + `startapp resume_pipeline`
- `settings/base.py` → `settings/test.py` split; configure `DATABASES`, `INSTALLED_APPS`, `pgvector`
- `conftest.py` at root: `@pytest.fixture(scope="session")` for DB setup, BDD scenario context
- `pytest.ini`: `bdd_features_base_dir = features/`, `django_db_setup`
- GitHub Actions CI stub: run `pytest --cov` on every push

**Exit criterion:** `pytest --collect-only` shows 0 errors; `docker compose up` starts cleanly.

---

## Milestone 1 — Hard Gate (First Full Double Loop)

**Goal:** The complete Double-Loop for Stage 1. This is the template every subsequent stage follows exactly.

### Outer Loop — BDD Specification

Write `features/hard_gate.feature` covering:
- `pass` — all criteria satisfied
- `fail` — any single criterion fails
- `unknown` — required data absent from resume
- `fail` trumps `unknown` (safety-first)
- Final score is `0.0` when gate outcome is `fail`

Run `pytest features/` → **all scenarios fail** (no step definitions). This is correct.

### Inner Loop — Unit Tests

Write `tests/unit/test_hard_gate.py` covering:
- `GateOutcome` aggregation logic (pass/fail/unknown precedence)
- `years_experience` criterion: meets, exactly meets, below, missing data
- `keyword_presence` criterion: found, missing, partial match, case insensitivity, empty config
- `certification` criterion: has cert, missing cert, empty section
- Unknown criterion type → `unknown`
- `FinalScoreCalculator`: gate fail → `0.0`, gate pass → weighted formula

Run `pytest tests/unit/` → **all tests fail** (no implementation). Correct.

### Implementation

Write in this order — each makes the next failing test go green:

1. `resume_pipeline/pipeline/hard_gate.py` — `GateOutcome`, `CriterionResult`, `HardGateEvaluation`, `HardGateEvaluator`
2. `resume_pipeline/pipeline/final_score.py` — `FinalScoreCalculator`
3. Wire step definitions in `features/steps/hard_gate_steps.py`

Run `pytest` → all inner tests green, all outer scenarios green.

### Django Model

Write `HardGateResult` model (see schema below). Write migration. No model tests until Milestone 4 (integration layer).

### Logging Integration

`StructuredAuditLogger.log_gate_transition()` called at the end of each criterion evaluation. Verify log output in unit tests by asserting on `caplog`.

**Exit criterion:** `pytest` is 100% green. `coverage report` shows >90% on `hard_gate.py`.

---

## Milestone 2 — Semantic Match & Hybrid Search

**Goal:** Stage 2 of the pipeline. Section-aware embeddings + RRF combining lexical and vector search.

### Outer Loop — BDD Specification

Write `features/semantic_match.feature`:
- Candidate with high semantic overlap scores above threshold
- Candidate with low overlap scores below threshold
- RRF rank fusion produces score between 0–1
- Hybrid search returns candidates ordered by RRF score

### Inner Loop — Unit Tests

Write `tests/unit/test_rrf.py`:
- `compute_rrf_score(lexical_rank, semantic_rank, k=60)` — formula correctness
- `normalize_cosine_similarity(raw)` → `[0, 1]`
- `section_weighted_similarity(section_scores, weights)` — weighted average

Write `tests/unit/test_embedding.py`:
- `generate_section_embedding(text, model)` returns vector of correct dimension
- Identical texts → similarity ≈ 1.0
- Unrelated texts → similarity < 0.5
- (Use a mock embedding client to avoid real API calls in unit tests)

### Implementation

1. `resume_pipeline/search/hybrid_search.py` — `HybridSearchEngine` wrapping pg full-text + pgvector cosine query
2. `resume_pipeline/pipeline/semantic_match.py` — `SemanticMatchEvaluator`
3. `resume_pipeline/embeddings.py` — `EmbeddingClient` (adapter over OpenAI / local model)

### Django Models

`SectionEmbedding`, `JobSectionEmbedding`, `SemanticMatchResult` (see schema).

### Observability Integration

`@pipeline_observability.instrument("semantic_match")` wraps `SemanticMatchEvaluator.evaluate()`. Assert latency records exist in integration tests.

**Exit criterion:** All scenarios green. RRF unit tests cover the mathematical edge cases (tied ranks, single-source results).

---

## Milestone 3 — Rubric Scoring

**Goal:** Stage 3. LLM evaluates 4–6 role-specific competencies; weights produce normalized score.

### Outer Loop — BDD Specification

Write `features/rubric_score.feature`:
- All criteria rated 5 → normalized score approaches 1.0
- Missing competency data → score flagged with low confidence
- Weighted formula is correctly applied

### Inner Loop — Unit Tests

Write `tests/unit/test_rubric.py`:
- `RubricWeights` constant validation (weights sum to 1.0)
- `normalize_rubric_score(raw_scores, weights)` — correct weighted average → `[0, 1]`
- `compute_evidence_quality(criterion_results)` — detection of supported vs. unsupported claims
- LLM call is mocked; test only the aggregation logic

### Implementation

1. `resume_pipeline/pipeline/rubric_score.py` — `RubricEvaluator`, `RubricWeights`
2. LLM prompt templates in `resume_pipeline/prompts/rubric.py`
3. `EvidenceQualityScorer` — heuristic that measures citation density in evidence strings

### Logging Integration

`StructuredAuditLogger.log_llm_override()` called if rubric LLM result deviates from heuristic baseline by > threshold.

**Exit criterion:** All scenarios green. Rubric weights constant test enforces `sum(weights) == 1.0` at import time.

---

## Milestone 4 — Final Score & Pipeline Orchestration

**Goal:** Wire all stages into a single `PipelineOrchestrator`. Enforce gate short-circuit. Capture full observability trace.

### Outer Loop — BDD Specification

Write `features/pipeline_orchestration.feature`:
- Gate fail → pipeline stops at Stage 1, final score = 0
- Gate unknown → pipeline continues with reduced confidence
- Gate pass → all stages run, final score = weighted formula
- Observability records are emitted for each stage that runs

### Inner Loop — Unit Tests

Write `tests/unit/test_pipeline.py`:
- `PipelineOrchestrator.run()` calls stages in order
- Stage short-circuit on gate fail (Stages 2–3 are NOT called)
- `FinalScore` formula: `(0.45 * semantic) + (0.45 * rubric_norm) + (0.10 * evidence)`
- Observability sink receives one record per stage executed

### Implementation

1. `resume_pipeline/pipeline/orchestrator.py` — `PipelineOrchestrator`
2. `FinalScore` Django model + migration
3. Integration test: full pipeline run against a test DB with pgvector

**Exit criterion:** Integration test covers the happy path end-to-end.

---

## Milestone 5 — Human-in-the-Loop API

**Goal:** REST endpoints exposing AI score, confidence, rubric breakdown. Override endpoint requires reason.

### Outer Loop — BDD Specification

Write `features/human_review.feature`:
- Reviewer submits override with reason → logged
- Override without reason → 400 Bad Request
- Override reason is stored and surfaced in audit log
- After override, application status transitions correctly

### Implementation

1. `resume_pipeline/views.py` — `ApplicationReviewView`, `OverrideView`
2. `resume_pipeline/serializers.py` — `FinalScoreSerializer`, `HumanReviewSerializer`
3. `HumanReview` model + migration

### Logging Integration

`StructuredAuditLogger.log_human_override()` in `OverrideView.post()`.

**Exit criterion:** API tests (pytest + `APIClient`) cover all scenarios.

---

## Milestone 6 — Human-in-the-Loop UI

**Goal:** Reviewer-facing interface. Shows AI score, confidence, rubric breakdown. Override form enforces mandatory reason.

### Components

- `ScoreCard` — displays `FinalScore`, confidence band, stage-level breakdown
- `RubricBreakdown` — per-competency scores with weight labels
- `OverridePanel` — decision buttons (Approve / Reject / Override) with mandatory `reason` textarea
  - Submit disabled until reason is non-empty
  - POST to `/api/reviews/` on confirm
- `AuditTrail` — read-only list of prior override events for the application

**Exit criterion:** Cypress e2e test: load score card → click Override → submit without reason → button stays disabled → enter reason → submit succeeds.

---

## Architecture Constraints (Non-Negotiable)

| Constraint | Decision |
|---|---|
| System of Record | PostgreSQL only — no Elasticsearch, no SQLite |
| Vector Storage | `pgvector` extension on the same Postgres instance |
| Hybrid Search | Reciprocal Rank Fusion over full-text + cosine similarity |
| Gate Outcomes | Strictly `pass`, `fail`, `unknown` — no other values |
| Final Score when gate fails | Hard-coded `0.0` — formula does not run |
| Test methodology | Double-Loop TDD — outer BDD spec must fail before inner unit test is written |
| Observability | Decorator-based latency wrapping — zero business logic pollution |
| Audit logging | Structured JSON lines — every gate transition and override is logged |

---

## Priority Order (Hard Deadline)

```
M1 Hard Gate  →  M2 Semantic Match  →  M4 Orchestrator  →  M5 API  →  M3 Rubric  →  M6 UI
```

Rationale: M1 + M2 + M4 give you a working end-to-end pipeline with the two heaviest algorithmic components. M5 unblocks human review immediately. M3 (LLM rubric) can run in parallel once M4's orchestrator interface is stable. M6 UI is last because the API is the real gate.
