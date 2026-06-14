#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Docker entrypoint — Elvex Nexus application container
#
# Execution order (fully automated, single-command bootstrap):
#
#   0. Ensure writable media directory exists
#   1. Wait for the PostgreSQL database to accept connections
#   2. Validate LLM backend configuration (warn on missing keys / no-op fallback)
#   3. Apply all pending Django migrations
#   4. Seed the database with demo data  (idempotent — safe on every restart)
#   5. Hand off to Gunicorn
#
# Environment variables (all have defaults):
#   DJANGO_SETTINGS_MODULE  — defaults to config.settings.local
#   GUNICORN_WORKERS        — defaults to 2
#   GUNICORN_TIMEOUT        — defaults to 120 s
#   DJANGO_LOG_LEVEL        — defaults to info
#   LLM_BACKEND             — "mock" | "openai" | "anthropic"  (default: mock)
#   LLM_BACKEND_FALLBACK    — optional secondary provider; when set and different
#                             from LLM_BACKEND, activates FallbackLLMBackend
# ---------------------------------------------------------------------------

set -euo pipefail

# ---------------------------------------------------------------------------
# 0. Media directory guard
#
# Gap 2 defence-in-depth: even if this container is started with `docker run`
# (no compose, no named volume), the write path must exist.  In the normal
# docker-compose flow the named volume `local_resume_media` is mounted at
# /app/media/resumes and this mkdir is a no-op, but it prevents a silent
# "No such file or directory" crash on the first PDF upload attempt in any
# other deployment configuration.
#
# `|| true` is intentional: if the bind-mount at /app is owned by a host UID
# that differs from appuser's UID, mkdir on the parent may fail — the named
# volume already provides the writable directory in that case, so we suppress
# the error rather than aborting the boot sequence.
# ---------------------------------------------------------------------------
echo "[entrypoint] Ensuring media directories exist..."
mkdir -p /app/media/resumes 2>/dev/null || true

# ---------------------------------------------------------------------------
# 1. Database readiness probe
#
# docker-compose `depends_on: db: condition: service_healthy` fires once the
# pg_isready healthcheck passes, but the TCP port being open does not
# guarantee Django can obtain a connection (e.g., during pgvector extension
# initialisation).  This probe retries with a clean error message rather than
# letting migrate fail with a cryptic connection-refused traceback.
# ---------------------------------------------------------------------------
echo "[entrypoint] Waiting for database..."
python - <<'PYEOF'
import os, sys, time

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.local"),
)

import django
django.setup()

from django.db import connections
from django.db.utils import OperationalError

MAX_RETRIES = 30
SLEEP_SECONDS = 2

for attempt in range(1, MAX_RETRIES + 1):
    try:
        connections["default"].ensure_connection()
        print(f"[entrypoint] Database ready after {attempt} attempt(s).")
        sys.exit(0)
    except OperationalError as exc:
        print(
            f"[entrypoint] Database not ready ({exc}) — "
            f"retry {attempt}/{MAX_RETRIES} in {SLEEP_SECONDS}s..."
        )
        time.sleep(SLEEP_SECONDS)

print("[entrypoint] FATAL: database did not become reachable in time.", file=sys.stderr)
sys.exit(1)
PYEOF

# ---------------------------------------------------------------------------
# 2. LLM backend validation
#
# Warn on obvious misconfiguration before the app starts serving requests.
# These are non-fatal warnings — the server still starts so operators can
# correct the env vars and restart without a full image rebuild.
#
# Checks:
#   a) LLM_BACKEND=openai without OPENAI_API_KEY
#   b) LLM_BACKEND=anthropic without ANTHROPIC_API_KEY
#   c) LLM_BACKEND_FALLBACK=openai without OPENAI_API_KEY
#   d) LLM_BACKEND_FALLBACK=anthropic without ANTHROPIC_API_KEY
#   e) LLM_BACKEND_FALLBACK set to the same value as LLM_BACKEND (no-op)
# ---------------------------------------------------------------------------
echo "[entrypoint] Validating LLM backend configuration..."

_LLM_BACKEND="${LLM_BACKEND:-mock}"
_LLM_FALLBACK="${LLM_BACKEND_FALLBACK:-}"

_check_key() {
    local provider="$1" key_var="$2" role="$3"
    if [ "$provider" = "openai" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
        echo "[entrypoint] WARNING: ${role}=openai but OPENAI_API_KEY is not set — rubric scoring will fail at runtime." >&2
    fi
    if [ "$provider" = "anthropic" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
        echo "[entrypoint] WARNING: ${role}=anthropic but ANTHROPIC_API_KEY is not set — rubric scoring will fail at runtime." >&2
    fi
}

_check_key "$_LLM_BACKEND"  "" "LLM_BACKEND"
if [ -n "$_LLM_FALLBACK" ]; then
    _check_key "$_LLM_FALLBACK" "" "LLM_BACKEND_FALLBACK"
    if [ "$_LLM_FALLBACK" = "$_LLM_BACKEND" ]; then
        echo "[entrypoint] WARNING: LLM_BACKEND_FALLBACK='${_LLM_FALLBACK}' equals LLM_BACKEND — fallback wrapper will not be created (same-provider guard)." >&2
    else
        echo "[entrypoint] LLM resilience: primary=${_LLM_BACKEND}, fallback=${_LLM_FALLBACK} (FallbackLLMBackend active)"
    fi
else
    echo "[entrypoint] LLM backend: ${_LLM_BACKEND} (single-provider mode, no fallback)"
fi

# ---------------------------------------------------------------------------
# 3. Migrations
#
# --noinput suppresses any interactive prompts (safe in CI and container boot).
# Migrations are idempotent; re-running on a fully-migrated database is a
# fast no-op.
# ---------------------------------------------------------------------------
echo "[entrypoint] Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "[entrypoint] Applying migrations..."
python manage.py migrate --noinput

# ---------------------------------------------------------------------------
# 4. Demo data seeding  (M0.6 — idempotent via get_or_create)
#
# Inserts the three canonical demo records (Alice / Bob / Carol) that the
# smoke test and the reviewer workflow depend on.  Uses natural-key
# get_or_create throughout, so repeated calls on an already-seeded database
# produce zero new rows and emit a clean "already up to date" log line.
# ---------------------------------------------------------------------------
echo "[entrypoint] Seeding demo data..."
python manage.py seed_demo

# ---------------------------------------------------------------------------
# 5. Application server
#
# exec replaces the shell process so Gunicorn becomes PID 1 and receives
# SIGTERM cleanly from `docker stop` / `docker compose down`.
# ---------------------------------------------------------------------------
echo "[entrypoint] Starting gunicorn on 0.0.0.0:8000..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --access-logfile - \
    --error-logfile  - \
    --log-level "${DJANGO_LOG_LEVEL:-info}"
