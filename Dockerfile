# ---------------------------------------------------------------------------
# Elvex Nexus — multi-stage Docker build
#
# Runtime environment variables (set via docker-compose.yml or -e flags):
#
#   LLM_BACKEND          "mock" | "openai" | "anthropic"   (default: mock)
#   LLM_BACKEND_FALLBACK optional secondary provider for automatic failover.
#                        When set and different from LLM_BACKEND, a
#                        FallbackLLMBackend wraps both providers.  Primary
#                        exhausts its tenacity retries first; on failure the
#                        fallback completes the evaluation and stamps
#                        RubricScore.is_evaluated_via_fallback = True.
#                        Leave unset to run in single-provider mode.
#
#   OPENAI_API_KEY       required when LLM_BACKEND or LLM_BACKEND_FALLBACK = "openai"
#   OPENAI_MODEL         (default: gpt-4o-mini)
#   ANTHROPIC_API_KEY    required when LLM_BACKEND or LLM_BACKEND_FALLBACK = "anthropic"
#   ANTHROPIC_MODEL      (default: claude-haiku-4-5-20251001)
#
# ---------------------------------------------------------------------------
# Stage 1: dependency builder
#
# Installs all Python dependencies into an isolated prefix (/install) so the
# runtime image can consume them without pip cache, build tools, or compiler
# toolchains bleeding into the final layer.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# psycopg2-binary bundles its own libpq — no build toolchain needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ---------------------------------------------------------------------------
# Stage 2: runtime image
#
# Lean image — no build tools, only the installed packages copied from Stage 1.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Non-root application user (security hardening).
RUN useradd --create-home --shell /bin/bash appuser

# Runtime-only system deps:
#   libpq5      — psycopg2 shared library
#   curl        — Docker HEALTHCHECK probe
#   libreoffice — headless Word (.doc/.docx) → PDF conversion (`soffice`),
#                 invoked by resume_pipeline/ingestion/word_converter.py.
#                 No pure-Python library renders both legacy .doc and .docx
#                 to PDF with real fidelity on Linux; this is the standard
#                 free/open-source answer to that problem. It's a heavy
#                 package (~500MB) — acceptable here since this is a
#                 batch-processing backend image, not a latency-critical
#                 microservice.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        libreoffice \
    && rm -rf /var/lib/apt/lists/*

# Pull the full Python package tree from the builder.
# This lands everything under /usr/local (bin/, lib/, etc.) so the system
# Python picks it up without any PYTHONPATH manipulation.
COPY --from=builder /install /usr/local


WORKDIR /app

# Copy application source.  The bind-mount (.:/app) in docker-compose.yml
# will shadow this at runtime for local development, but the image stays
# self-contained for CI, staging, and production use.
COPY . .

# Entrypoint lives outside /app so it is never shadowed by the bind-mount.
# Copied from the baked-in source above; chmod makes it executable.
RUN cp /app/scripts/entrypoint.sh /entrypoint.sh && chmod +x /entrypoint.sh

# ---------------------------------------------------------------------------
# Gap 2 fix: media directory ownership
#
# Create /app/media/resumes while still root so the directory exists with
# appuser ownership inside the image.  In docker-compose the named volume
# `local_resume_media` is mounted at this exact path, overlaying the
# bind-mount at /app and giving appuser a writable, Docker-managed directory
# regardless of the host's UID.  This mkdir also serves as the initialisation
# seed for that named volume on first use.
# ---------------------------------------------------------------------------
RUN mkdir -p /app/media/resumes \
    && chown -R appuser:appuser /app

USER appuser

# Gunicorn HTTP port
EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
