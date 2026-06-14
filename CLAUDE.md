# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**elvex-nexus** is an AI-powered resume evaluation pipeline. It accepts PDF resumes, parses them, runs them through a 4-stage scoring pipeline, and surfaces results for human review. The backend is Django + DRF with PostgreSQL + pgvector. The frontend is React + Vite.

## Running the stack

```bash
# Full stack (no API keys required — uses mock LLM backend by default)
docker compose up --build

# With a real LLM backend
LLM_BACKEND=openai OPENAI_API_KEY=sk-... docker compose up --build
LLM_BACKEND=anthropic ANTHROPIC_API_KEY=... docker compose up --build

# Reset demo data (seeds Alice / Bob / Carol)
docker compose run --rm app python manage.py seed_demo --purge
docker compose run --rm app python manage.py seed_demo
```

The app boots on http://localhost:8000. The entrypoint auto-runs migrations and `seed_demo`.

## Python tests

```bash
# All tests
pytest

# Unit tests only (fast, no DB, no network)
pytest -m unit

# Integration tests
pytest -m integration

# BDD feature scenarios
pytest -m bdd

# Single test file
pytest tests/unit/test_pipeline.py

# With coverage
pytest --cov --cov-report=html
```

Settings module for tests: `config.settings.test` (SQLite, no pgvector). Set via `pytest.ini`.

## Frontend tests

```bash
cd frontend
npm test                 # Jest unit tests (one-shot)
npm run test:watch       # Jest in watch mode
npm run cy:open          # Cypress interactive
npm run cy:run           # Cypress headless
npm run dev              # Vite dev server (proxies /api to localhost:8000)
```

## Django management

```bash
python manage.py migrate
python manage.py seed_demo          # Populate demo data
python manage.py seed_demo --purge  # Wipe and re-seed
```

## Architecture

### 4-stage pipeline (`resume_pipeline/pipeline/`)

The core evaluation runs in `PipelineOrchestrator.run()`:

1. **Hard Gate** (`hard_gate.py`) — checks must-have criteria (years experience, keyword presence, certifications). Outcome: PASS / FAIL / UNKNOWN. Short-circuits to `FinalScore=0` on FAIL.
2. **Semantic Match** (`semantic_match.py`) — cosine similarity between per-section candidate and job embeddings, fused with lexical rank via RRF (`search/rrf.py`).
3. **Rubric Scoring** (`rubric_score.py`) — LLM evaluates 5 competencies (core_skills, relevant_experience, scope_impact, domain_alignment, education_certs) on a 1–5 scale using prompts in `pipeline/prompts/`. Structured output enforced by `instructor`.
4. **Final Score** (`final_score.py`) — `0.45 * semantic + 0.45 * rubric_norm + 0.10 * evidence_quality`.

The orchestrator is dependency-injected: all four evaluators can be swapped in tests. It does **not** persist to the DB — that's the caller's responsibility (view or Celery task).

### LLM backends (`resume_pipeline/pipeline/rubric_score.py`)

Controlled by the `LLM_BACKEND` env var (`mock` | `openai` | `anthropic`). `make_rubric_backend()` selects the backend. The mock backend returns deterministic scores without network calls — used by default in Docker and tests.

### Data model (`resume_pipeline/models.py`)

```
Job → Application ← Candidate
Application → HardGateResult (Stage 1)
Application → SemanticMatchResult (Stage 2)
Application → RubricScore (Stage 3)
Application → FinalScore (Stage 4)
Application → HumanReview (human-in-the-loop)
Candidate → SectionEmbedding (per-section vectors, dim=1536)
Job → JobSectionEmbedding
```

All PKs are UUIDs. `Application.status` tracks lifecycle: `pending → gate_failed / gate_unknown / gate_passed → scored → under_review → approved / rejected`.

### Ingestion (`resume_pipeline/ingestion/`)

PDF parsing uses `pymupdf` (primary) with a `pdfplumber` fallback for multi-column layouts. `section_detector.py` uses spaCy (`en_core_web_sm`) to classify resume sections.

### Hybrid search (`resume_pipeline/search/`)

`HybridSearchEngine` runs PostgreSQL FTS + pgvector cosine similarity, then fuses rankings with Reciprocal Rank Fusion (`rrf.py`). Returns ranked candidate IDs; per-section scores come from `SemanticMatchEvaluator`.

### API endpoints (`resume_pipeline/urls.py`)

All routes are under `/api/`. Key human-review endpoints:
- `GET /api/applications/<uuid>/score/` — AI score card
- `POST /api/applications/<uuid>/reviews/` — submit human decision (approve / reject / override_pass / override_fail; override decisions require `override_reason`)
- `POST /api/applications/` — submit a new application (triggers pipeline)
- `GET /api/health/` — used by Docker healthcheck

### Settings hierarchy

`config/settings/base.py` → `local.py` / `test.py` / `production.py`. Test settings use SQLite and stub out pgvector. Local and production use PostgreSQL via `DATABASE_URL`.

### Observability & audit logging

`resume_pipeline/observability.py` — process-level singleton `pipeline_observability` records per-stage latency. `resume_pipeline/logging_module.py` — `audit_logger` singleton emits structured JSON events (gate transitions, score computed, overrides). Use the `fresh_observability` pytest fixture to isolate latency assertions between tests.

### BDD tests (`features/`)

Feature files describe outer-loop scenarios. Step definitions live in `features/steps/`. The `ctx` fixture in `conftest.py` is the shared state dict passed between steps within a scenario.
