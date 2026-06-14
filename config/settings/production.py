"""
Production settings.

All secrets via environment variables — never hardcoded.
"""

import os

from config.settings.base import *  # noqa: F401, F403

DEBUG = False
IS_PRODUCTION = True

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # hard fail if absent
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

import dj_database_url  # noqa: E402

DATABASES = {
    "default": dj_database_url.parse(
        os.environ["DATABASE_URL"],  # hard fail if absent
        conn_max_age=60,
        ssl_require=True,
    ),
}

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# ---------------------------------------------------------------------------
# Structured audit logging
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
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
            "level": "WARNING",
        },
    },
}

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

LLM_BACKEND = os.environ.get("LLM_BACKEND", "openai")
