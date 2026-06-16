# ==============================================================================
#  Elvex Nexus — Developer Makefile
#
#  Single-command local bootstrap:
#
#    make bootstrap          Full cold-start: build → up → wait → seed → open
#    make up                 Build and start all services (no seed, no browser)
#    make down               Stop and remove containers (volumes preserved)
#    make clean              Stop containers AND wipe all Docker volumes
#
#  Day-to-day:
#
#    make logs               Tail all service logs
#    make logs-app           Tail Django/Gunicorn log only
#    make shell              Drop into a bash shell inside the app container
#    make shell-db           Drop into psql inside the db container
#    make seed               (Re-)seed demo data  (Alice / Bob / Carol)
#    make createsuperuser    Create admin / admin_dev_password (idempotent)
#    make migrate            Run pending Django migrations
#    make test               Run the full pytest suite (unit + integration + BDD)
#    make test-unit          Fast unit-only pass  (no DB, no network)
#    make test-bdd           BDD outer-loop scenarios only
#    make coverage           pytest with HTML coverage report
#    make test-fe            Vitest unit tests (one-shot)
#    make test-fe-watch      Vitest in watch mode (re-runs on save)
#    make test-fe-coverage   Vitest with V8 HTML coverage report
#    make test-e2e           Playwright E2E suite (auto-starts Vite)
#    make frontend           Start the Vite dev server  (http://localhost:3000)
#    make open               Open the app in the default browser
#    make help               Print this help screen
#
#  LLM Resilience Fallback (optional):
#
#    LLM_BACKEND=openai LLM_BACKEND_FALLBACK=anthropic \
#      OPENAI_API_KEY=sk-... ANTHROPIC_API_KEY=ant-... make bootstrap
#
# ==============================================================================

# ------------------------------------------------------------------------------
# Project-level constants
# ------------------------------------------------------------------------------

# Docker Compose project name (matches the directory name; override via env).
PROJECT          := elvex-nexus

# Compose service names as declared in docker-compose.yml
APP_SERVICE      := app
DB_SERVICE       := db

# Container name that Compose assigns automatically:  <project>-<service>-<index>
APP_CONTAINER    := $(PROJECT)-$(APP_SERVICE)-1
DB_CONTAINER     := $(PROJECT)-$(DB_SERVICE)-1

# Health-check endpoint (used by the wait-gate)
HEALTH_URL       := http://localhost:8000/api/health/

# Frontend dev server URL (Vite)
FRONTEND_URL     := http://localhost:3000

# How long to wait for the app to become healthy (seconds × attempts)
HEALTH_RETRIES   := 30
HEALTH_INTERVAL  := 3

# Django superuser credentials (dev-only; never use in production)
DJANGO_SU_USER   := admin
DJANGO_SU_EMAIL  := admin@elvex.local
DJANGO_SU_PASS   := admin_dev_password

# Detect the host OS to pick the right "open browser" command
UNAME_S          := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
  OPEN_CMD := open
else
  OPEN_CMD := xdg-open
endif

# Compose command — supports both `docker compose` (v2) and legacy `docker-compose`
COMPOSE          := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

# Colour codes for terminal output
BOLD   := \033[1m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
CYAN   := \033[0;36m
RESET  := \033[0m

# ------------------------------------------------------------------------------
# .PHONY — prevents make from confusing targets with files of the same name
# ------------------------------------------------------------------------------
.PHONY: \
  bootstrap up down clean \
  wait-healthy seed createsuperuser migrate \
  logs logs-app shell shell-db \
  ensure-running validate-llm \
  test test-unit test-bdd coverage \
  frontend frontend-bg open \
  test-fe test-fe-watch test-fe-coverage test-e2e \
  fe-install \
  help

# ------------------------------------------------------------------------------
# Default target
# ------------------------------------------------------------------------------
.DEFAULT_GOAL := help

# ==============================================================================
#  PRIMARY TARGETS
# ==============================================================================

## bootstrap  |  Full cold-start: build → up → wait → seed → admin → frontend → browser
bootstrap: validate-llm down up wait-healthy seed createsuperuser frontend-bg open
	@printf "$(GREEN)$(BOLD)✓ Bootstrap complete.$(RESET)\n"
	@printf "  Backend:  http://localhost:8000\n"
	@printf "  Frontend: $(FRONTEND_URL)\n"
	@printf "  Admin:    http://localhost:8000/admin  [$(DJANGO_SU_USER) / $(DJANGO_SU_PASS)]\n"

## validate-llm  |  Warn if LLM_BACKEND env vars are misconfigured (non-fatal)
validate-llm:
	@_backend="$${LLM_BACKEND:-mock}"; \
	_fallback="$${LLM_BACKEND_FALLBACK:-}"; \
	_ok=1; \
	if [ "$$_backend" = "openai" ] && [ -z "$${OPENAI_API_KEY:-}" ]; then \
	  printf "$(YELLOW)$(BOLD)⚠  LLM_BACKEND=openai but OPENAI_API_KEY is not set — rubric scoring will fail.$(RESET)\n" >&2; \
	  _ok=0; \
	fi; \
	if [ "$$_backend" = "anthropic" ] && [ -z "$${ANTHROPIC_API_KEY:-}" ]; then \
	  printf "$(YELLOW)$(BOLD)⚠  LLM_BACKEND=anthropic but ANTHROPIC_API_KEY is not set — rubric scoring will fail.$(RESET)\n" >&2; \
	  _ok=0; \
	fi; \
	if [ -n "$$_fallback" ]; then \
	  if [ "$$_fallback" = "openai" ] && [ -z "$${OPENAI_API_KEY:-}" ]; then \
	    printf "$(YELLOW)$(BOLD)⚠  LLM_BACKEND_FALLBACK=openai but OPENAI_API_KEY is not set.$(RESET)\n" >&2; \
	    _ok=0; \
	  fi; \
	  if [ "$$_fallback" = "anthropic" ] && [ -z "$${ANTHROPIC_API_KEY:-}" ]; then \
	    printf "$(YELLOW)$(BOLD)⚠  LLM_BACKEND_FALLBACK=anthropic but ANTHROPIC_API_KEY is not set.$(RESET)\n" >&2; \
	    _ok=0; \
	  fi; \
	  if [ "$$_fallback" = "$$_backend" ]; then \
	    printf "$(YELLOW)$(BOLD)⚠  LLM_BACKEND_FALLBACK equals LLM_BACKEND ('$$_backend') — fallback will be a no-op.$(RESET)\n" >&2; \
	  fi; \
	fi; \
	if [ "$$_ok" = "1" ] && [ -z "$$_fallback" ]; then \
	  printf "$(GREEN)✓ LLM backend: $$_backend (single-provider, no fallback)$(RESET)\n"; \
	elif [ "$$_ok" = "1" ]; then \
	  printf "$(GREEN)✓ LLM backend: $$_backend → fallback: $$_fallback$(RESET)\n"; \
	fi

## up          |  Build images and start all services in the background
up:
	@printf "$(CYAN)$(BOLD)▶ Building images and starting services...$(RESET)\n"
	@$(COMPOSE) up --build --detach
	@printf "$(GREEN)✓ Services started.$(RESET)\n"

## down        |  Stop and remove containers (volumes are preserved)
down:
	@printf "$(CYAN)$(BOLD)▶ Bringing down containers...$(RESET)\n"
	@$(COMPOSE) down --remove-orphans
	@printf "$(GREEN)✓ Containers removed.$(RESET)\n"

## clean       |  Stop containers AND delete all Docker volumes (full wipe)
clean:
	@printf "$(YELLOW)$(BOLD)⚠ Wiping containers and volumes...$(RESET)\n"
	@$(COMPOSE) down --volumes --remove-orphans
	@printf "$(GREEN)✓ Volumes wiped.$(RESET)\n"

# ==============================================================================
#  WAIT GATE
# ==============================================================================

## wait-healthy  |  Block until /api/health/ returns HTTP 200
wait-healthy:
	@printf "$(CYAN)$(BOLD)▶ Waiting for app to become healthy ($(HEALTH_URL))...$(RESET)\n"
	@attempt=1; \
	while [ $$attempt -le $(HEALTH_RETRIES) ]; do \
	  status=$$(curl -s -o /dev/null -w "%{http_code}" $(HEALTH_URL) 2>/dev/null); \
	  if [ "$$status" = "200" ]; then \
	    printf "$(GREEN)✓ App healthy after $$attempt attempt(s).$(RESET)\n"; \
	    exit 0; \
	  fi; \
	  printf "  [$$attempt/$(HEALTH_RETRIES)] status=$$status — retrying in $(HEALTH_INTERVAL)s...\n"; \
	  sleep $(HEALTH_INTERVAL); \
	  attempt=$$((attempt + 1)); \
	done; \
	printf "$(YELLOW)$(BOLD)✗ App did not become healthy in time.$(RESET)\n"; \
	printf "  Run 'make logs-app' to inspect the startup output.\n"; \
	exit 1

# ==============================================================================
#  DATA & ADMIN
# ==============================================================================

## seed          |  (Re-)seed demo data inside the running app container
seed:
	@printf "$(CYAN)$(BOLD)▶ Seeding demo data...$(RESET)\n"
	@docker exec $(APP_CONTAINER) python manage.py seed_demo
	@printf "$(GREEN)✓ Demo data seeded (Alice / Bob / Carol).$(RESET)\n"

## createsuperuser  |  Create Django superuser admin/admin_dev_password (idempotent)
createsuperuser:
	@printf "$(CYAN)$(BOLD)▶ Provisioning superuser '$(DJANGO_SU_USER)'...$(RESET)\n"
	@docker exec $(APP_CONTAINER) \
	  python -c "import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local'); django.setup(); from django.contrib.auth import get_user_model; User = get_user_model(); u, created = User.objects.get_or_create(username='$(DJANGO_SU_USER)', defaults={'email': '$(DJANGO_SU_EMAIL)', 'is_staff': True, 'is_superuser': True}); [u.set_password('$(DJANGO_SU_PASS)'), u.save()] if created else None; print('created' if created else 'already exists')"
	@printf "$(GREEN)✓ Superuser ready: $(DJANGO_SU_USER) / $(DJANGO_SU_PASS)$(RESET)\n"

## migrate       |  Run pending Django migrations inside the running app container
migrate:
	@printf "$(CYAN)$(BOLD)▶ Running migrations...$(RESET)\n"
	@docker exec $(APP_CONTAINER) python manage.py migrate --noinput
	@printf "$(GREEN)✓ Migrations applied.$(RESET)\n"

# ==============================================================================
#  LOGS & SHELLS
# ==============================================================================

## logs          |  Tail all service logs  (Ctrl-C to exit)
logs:
	@$(COMPOSE) logs --follow

## logs-app      |  Tail the Django/Gunicorn log only  (Ctrl-C to exit)
logs-app:
	@$(COMPOSE) logs --follow $(APP_SERVICE)

## shell         |  Open a bash shell inside the running app container
shell:
	@docker exec -it $(APP_CONTAINER) bash

## shell-db      |  Open a psql session inside the running db container
shell-db:
	@docker exec -it $(DB_CONTAINER) \
	  psql -U elvex -d elvex_nexus

# ==============================================================================
#  TESTING
# ==============================================================================

# Internal guard: start the stack automatically if the app container is not
# already running.  Not listed in `make help` (no ## prefix).
# Used as a prerequisite by all targets that call `docker exec $(APP_CONTAINER)`.
ensure-running:
	@if ! docker ps --filter "name=^/$(APP_CONTAINER)$$" --filter "status=running" \
	      --format "{{.Names}}" | grep -q "$(APP_CONTAINER)"; then \
	  printf "$(YELLOW)$(BOLD)⚠ $(APP_CONTAINER) is not running — starting stack...$(RESET)\n"; \
	  $(MAKE) up wait-healthy; \
	fi

## test          |  Run the full pytest suite (unit + integration + BDD)
test: ensure-running
	@printf "$(CYAN)$(BOLD)▶ Running full test suite...$(RESET)\n"
	@docker exec $(APP_CONTAINER) pytest

## test-unit     |  Fast unit-only pass  (no DB, no network)
test-unit: ensure-running
	@printf "$(CYAN)$(BOLD)▶ Running unit tests...$(RESET)\n"
	@docker exec $(APP_CONTAINER) pytest -m unit

## test-bdd      |  BDD outer-loop scenarios only
test-bdd: ensure-running
	@printf "$(CYAN)$(BOLD)▶ Running BDD scenarios...$(RESET)\n"
	@docker exec $(APP_CONTAINER) pytest -m bdd

## coverage      |  pytest with HTML coverage report  (opens htmlcov/index.html)
coverage: ensure-running
	@printf "$(CYAN)$(BOLD)▶ Running tests with coverage...$(RESET)\n"
	@docker exec $(APP_CONTAINER) pytest --cov --cov-report=html
	@printf "$(GREEN)✓ Report written to htmlcov/index.html$(RESET)\n"
	@$(OPEN_CMD) htmlcov/index.html 2>/dev/null || true

# ==============================================================================
#  FRONTEND
# ==============================================================================

## frontend      |  Start the Vite dev server in the foreground  (http://localhost:3000)
frontend:
	@printf "$(CYAN)$(BOLD)▶ Starting Vite dev server...$(RESET)\n"
	@cd frontend && npm run dev

## frontend-bg   |  Start the Vite dev server in the background and wait until ready
frontend-bg:
	@printf "$(CYAN)$(BOLD)▶ Starting Vite dev server in background...$(RESET)\n"
	@cd frontend && npm run dev &
	@attempt=1; \
	while [ $$attempt -le 20 ]; do \
	  if curl -s -o /dev/null -w "%{http_code}" $(FRONTEND_URL) 2>/dev/null | grep -q "200\|304"; then \
	    printf "$(GREEN)✓ Frontend ready at $(FRONTEND_URL)$(RESET)\n"; \
	    exit 0; \
	  fi; \
	  printf "  [$$attempt/20] waiting for frontend...\n"; \
	  sleep 1; \
	  attempt=$$((attempt + 1)); \
	done; \
	printf "$(YELLOW)⚠ Frontend did not respond in time — it may still be starting.$(RESET)\n"

## fe-install    |  Install frontend npm dependencies (auto-run by test targets)
fe-install: frontend/node_modules/.install-stamp

# Stamp file: re-runs npm install only when package.json changes.
# Not in .PHONY so Make can compare file timestamps.
frontend/node_modules/.install-stamp: frontend/package.json
	@printf "$(CYAN)$(BOLD)▶ Installing frontend dependencies...$(RESET)\n"
	@cd frontend && npm install
	@printf "$(CYAN)$(BOLD)▶ Installing Playwright browsers...$(RESET)\n"
	@cd frontend && npx playwright install --with-deps chromium
	@touch frontend/node_modules/.install-stamp
	@printf "$(GREEN)✓ Frontend dependencies ready.$(RESET)\n"

## test-fe       |  Run Vitest unit tests (one-shot, no watch)
test-fe: fe-install
	@printf "$(CYAN)$(BOLD)▶ Running frontend unit tests (Vitest)...$(RESET)\n"
	@cd frontend && npm run test
	@printf "$(GREEN)✓ Frontend unit tests complete.$(RESET)\n"

## test-fe-watch  |  Run Vitest in watch mode  (re-runs on file save)
test-fe-watch: fe-install
	@printf "$(CYAN)$(BOLD)▶ Starting Vitest in watch mode...$(RESET)\n"
	@cd frontend && npm run test:watch

## test-fe-coverage  |  Vitest with V8 HTML coverage report
test-fe-coverage: fe-install
	@printf "$(CYAN)$(BOLD)▶ Running frontend tests with coverage...$(RESET)\n"
	@cd frontend && npm run coverage
	@printf "$(GREEN)✓ Coverage report written to frontend/coverage/index.html$(RESET)\n"
	@$(OPEN_CMD) frontend/coverage/index.html 2>/dev/null || true

## test-e2e      |  Run Playwright E2E suite (spins up Vite automatically)
test-e2e: fe-install
	@printf "$(CYAN)$(BOLD)▶ Running Playwright E2E tests...$(RESET)\n"
	@cd frontend && npx playwright test
	@printf "$(GREEN)✓ E2E tests complete.$(RESET)\n"

## open          |  Open the frontend in the system default browser
open:
	@printf "$(CYAN)$(BOLD)▶ Opening $(FRONTEND_URL) ...$(RESET)\n"
	@$(OPEN_CMD) $(FRONTEND_URL) 2>/dev/null || \
	  printf "$(YELLOW)  Could not detect a browser launcher. Visit $(FRONTEND_URL) manually.$(RESET)\n"

# ==============================================================================
#  HELP
# ==============================================================================

## help          |  Print available targets (default)
help:
	@printf "\n$(BOLD)Elvex Nexus — Developer Makefile$(RESET)\n\n"
	@printf "$(BOLD)Usage:$(RESET)  make <target>  [VAR=value ...]\n\n"
	@printf "$(BOLD)Targets:$(RESET)\n"
	@awk 'BEGIN { FS = "  \\|  " } \
	      /^## /{ \
	        target=$$1; sub(/^## /,"",target); \
	        desc=$$2; \
	        printf "  $(CYAN)%-22s$(RESET) %s\n", target, desc \
	      }' $(MAKEFILE_LIST)
	@printf "\n$(BOLD)LLM Resilience (optional env vars):$(RESET)\n"
	@printf "  $(CYAN)LLM_BACKEND$(RESET)             Primary provider: mock | openai | anthropic  (default: mock)\n"
	@printf "  $(CYAN)LLM_BACKEND_FALLBACK$(RESET)    Secondary provider for automatic failover\n"
	@printf "  $(CYAN)OPENAI_API_KEY$(RESET)          Required when LLM_BACKEND or FALLBACK = openai\n"
	@printf "  $(CYAN)ANTHROPIC_API_KEY$(RESET)       Required when LLM_BACKEND or FALLBACK = anthropic\n"
	@printf "\n$(BOLD)Example:$(RESET)\n"
	@printf "  LLM_BACKEND=openai LLM_BACKEND_FALLBACK=anthropic \\\\\n"
	@printf "    OPENAI_API_KEY=sk-... ANTHROPIC_API_KEY=ant-... make bootstrap\n\n"
