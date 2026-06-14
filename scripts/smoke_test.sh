#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Smoke test — validates the running application responds correctly.
#
# Usage:
#   ./scripts/smoke_test.sh [BASE_URL]
#
# Defaults BASE_URL to http://localhost:8000 if not provided.
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed
#
# Prerequisites:
#   - curl (standard on macOS/Linux)
#   - jq   (optional; used for JSON response validation)
#   - A running docker compose stack:  docker compose up -d
# ---------------------------------------------------------------------------

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

_check() {
    local label="$1"
    local result="$2"
    if [ "$result" = "0" ]; then
        echo "[PASS] $label"
        PASS=$((PASS + 1))
    else
        echo "[FAIL] $label"
        FAIL=$((FAIL + 1))
    fi
}

echo "=============================="
echo "Smoke test: $BASE_URL"
echo "=============================="

# ---------------------------------------------------------------------------
# 1. Health endpoint
# ---------------------------------------------------------------------------
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    --max-time 10 \
    "${BASE_URL}/api/health/")
_check "GET /api/health/ returns 200" $([ "$HTTP_STATUS" = "200" ] && echo 0 || echo 1)

# ---------------------------------------------------------------------------
# 2. Applications list endpoint (DRF browsable API)
# ---------------------------------------------------------------------------
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Accept: application/json" \
    --max-time 10 \
    "${BASE_URL}/api/applications/")
_check "GET /api/applications/ returns 2xx" $([ "${HTTP_STATUS:0:1}" = "2" ] && echo 0 || echo 1)

# ---------------------------------------------------------------------------
# 3. Jobs list endpoint
# ---------------------------------------------------------------------------
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Accept: application/json" \
    --max-time 10 \
    "${BASE_URL}/api/jobs/")
_check "GET /api/jobs/ returns 2xx" $([ "${HTTP_STATUS:0:1}" = "2" ] && echo 0 || echo 1)

# ---------------------------------------------------------------------------
# 4. Seed data visible — at least one job seeded
# ---------------------------------------------------------------------------
JOBS_BODY=$(curl -s \
    -H "Accept: application/json" \
    --max-time 10 \
    "${BASE_URL}/api/jobs/" 2>/dev/null || echo '{"count":0}')

if command -v jq &>/dev/null; then
    JOB_COUNT=$(echo "$JOBS_BODY" | jq -r '.count // (.results | length) // 0' 2>/dev/null || echo 0)
    _check "At least 1 job seeded (seed_demo ran)" $([ "$JOB_COUNT" -ge 1 ] && echo 0 || echo 1)
else
    # Fallback: check for "Senior Backend Engineer" string in response
    echo "$JOBS_BODY" | grep -q "Senior Backend Engineer"
    _check "Seed job title visible in /api/jobs/ (jq not installed, grep fallback)" $?
fi

# ---------------------------------------------------------------------------
# 5. Score endpoint reachable (POST with valid payload)
#    Uses the first seeded application if one exists.
# ---------------------------------------------------------------------------
APPS_BODY=$(curl -s \
    -H "Accept: application/json" \
    --max-time 10 \
    "${BASE_URL}/api/applications/" 2>/dev/null || echo '{"results":[]}')

if command -v jq &>/dev/null; then
    FIRST_APP_ID=$(echo "$APPS_BODY" | jq -r '.results[0].id // empty' 2>/dev/null || echo "")
    if [ -n "$FIRST_APP_ID" ]; then
        HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST \
            -H "Content-Type: application/json" \
            -H "Accept: application/json" \
            -d '{"trigger": "smoke_test"}' \
            --max-time 30 \
            "${BASE_URL}/api/applications/${FIRST_APP_ID}/score/")
        _check "POST /api/applications/<id>/score/ returns 2xx" \
            $([ "${HTTP_STATUS:0:1}" = "2" ] && echo 0 || echo 1)
    else
        echo "[SKIP] No applications found — skipping score endpoint check"
    fi
else
    echo "[SKIP] jq not installed — skipping score endpoint check (install jq for full smoke test)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "=============================="
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "=============================="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
