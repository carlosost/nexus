# Elvex Nexus

**Stop screening resumes by gut feeling. Score them with a pipeline you can audit.**

Elvex Nexus turns a job description and a stack of PDF, DOC or DOCX resumes into ranked, explainable candidate scores — hard-gate filtering, semantic similarity, LLM-based rubric scoring, and a human-in-the-loop review layer, all wired into one Django + React stack you can run with a single command.

> In advance, two very important information: Section "Quick Start" bellow has instructions to run the application with real LLM conectivity. Documentation "ARCHITECTURE_DECISIONS.md" has a template of Job Description to be used to create new Jobs.

---

## Why this exists

Resume screening tools tend to fall into two camps: keyword-matching ATS software that rejects good candidates over phrasing, or black-box "AI scoring" you can't interrogate when a hiring manager asks *why*. Elvex Nexus is built around a different idea — every score is the output of a **4-stage pipeline**, and every stage's verdict is persisted, logged, and inspectable:

1. A candidate either clears your non-negotiables or doesn't (Hard Gate).
2. Their resume either resembles the job semantically or it doesn't (Semantic Match).
3. An LLM rates them against five weighted competencies, with citations (Rubric Score).
4. The three signals combine into one composite score a human reviewer can override — with a mandatory reason, logged for audit.

---

## Core Feature Matrix

* **Markdown-Driven Job Ingestion** — Paste a Markdown job spec (`# Title`, `## Description`, `## Requirements`, `## Must Haves`) into `POST /api/jobs/`, and the parser maps it directly onto the `Job` model — `title`, `description`, `requirements_raw`, and `must_haves` — with field-level 422 errors when something's missing. No multi-field form to maintain, and the input format doubles as LLM-ready context.

* **High-Performance Resume Pipeline** — PDF resumes are parsed with `pymupdf` (fast path) and silently fall back to `pdfplumber` for multi-column layouts that trip up the primary backend. Section detection (`spaCy`) extracts experience, skills, education, and certifications into a structured JSON blob that feeds every downstream pipeline stage.

* **4-Stage Scoring Pipeline** — Hard Gate (pass/fail/unknown on must-have criteria) → Semantic Match (cosine similarity + lexical rank fused via Reciprocal Rank Fusion) → Rubric Scoring (LLM-evaluated, 5 competencies, `instructor`-enforced structured output) → Final Score (`0.45 × semantic + 0.45 × rubric + 0.10 × evidence_quality`). A Hard Gate `FAIL` short-circuits straight to a final score of `0`.

* **LLM Resilience & Fallback** — Switch between `mock`, `openai`, and `anthropic` rubric backends with one environment variable. Configure a fallback provider (`LLM_BACKEND_FALLBACK`) so a primary-provider outage doesn't stall the pipeline — the system retries via `tenacity`, fails over automatically, and stamps `is_evaluated_via_fallback=True` on the affected score for reviewer visibility.

* **AI Orchestration & Telemetry Dashboard** — A React dashboard surfaces application status distribution, job funnel metrics, and LLM resilience stats (how often fallback kicked in) via `GET /api/dashboard/stats/`, backed by a process-level observability singleton that records per-stage pipeline latency.

* **Human-in-the-Loop Review** — Reviewers approve, reject, or override any AI verdict via `POST /api/applications/<uuid>/reviews/`. Override decisions (`override_pass` / `override_fail`) require a non-empty `override_reason` — enforced at the serializer layer before the DB is touched, so every disagreement with the model is on the record.

* **Structured Audit Logging & Observability** — Every gate transition, score computation, and human override emits a structured JSON event via the `audit_logger` singleton, and pipeline stage latency is tracked via `pipeline_observability` — both designed to be queryable in your log aggregator of choice.

---

## Quick-Start Blueprint — Get Running in 2 Minutes

### Option A: Docker (recommended — zero local dependencies)

```bash
git clone <your-fork-url> elvex-nexus
cd elvex-nexus

# Boots Postgres + pgvector, runs migrations, seeds demo data
# (Alice / Bob / Carol), and starts Gunicorn on :8000 — no API keys needed.
docker compose up --build
```

```bash
# In a second terminal — confirm it's alive
curl http://localhost:8000/api/health/
# {"status": "ok"}
```

Want real LLM scoring instead of deterministic mock scores?

```bash
LLM_BACKEND=openai OPENAI_API_KEY=sk-... docker compose up --build
# or
LLM_BACKEND=anthropic ANTHROPIC_API_KEY=sk-ant-... docker compose up --build
```

Want automatic failover if the primary provider goes down?

```bash
# OpenAI primary, Anthropic fallback
LLM_BACKEND=openai OPENAI_API_KEY=sk-... \
  LLM_BACKEND_FALLBACK=anthropic ANTHROPIC_API_KEY=sk-ant-... \
  docker compose up --build

# Anthropic primary, OpenAI fallback
LLM_BACKEND=anthropic ANTHROPIC_API_KEY=sk-ant-... \
  LLM_BACKEND_FALLBACK=openai OPENAI_API_KEY=sk-... \
  docker compose up --build
```

Scores produced via the fallback are stamped `is_evaluated_via_fallback=True` and surfaced in the LLM Resilience chart on the Dashboard.

### Option B: Makefile (Docker under the hood, fewer keystrokes)

```bash
make bootstrap
# → builds, starts, waits for healthcheck, seeds demo data, opens the browser
```

With a real LLM backend:

```bash
LLM_BACKEND=openai OPENAI_API_KEY=sk-... make bootstrap
# or
LLM_BACKEND=anthropic ANTHROPIC_API_KEY=sk-ant-... make bootstrap
```

With automatic failover:

```bash
# OpenAI primary, Anthropic fallback
LLM_BACKEND=openai OPENAI_API_KEY=sk-... \
  LLM_BACKEND_FALLBACK=anthropic ANTHROPIC_API_KEY=sk-ant-... \
  make bootstrap

# Anthropic primary, OpenAI fallback
LLM_BACKEND=anthropic ANTHROPIC_API_KEY=sk-ant-... \
  LLM_BACKEND_FALLBACK=openai OPENAI_API_KEY=sk-... \
  make bootstrap
```

```bash
make logs-app     # tail Django/Gunicorn logs
make shell        # bash inside the app container
make test         # full pytest suite (unit + integration + BDD)
```

### Frontend dev server (hot-reload against the Dockerized backend)

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000  (proxies /api/* to http://localhost:8000)
```

### Reset demo data at any point

```bash
docker compose run --rm app python manage.py seed_demo --purge
docker compose run --rm app python manage.py seed_demo
```

---

## Where to go next

* **`RUNTIME_SETUP.md`** — full local (non-Docker) onboarding: virtualenv, Postgres, env vars, migrations, and the Vite dev server, step by step.
* **`ARCHITECTURE_DECISIONS.md`** — the engineering rationale behind Markdown-first job ingestion, the PDF parser failover chain, and the vector embedding lifecycle.
* **`CLAUDE.md`** — command reference for running tests (`pytest -m unit`, `pytest -m bdd`, `npm run cy:run`, etc.) and a map of the pipeline architecture.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 4.2 + Django REST Framework |
| Database | PostgreSQL 16 + `pgvector` |
| PDF Parsing | `pymupdf` (primary), `pdfplumber` (fallback) |
| NLP | spaCy (`en_core_web_sm`) |
| LLM Integration | `instructor` (structured output), `openai`, `anthropic`, `tenacity` (retries) |
| Frontend | React 18 + Vite |
| Frontend Testing | Vitest, React Testing Library, Playwright, Cypress |
| Backend Testing | pytest, pytest-django, pytest-bdd |
