# Runtime Setup — Onboarding Guide

This is the from-zero, no-Docker path: a real Python virtualenv, a real local PostgreSQL instance, and a real Vite dev server. If you just want the app running with the least effort, use `docker compose up --build` from the README instead — this guide is for when you need to step through the Django app or frontend with a debugger attached.

> The repository does not currently ship an `.env.example` file. The **Environment Variables** section below documents every variable the app reads, with working local-dev defaults — copy the block in step 4 verbatim into your own `.env` (or export the variables directly; `.env` is already in `.gitignore`).

---

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | **3.11** | Matches the `python:3.11-slim` base image used in `Dockerfile`; other 3.11.x patch versions are fine. |
| PostgreSQL | **16**, with the **pgvector** extension | `docker-compose.yml` runs `pgvector/pgvector:pg16` — match that locally for embedding storage to work without code changes. |
| Node.js | **20 LTS or newer** | Required by Vite 8 / Vitest 1.6 in `frontend/package.json`. |
| npm | Bundled with Node 20+ | Used for all frontend package management and scripts. |
| `pip` | Bundled with Python 3.11 | — |

> **macOS:** `brew install postgresql@16 pgvector node`
> **Ubuntu/Debian:** Install PostgreSQL 16 from the [PGDG apt repository](https://www.postgresql.org/download/linux/ubuntu/), then build/install `pgvector` per its [README](https://github.com/pgvector/pgvector#installation). Install Node via [nodesource](https://github.com/nodesource/distributions) or `nvm`.

---

## Backend Setup

### 1. Clone and create a virtual environment

```bash
git clone <your-fork-url> elvex-nexus
cd elvex-nexus

python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 2. Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> `requirements.txt` pulls the `en_core_web_sm` spaCy model directly from a GitHub release URL — no separate `python -m spacy download` step is needed. `psycopg2-binary` bundles its own `libpq`, so no system Postgres client headers are required just to install dependencies.

### 3. Stand up PostgreSQL with the pgvector extension

```bash
# Start your local Postgres 16 instance, then:
createdb elvex_nexus
psql -d elvex_nexus -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Create a dedicated role matching the Docker Compose defaults (optional but
# keeps your DATABASE_URL consistent with the rest of this guide):
psql -d elvex_nexus -c "CREATE USER elvex WITH PASSWORD 'elvex_dev_password';"
psql -d elvex_nexus -c "GRANT ALL PRIVILEGES ON DATABASE elvex_nexus TO elvex;"
```

### 4. Configure environment variables

Create a `.env` file at the repository root (it's already excluded from version control):

```bash
cat > .env << 'EOF'
# ── Django core ──────────────────────────────────────────────────────────
DJANGO_SETTINGS_MODULE=config.settings.local
DJANGO_SECRET_KEY=insecure-dev-secret-change-in-prod
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
IS_PRODUCTION=false

# ── Database ─────────────────────────────────────────────────────────────
DATABASE_URL=postgres://elvex:elvex_dev_password@localhost:5432/elvex_nexus

# ── LLM backend ──────────────────────────────────────────────────────────
# "mock" requires no API key and returns deterministic scores — start here.
LLM_BACKEND=mock
LLM_BACKEND_FALLBACK=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# ── Logging ──────────────────────────────────────────────────────────────
DJANGO_LOG_LEVEL=INFO
EOF
```

Load it into your shell (or use `direnv` / `python-dotenv` if you prefer not to export manually):

```bash
export $(grep -v '^#' .env | xargs)
```

> Want real LLM scoring instead of the mock backend? Set `LLM_BACKEND=openai` and `OPENAI_API_KEY=sk-...`, or `LLM_BACKEND=anthropic` and `ANTHROPIC_API_KEY=sk-ant-...`. Set both `LLM_BACKEND` and `LLM_BACKEND_FALLBACK` to enable automatic failover between providers.

### 5. Run migrations and seed demo data

```bash
python manage.py migrate
python manage.py seed_demo
# Populates three demo candidates (Alice / Bob / Carol) against a sample
# "Senior Backend Engineer" job so the dashboard isn't empty on first load.
```

To wipe and re-seed at any point:

```bash
python manage.py seed_demo --purge
python manage.py seed_demo
```

### 6. Launch the server

```bash
python manage.py runserver 0.0.0.0:8000
```

```bash
# Confirm it's up
curl http://localhost:8000/api/health/
# {"status": "ok"}
```

---

## Frontend Setup

### 1. Navigate to the client folder

```bash
cd frontend
```

### 2. Install dependencies

```bash
npm install
```

### 3. Configure environment variables

The frontend talks to the backend through Vite's dev-server proxy (configured in `frontend/vite.config.js`) — `/api/*` requests are forwarded to `http://localhost:8000` automatically, so **no frontend-side environment variables are required** for local development against the backend you started in step 6 above.

If you need to point the frontend at a different backend host (e.g., a staging API), override the proxy target:

```bash
cat > .env.local << 'EOF'
VITE_API_PROXY_TARGET=http://localhost:8000
EOF
```

> `VITE_API_PROXY_TARGET` is not currently read by `vite.config.js` — the proxy target is hardcoded to `http://localhost:8000`. If you need a configurable target, update the `server.proxy['/api'].target` value in `frontend/vite.config.js` to read `process.env.VITE_API_PROXY_TARGET`.

### 4. Run the Vite dev server

```bash
npm run dev
```

```
  VITE v8.x.x  ready in 312 ms

  ➜  Local:   http://localhost:3000/
  ➜  Network: use --host to expose
```

Open `http://localhost:3000` — you should see the dashboard populated with the seeded demo data from step 5.

### 5. Frontend test commands (for reference)

```bash
npm test              # Vitest unit tests, one-shot
npm run test:watch    # Vitest in watch mode
npm run cy:open       # Cypress interactive
npm run cy:run        # Cypress headless
npm run e2e           # Playwright E2E suite
```

---

## Verifying the Full Stack

With both servers running (Django on `:8000`, Vite on `:3000`):

1. Visit `http://localhost:3000` — the dashboard should show 3 seeded applications with statuses already computed.
2. `POST` a new job via the UI's job ingestion modal, or directly:

   ```bash
   curl -X POST http://localhost:8000/api/jobs/ \
     -H "Content-Type: application/json" \
     -d '{
       "raw_markdown": "# Staff Platform Engineer\n\n## Description\nOwns the core data platform.\n\n## Requirements\n### Required Skills\n- Python\n- Kubernetes\n### Minimum Experience\n6 years\n\n## Must Haves\n### min_experience\ntype: years_experience\nminimum_years: 6\n"
     }'
   ```

3. Confirm the new job appears in the dashboard's job list without a page reload requiring a backend restart.

---

## Running the Backend Test Suite

```bash
pytest                          # everything
pytest -m unit                  # fast, no DB, no network
pytest -m integration           # real ORM against SQLite
pytest -m bdd                   # Gherkin outer-loop scenarios
pytest --cov --cov-report=html  # with coverage
```

Tests run against `config.settings.test` (SQLite, pgvector stubbed out as a JSON field) — you do not need your local PostgreSQL instance running to run the test suite.

---

## Troubleshooting

* **`django.db.utils.OperationalError: could not connect to server`** — your local Postgres isn't running, or `DATABASE_URL` in `.env` doesn't match your actual user/password/port. Double-check with `psql "$DATABASE_URL"`.
* **`ImportError` mentioning `vector` extension** — you skipped `CREATE EXTENSION IF NOT EXISTS vector;` in step 3, or your Postgres build doesn't have pgvector installed.
* **`ModuleNotFoundError: No module named 'en_core_web_sm'`** — the spaCy model wheel failed to download during `pip install -r requirements.txt` (often a network/proxy issue). Retry the install, or run `pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl` directly.
* **Frontend shows a blank dashboard with network errors in the console** — confirm the Django server is actually running on `:8000` and `curl http://localhost:8000/api/health/` returns `{"status": "ok"}` before assuming a frontend bug.
