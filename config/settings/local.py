"""
Local development settings.

Reads DATABASE_URL from environment (set by docker-compose.yml).
Requires PostgreSQL + pgvector.
"""

import os

from config.settings.base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# ---------------------------------------------------------------------------
# Database — PostgreSQL + pgvector
# ---------------------------------------------------------------------------

import dj_database_url  # noqa: E402  (installed via requirements.txt)

_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgres://elvex:elvex_dev_password@localhost:5432/elvex_nexus",
)

DATABASES = {
    "default": dj_database_url.parse(_DATABASE_URL, conn_max_age=60),
}

# ---------------------------------------------------------------------------
# Audit / pipeline logging — structured JSON to stdout
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json_line": {
            "()": "django.utils.log.ServerFormatter",
            "format": "%(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json_line",
        },
    },
    "loggers": {
        "pipeline.audit": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
        },
    },
}

# ---------------------------------------------------------------------------
# Pipeline flags
# ---------------------------------------------------------------------------

IS_PRODUCTION = os.environ.get("IS_PRODUCTION", "false").lower() == "true"
LLM_BACKEND = os.environ.get("LLM_BACKEND", "mock")
