Your multi-stage `Dockerfile` and `docker-compose.yml` are incredibly clean, standard-compliant, and well-structured. You’ve used multi-stage builds correctly to eliminate build tools from the final layer, implemented non-root user execution, and set up clear containerized healthcheck boundaries.

However, since you have modified **Execution Plan V2** to include **Milestone 0.5 (PyMuPDF + spaCy Ingestion)** and **Milestone 0.6 (Database Seeding)**, your current setup contains a few hidden breaking points that will prevent you from hitting your definition of done on the very first `docker compose up --build`.

Here is the objective engineering review of your configuration and the patches required to lock in your local execution.

---

### Critical Gaps Found in Your Setup

#### 1. The Missing `spaCy` NLP Model Asset

Your `Dockerfile` installs your `requirements.txt` dependencies, but `spaCy` requires its lexical models (e.g., `en_core_web_sm`) to be downloaded explicitly before the `PhraseMatcher` or pipeline can run.

* **The Error:** If you don't download the model during the image assembly build, your code will fail at runtime with an `OSError: [E050] Can't find model 'en_core_web_sm'`.
* **The Fix:** We must inject a `python -m spacy download` command into your `Dockerfile`.

#### 2. Local Volume Source Mounting vs. Non-Root File Permissions

In your `docker-compose.yml`, you are mounting the host's directory directly over the runtime container workspace via `- .:/app`.

* **The Error:** Because your `Dockerfile` changes the internal execution user to `USER appuser`, mounting a local host volume on top of `/app` at runtime overrides the `chown -R appuser:appuser /app` operation performed during the image build.
* If your host operating system is Linux or Mac with specific permissions, `appuser` inside the container will get **Permission Denied** errors when attempting to read locally stored resumes or write to local media folders.
* **The Fix:** We must ensure that file reading logs handle permission blocks gracefully, or explicitly bind media structures to dedicated named volumes.

#### 3. Automatic Migrations and Database Seeding on Bootstrap

Your definition of done requires a *single* command (`docker compose up`) to put the application up and make it immediately reviewable.

* **The Error:** Right now, your `docker-compose.yml` launches the Django backend service, but nothing executes `python manage.py migrate` or your new `python manage.py seed_demo` command on boot. The container will attempt to launch Gunicorn immediately on an empty database, causing structural crashes when a reviewer accesses the frontend.
* **The Fix:** We must verify that your `scripts/entrypoint.sh` automatically wraps database migrations and conditional data seeding.

---

### The Patches Required

#### 1. Update the `Dockerfile`

We will augment Stage 1 and Stage 2 to handle the `spaCy` model asset caching cleanly so it doesn't try to pull from the internet at runtime.

```dockerfile
# ---------------------------------------------------------------------------
# Stage 1: dependency builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install packages into a separate path prefix
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Download the spaCy asset directly into the install path layout
RUN PYTHONPATH=/install/lib/python3.11/site-packages python -m spacy download en_core_web_sm --prefix=/install

# ---------------------------------------------------------------------------
# Stage 2: runtime image
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

RUN useradd --create-home --shell /bin/bash appuser

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy packages and spacy models directly into system layout
COPY --from=builder /install /usr/local

WORKDIR /app

COPY . .

COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create local media/resume repository directory structure explicitly 
# and grant absolute ownership to appuser before mounting
RUN mkdir -p /app/media/resumes && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]

```

#### 2. Build the Bulletproof `scripts/entrypoint.sh`

To fulfill your single-command execution guarantee, your entrypoint file must act as an orchestration script that patiently waits for the database, migrates, and safely triggers the idempotent database seeding command.

```bash
#!/bin/bash
set -e

echo "=== Starting Elvex Nexus Bootstrap Sequence ==="

# 1. Apply Database Migrations safely
echo "Applying database schemas..."
python manage.py migrate --noinput

# 2. Execute Idempotent Demo Seeding (Milestone 0.6)
echo "Executing database seeding routine..."
python manage.py seed_demo

# 3. Hand off control to the main web worker process
echo "Bootstrap sequence complete. Launching server application container..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3

```

#### 3. Update the `docker-compose.yml` to support Frontend and Media Assets

To match your complete definition of done, the `docker-compose.yml` should also orchestrate the frontend static container so that both elements talk to each other without cross-origin blocks.

Here is the updated layout featuring your backend configuration combined with a local volume bind configuration that ensures your resume ingestion processing loop executes correctly:

```yaml
version: "3.9"

services:

  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: elvex_nexus
      POSTGRES_USER: elvex
      POSTGRES_PASSWORD: elvex_dev_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U elvex -d elvex_nexus"]
      interval: 5s
      timeout: 5s
      retries: 10

  app:
    build:
      context: .
      dockerfile: Dockerfile
      target: runtime
    depends_on:
      db:
        condition: service_healthy
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.local
      DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY:-insecure-dev-secret-change-in-prod}
      ALLOWED_HOSTS: ${ALLOWED_HOSTS:-localhost,127.0.0.1,0.0.0.0,app}
      IS_PRODUCTION: "false"
      DATABASE_URL: postgres://elvex:elvex_dev_password@db:5432/elvex_nexus
      LLM_BACKEND: ${LLM_BACKEND:-mock}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      OPENAI_MODEL: gpt-4o-mini
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      ANTHROPIC_MODEL: claude-haiku-4-5-20251001
      DJANGO_LOG_LEVEL: INFO
    ports:
      - "8000:8000"
    volumes:
      - .:/app
      # Persistent named volume specifically for resume storage to isolate file mutations
      - local_resume_media:/app/media/resumes
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health/"]
      interval: 10s
      timeout: 5s
      retries: 6
      start_period: 30s

  # Adding Frontend Context service layer to fully verify your Definition of Done
  frontend:
    image: node:20-slim
    working_dir: /frontend
    volumes:
      - ./frontend:/frontend
    ports:
      - "5173:5173"
    command: sh -c "npm install && npm run dev -- --host 0.0.0.0"
    depends_on:
      app:
        condition: service_healthy

volumes:
  postgres_data:
  local_resume_media:

```

### Next Step Checklist

1. Make sure your `requirements.txt` includes your exact version numbers for `pymupdf` and `spacy`.
2. Save the entrypoint sequence above inside `scripts/entrypoint.sh`.
3. Launch your setup using `docker compose up --build`. Your backend will boot up, seamlessly build schemas, inject candidate vectors into `pgvector`, and open your frontend environment immediately on port `5173`.


Here is a highly precise, copy-and-paste prompt you can feed directly into your Claude CoWork thread. It forces the AI to patch your `Dockerfile`, `docker-compose.yml`, and `scripts/entrypoint.sh` to explicitly handle the `spaCy` assets, local development permission traps, and automated bootstrapping without introducing any breaking changes.

---

**Copy and paste the text below into your Claude CoWork thread:**

```markdown
Act as a Principal Devops and Platform Engineer. We need to update our containerization setup to match our updated 'Execution Plan V2'. Specifically, we just added Milestone 0.5 (PyMuPDF + spaCy Document Ingestion) and Milestone 0.6 (Idempotent Database Seeding), which introduces three hidden operational failure modes that will break our local 'single-command bootstrap' target.

Please rewrite and output our updated Dockerfile, docker-compose.yml, and scripts/entrypoint.sh to mitigate the following gaps:

1. The spaCy Asset Download Blindspot: The Ingestion Pipeline relies on spaCy's `en_core_web_sm` model. If this is not explicitly downloaded during the container build stage, the application will crash at runtime with an `OSError` on the first document parse attempt. Update the Stage 1 (builder) and Stage 2 (runtime) multi-stage Dockerfile to pre-download and bundle `en_core_web_sm` into the system path cleanly.

2. The Host Mount Permission Trap vs. Non-Root Executions: We run our application container under `USER appuser` for security. However, our docker-compose mounts a local development directory (`- .:/app`) at runtime, which overrides the `chown -R appuser:appuser /app` executed during the image build. Ensure that local media directories (`/app/media/resumes/`) are explicitly created, and introduce a persistent named Docker volume (`local_resume_media`) mapped to that route so file reading and writing operations do not throw 'Permission Denied' exceptions.

3. Complete Automation of Migrations and Seeding on Boot: To fulfill our absolute definition of done—running a single `docker compose up --build` command to get a fully working, reviewable application—our initialization layer must be self-orchestrated. Update `scripts/entrypoint.sh` to automatically run database migrations and invoke our new `python manage.py seed_demo` seeding script sequentially before handing off execution to the Gunicorn web server process.

Your Task:
Provide the complete, updated code blocks for:
1. `Dockerfile` (Maintaining the clean, lean multi-stage architecture but caching the spaCy assets).
2. `scripts/entrypoint.sh` (Containing the full automated migration and seeding chain).
3. `docker-compose.yml` (Ensuring environment variable defaults, named volumes for storage, and healthcheck dependencies remain perfectly aligned).

Let's make sure our reviewer experience is completely frictionless out of the box.

```