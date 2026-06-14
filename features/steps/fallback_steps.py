"""
BDD step definitions for features/llm_fallback.feature.

All LLM interactions are mocked — no live API calls are made.
Audit events are captured by installing a temporary logging.Handler on
the pipeline.audit logger channel.

Shared context keys (ctx dict)
───────────────────────────────
  resume_parsed        — Alice's structured resume dict
  job_must_haves       — Hard-gate criteria
  job_requirements     — Rubric requirements blob
  primary_backend      — OpenAIRubricBackend (with mocked _client)
  fallback_backend     — AnthropicRubricBackend (with mocked _client)
  fallback_llm_backend — FallbackLLMBackend instance
  rubric_evaluator     — RubricEvaluator wrapping the fallback backend
  audit_events         — list[dict] captured from pipeline.audit logger
  rubric_result        — RubricResult from evaluator.evaluate()
  pipeline_result      — PipelineResult from orchestrator.run()
  raised_exc           — Exception captured when a step expects failure
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from typing import Generator
from unittest.mock import MagicMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from resume_pipeline.logging_module import StructuredAuditLogger
from resume_pipeline.pipeline.fallback_backend import FallbackLLMBackend
from resume_pipeline.pipeline.orchestrator import PipelineInput, PipelineOrchestrator
from resume_pipeline.pipeline.rubric_score import (
    CRITERIA,
    AnthropicRubricBackend,
    OpenAIRubricBackend,
    RubricEvaluator,
    RubricScoreResponse,
    make_rubric_backend,
)

scenarios("llm_fallback.feature")


# ---------------------------------------------------------------------------
# Internal helpers (not steps)
# ---------------------------------------------------------------------------

def _capture_handler(events: list[dict]) -> logging.Handler:
    """Create a logging handler that appends JSON audit records to events."""
    class _H(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            msg = record.getMessage()
            if msg.strip().startswith("{"):
                try:
                    events.append(json.loads(msg))
                except json.JSONDecodeError:
                    pass
    return _H()


def _install_audit_capture(ctx: dict) -> None:
    """Install a capture handler on pipeline.audit and store events in ctx."""
    events: list[dict] = []
    handler = _capture_handler(events)
    log = logging.getLogger("pipeline.audit")
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    ctx["audit_events"] = events
    ctx["_audit_handler"] = handler


def _uninstall_audit_capture(ctx: dict) -> None:
    handler = ctx.pop("_audit_handler", None)
    if handler:
        logging.getLogger("pipeline.audit").removeHandler(handler)


def _valid_rubric_response(score: int = 4) -> RubricScoreResponse:
    return RubricScoreResponse(
        scores={c: score for c in CRITERIA},
        justifications={c: f"Strong evidence found for criterion {c}." for c in CRITERIA},
    )


def _make_openai_backend(model: str = "gpt-4o-mini", max_retries: int = 3) -> OpenAIRubricBackend:
    backend = OpenAIRubricBackend.__new__(OpenAIRubricBackend)
    backend._model = model
    backend._max_retries = max_retries
    backend._client = MagicMock()
    return backend


def _make_anthropic_backend(
    model: str = "claude-haiku-4-5-20251001",
    max_retries: int = 3,
) -> AnthropicRubricBackend:
    backend = AnthropicRubricBackend.__new__(AnthropicRubricBackend)
    backend._model = model
    backend._max_retries = max_retries
    backend._client = MagicMock()
    return backend


# ---------------------------------------------------------------------------
# Background steps
# ---------------------------------------------------------------------------

@given("a valid resume for Alice with 7 years of Python and Django experience")
def alice_resume(ctx: dict) -> None:
    ctx["resume_parsed"] = {
        "total_experience_years": 7,
        "experience": "Senior Python Engineer at Acme 2017-2024. Led Django migration.",
        "skills": "Python Django PostgreSQL Redis Docker Kubernetes REST APIs",
        "education": "BSc Computer Science, UC Berkeley 2016",
        "certifications": ["AWS Solutions Architect Professional"],
    }


@given("a job with must-haves: 5+ years experience, Python, Django")
def job_must_haves(ctx: dict) -> None:
    ctx["job_must_haves"] = {
        "min_experience": {"type": "years_experience", "minimum_years": 5},
        "python_required": {
            "type": "keyword_presence",
            "keywords": ["Python"],
            "sections": ["skills", "experience"],
        },
        "django_required": {
            "type": "keyword_presence",
            "keywords": ["Django"],
            "sections": ["skills", "experience"],
        },
    }
    ctx["job_requirements"] = {
        "required_skills": ["Python", "Django", "PostgreSQL", "REST APIs"],
        "minimum_experience_years": 5,
    }


@given("a mock rubric backend that returns all scores of 4")
def mock_rubric_response(ctx: dict) -> None:
    ctx["_default_valid_response"] = _valid_rubric_response(score=4)


# ---------------------------------------------------------------------------
# Primary backend setup
# ---------------------------------------------------------------------------

@given("the primary LLM backend is OpenAI configured with max_retries 3")
def primary_openai_backend(ctx: dict) -> None:
    ctx["primary_backend"] = _make_openai_backend(model="gpt-4o-mini", max_retries=3)


@given("the OpenAI client raises RateLimitError on every attempt")
def primary_raises_rate_limit(ctx: dict) -> None:
    import openai
    error = openai.RateLimitError(
        "rate limit exceeded",
        response=MagicMock(status_code=429),
        body={},
    )
    ctx["primary_backend"].complete = MagicMock(side_effect=[error])
    ctx["_primary_error_type"] = "RateLimitError"


@given("the OpenAI client raises APITimeoutError on every attempt")
def primary_raises_timeout(ctx: dict) -> None:
    import openai
    error = openai.APITimeoutError(request=MagicMock())
    ctx["primary_backend"].complete = MagicMock(side_effect=[error])
    ctx["_primary_error_type"] = "APITimeoutError"


@given("the OpenAI client raises APIConnectionError on every attempt")
def primary_raises_connection(ctx: dict) -> None:
    import openai
    error = openai.APIConnectionError(request=MagicMock())
    ctx["primary_backend"].complete = MagicMock(side_effect=[error])
    ctx["_primary_error_type"] = "APIConnectionError"


@given("the OpenAI client returns a valid rubric score on the first attempt")
def primary_returns_valid_response(ctx: dict) -> None:
    valid_resp = _valid_rubric_response(score=4)
    ctx["primary_backend"].complete = MagicMock(return_value=valid_resp)


# ---------------------------------------------------------------------------
# Fallback backend setup
# ---------------------------------------------------------------------------

@given("the fallback LLM backend is Anthropic and returns a valid rubric score")
def fallback_anthropic_succeeds(ctx: dict) -> None:
    backend = _make_anthropic_backend(model="claude-haiku-4-5-20251001")
    backend.complete = MagicMock(return_value=_valid_rubric_response(score=3))
    ctx["fallback_backend"] = backend


@given("the fallback LLM backend is Anthropic and also raises an exception")
def fallback_anthropic_fails(ctx: dict) -> None:
    backend = _make_anthropic_backend(model="claude-haiku-4-5-20251001")
    backend.complete = MagicMock(side_effect=[RuntimeError("Anthropic service down")])
    ctx["fallback_backend"] = backend


# ---------------------------------------------------------------------------
# FallbackLLMBackend wiring
# ---------------------------------------------------------------------------

@given("a FallbackLLMBackend is wired with OpenAI as primary and Anthropic as fallback")
def wire_fallback_backend(ctx: dict) -> None:
    ctx["fallback_llm_backend"] = FallbackLLMBackend(
        primary=ctx["primary_backend"],
        fallback=ctx["fallback_backend"],
        # Inject a fresh StructuredAuditLogger so events go to the same channel
        # our capture handler is listening on.
        audit_logger=StructuredAuditLogger(),
    )
    ctx["rubric_evaluator"] = RubricEvaluator(ctx["fallback_llm_backend"])


@given("the pipeline orchestrator uses this FallbackLLMBackend for rubric scoring")
def wire_orchestrator(ctx: dict) -> None:
    semantic_mock = MagicMock()
    sem_result = MagicMock()
    sem_result.final_score = 0.78
    sem_result.section_scores = {"skills": 0.78, "experience": 0.78}
    semantic_mock.evaluate.return_value = sem_result

    ctx["orchestrator"] = PipelineOrchestrator(
        semantic_evaluator=semantic_mock,
        rubric_evaluator=ctx["rubric_evaluator"],
    )


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------

@when("the rubric evaluator runs against Alice's resume")
def run_rubric_evaluator(ctx: dict) -> None:
    _install_audit_capture(ctx)
    try:
        ctx["rubric_result"] = ctx["rubric_evaluator"].evaluate(
            resume_parsed=ctx["resume_parsed"],
            job_requirements=ctx["job_requirements"],
        )
        ctx["raised_exc"] = None
    except Exception as exc:
        ctx["rubric_result"] = None
        ctx["raised_exc"] = exc
    finally:
        _uninstall_audit_capture(ctx)


@when("the rubric evaluator attempts to run against Alice's resume")
def attempt_rubric_evaluator(ctx: dict) -> None:
    run_rubric_evaluator(ctx)


@when("the full pipeline runs for Alice's application")
def run_full_pipeline(ctx: dict) -> None:
    pipeline_input = PipelineInput(
        application_id="bdd-fallback-alice-001",
        job_must_haves=ctx["job_must_haves"],
        resume_parsed=ctx["resume_parsed"],
        candidate_embeddings={"skills": [0.1] * 10, "experience": [0.2] * 10},
        job_embeddings={"skills": [0.11] * 10, "experience": [0.19] * 10},
        lexical_rank=1,
        semantic_rank=1,
        job_requirements=ctx["job_requirements"],
    )
    _install_audit_capture(ctx)
    try:
        ctx["pipeline_result"] = ctx["orchestrator"].run(pipeline_input)
        ctx["raised_exc"] = None
    except Exception as exc:
        ctx["pipeline_result"] = None
        ctx["raised_exc"] = exc
    finally:
        _uninstall_audit_capture(ctx)


@when("make_rubric_backend() is called with no arguments")
def call_make_rubric_backend(ctx: dict) -> None:
    ctx["backend_result"] = make_rubric_backend()


# ---------------------------------------------------------------------------
# Then — rubric result assertions
# ---------------------------------------------------------------------------

@then("the rubric evaluation completes successfully")
def rubric_completes_successfully(ctx: dict) -> None:
    assert ctx.get("raised_exc") is None, (
        f"Expected successful evaluation but got: {ctx['raised_exc']}"
    )
    assert ctx["rubric_result"] is not None


@then("a provider exception is raised")
def provider_exception_raised(ctx: dict) -> None:
    assert ctx.get("raised_exc") is not None, "Expected an exception but evaluation succeeded"


@then(parsers.parse('the RubricResult has is_evaluated_via_fallback set to {flag}'))
def rubric_result_fallback_flag(ctx: dict, flag: str) -> None:
    expected = flag.strip().lower() == "true"
    result = ctx["rubric_result"]
    assert result is not None, "RubricResult is None — evaluation did not complete"
    assert result.is_evaluated_via_fallback is expected, (
        f"Expected is_evaluated_via_fallback={expected}, got {result.is_evaluated_via_fallback}"
    )


# ---------------------------------------------------------------------------
# Then — audit event assertions
# ---------------------------------------------------------------------------

def _events_of_type(ctx: dict, event_type: str) -> list[dict]:
    return [e for e in ctx.get("audit_events", []) if e.get("event") == event_type]


@then(parsers.parse('a "{event_type}" audit event is emitted with provider "{provider}"'))
def audit_event_with_provider(ctx: dict, event_type: str, provider: str) -> None:
    matches = _events_of_type(ctx, event_type)
    assert matches, f"No '{event_type}' audit event found. Events: {[e['event'] for e in ctx.get('audit_events', [])]}"
    assert any(e.get("provider") == provider for e in matches), (
        f"'{event_type}' event found but provider={provider!r} not in {matches}"
    )


@then(parsers.parse('a "{event_type}" audit event is emitted with target_provider "{target}"'))
def audit_event_with_target_provider(ctx: dict, event_type: str, target: str) -> None:
    matches = _events_of_type(ctx, event_type)
    assert matches, f"No '{event_type}' audit event found."
    assert any(e.get("target_provider") == target for e in matches), (
        f"target_provider={target!r} not found in {matches}"
    )


@then(parsers.parse('a "{event_type}" audit event is emitted'))
def audit_event_emitted(ctx: dict, event_type: str) -> None:
    matches = _events_of_type(ctx, event_type)
    assert matches, (
        f"Expected '{event_type}' audit event but none found. "
        f"Seen: {sorted({e['event'] for e in ctx.get('audit_events', [])})}"
    )


@then(parsers.parse('no "{event_type}" event is emitted'))
def no_audit_event(ctx: dict, event_type: str) -> None:
    matches = _events_of_type(ctx, event_type)
    assert not matches, f"Expected no '{event_type}' event but found: {matches}"


@then(parsers.parse('a "primary_llm_failed" event has error_type "{error_type}"'))
def primary_failed_has_error_type(ctx: dict, error_type: str) -> None:
    events = _events_of_type(ctx, "primary_llm_failed")
    assert events, "No primary_llm_failed event found"
    assert any(e.get("error_type") == error_type for e in events), (
        f"error_type={error_type!r} not found. Events: {events}"
    )


@then(parsers.parse('a "fallback_llm_exhausted" event has primary_provider "{provider}"'))
def exhausted_has_primary_provider(ctx: dict, provider: str) -> None:
    events = _events_of_type(ctx, "fallback_llm_exhausted")
    assert events, "No fallback_llm_exhausted event found"
    assert any(e.get("primary_provider") == provider for e in events), str(events)


@then(parsers.parse('a "fallback_llm_exhausted" event has fallback_provider "{provider}"'))
def exhausted_has_fallback_provider(ctx: dict, provider: str) -> None:
    events = _events_of_type(ctx, "fallback_llm_exhausted")
    assert events, "No fallback_llm_exhausted event found"
    assert any(e.get("fallback_provider") == provider for e in events), str(events)


# ---------------------------------------------------------------------------
# Then — orchestrator / pipeline assertions
# ---------------------------------------------------------------------------

@then(parsers.parse('the PipelineResult has is_evaluated_via_fallback set to {flag}'))
def pipeline_result_fallback_flag(ctx: dict, flag: str) -> None:
    expected = flag.strip().lower() == "true"
    result = ctx["pipeline_result"]
    assert result is not None, "PipelineResult is None — pipeline did not complete"
    assert result.is_evaluated_via_fallback is expected, (
        f"Expected PipelineResult.is_evaluated_via_fallback={expected}, "
        f"got {result.is_evaluated_via_fallback}"
    )


@then(parsers.parse('the "score_computed" audit event contains is_evaluated_via_fallback {flag}'))
def score_computed_has_fallback_flag(ctx: dict, flag: str) -> None:
    expected = flag.strip().lower() == "true"
    score_events = _events_of_type(ctx, "score_computed")
    assert score_events, "No score_computed audit event found"
    evt = score_events[-1]
    assert "is_evaluated_via_fallback" in evt, (
        f"score_computed event missing is_evaluated_via_fallback field: {evt}"
    )
    assert evt["is_evaluated_via_fallback"] is expected, (
        f"Expected {expected}, got {evt['is_evaluated_via_fallback']}"
    )


# ---------------------------------------------------------------------------
# Then — factory assertions (Scenario 6)
# ---------------------------------------------------------------------------

@given(parsers.parse('the environment variable LLM_BACKEND is set to "{value}"'))
def set_llm_backend_env(ctx: dict, value: str) -> None:
    ctx.setdefault("_env_overrides", {})["LLM_BACKEND"] = value
    os.environ["LLM_BACKEND"] = value


@given(parsers.parse('the environment variable LLM_BACKEND_FALLBACK is set to "{value}"'))
def set_llm_backend_fallback_env(ctx: dict, value: str) -> None:
    ctx.setdefault("_env_overrides", {})["LLM_BACKEND_FALLBACK"] = value
    os.environ["LLM_BACKEND_FALLBACK"] = value


@then("the returned backend is a FallbackLLMBackend")
def returned_backend_is_fallback(ctx: dict) -> None:
    assert isinstance(ctx["backend_result"], FallbackLLMBackend), (
        f"Expected FallbackLLMBackend, got {type(ctx['backend_result']).__name__}"
    )
    # Clean up env
    for key in ctx.get("_env_overrides", {}):
        os.environ.pop(key, None)


@then(parsers.parse('its primary provider model_name contains "{substring}"'))
def primary_model_contains(ctx: dict, substring: str) -> None:
    backend = ctx["backend_result"]
    assert isinstance(backend, FallbackLLMBackend)
    assert substring.lower() in backend.primary.model_name.lower(), (
        f"Expected '{substring}' in primary model_name '{backend.primary.model_name}'"
    )


@then(parsers.parse('its fallback provider model_name contains "{substring}"'))
def fallback_model_contains(ctx: dict, substring: str) -> None:
    backend = ctx["backend_result"]
    assert isinstance(backend, FallbackLLMBackend)
    assert substring.lower() in backend.fallback_backend.model_name.lower(), (
        f"Expected '{substring}' in fallback model_name '{backend.fallback_backend.model_name}'"
    )
