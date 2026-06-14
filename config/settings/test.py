"""
Test settings.

Uses SQLite in-memory so the test suite runs without a PostgreSQL instance.
pgvector models (SectionEmbedding, JobSectionEmbedding) declare their
embedding field as JSONField in models.py for portability — no pgvector
extension is needed in the test environment.
"""

from config.settings.base import *  # noqa: F401, F403

DEBUG = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Faster password hashing in tests.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
