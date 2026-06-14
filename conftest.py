"""
Root conftest.py — shared fixtures and pytest-bdd configuration.

Loaded automatically by pytest before any test or feature file runs.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# pytest-bdd — bulk bind all scenarios in all feature files.
# Comment this out to use explicit @scenario decorators instead.
# ---------------------------------------------------------------------------

# from pytest_bdd import scenarios
# scenarios("features/")   # ← uncomment when all step definitions are complete


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx() -> dict:
    """
    Shared state container passed between BDD step definitions.

    Each scenario gets a fresh dict. Steps store intermediate values here
    instead of module-level globals (which would bleed between scenarios).
    """
    return {}


@pytest.fixture(autouse=False)
def fresh_observability():
    """
    Provides a clean PipelineObservability instance with cleared records.

    Use in tests that assert on latency records to avoid cross-test pollution.
    """
    from resume_pipeline.observability import pipeline_observability
    pipeline_observability.clear()
    yield pipeline_observability
    pipeline_observability.clear()
