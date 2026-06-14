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
#   libpq5  — psycopg2 shared library
#   curl    — Docker HEALTHCHECK probe
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
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
