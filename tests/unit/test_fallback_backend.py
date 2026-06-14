"""
M8 — Inner TDD loop: LLM Provider Resilience Fallback.

Tests the FallbackLLMBackend in complete isolation — no live API calls,
no real LLM providers, no Django database.

Test classes
────────────
  TestFallbackLLMBackendPrimarySucceeds      — happy path, no handoff
  TestFallbackLLMBackendRateLimitHandoff     — RateLimitError triggers fallback
  TestFallbackLLMBackendTimeoutHandoff       — APITimeoutError triggers fallback
  TestFallbackLLMBackendConnectionHandoff    — APIConnectionError triggers fallback
  TestFallbackLLMBackendBothFail             — both providers fail, exception raised
  TestFallbackAuditEventPayloads             — structured JSON event assertions
  TestFallbackIntegrationWithRubricEvaluator — is_evaluated_via_fallback propagation
  TestMakeRubricBackendFactory               — factory wiring from env vars

Run:
    pytest tests/unit/test_fallback_backend.py -v
    pytest tests/unit/test_fallback_backend.py -v -m unit
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from resume_pipeline.logging_module import StructuredAuditLogger
from resume_pipeline.pipeline.fallback_backend import FallbackLLMBackend
from resume_pipeline.pipeline.rubric_score import (
    CRITERIA,
    AnthropicRubricBackend,
    MockLLMBackend,
    OpenAIRubricBackend,
    RubricEvaluator,
    RubricScoreResponse,
    build_llm_response,
    make_rubric_backend,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _mock_openai_backend(
    model: str = "gpt-4o-mini",
    max_retries: int = 3,
) -> OpenAIRubricBackend:
    """Return an OpenAIRubricBackend with a fully-injected mock client."""
    backend = OpenAIRubricBackend.__new__(OpenAIRubricBackend)
    backend._model = model
    backend._max_retries = max_retries
    backend._client = MagicMock()
    return backend


def _mock_anthropic_backend(
    model: str = "claude-haiku-4-5-20251001",
    max_retries: int = 3,
) -> AnthropicRubricBackend:
    """Return an AnthropicRubricBackend with a fully-injected mock client."""
    backend = AnthropicRubricBackend.__new__(AnthropicRubricBackend)
    backend._model = model
    backend._max_retries = max_retries
    backend._client = MagicMock()
    return backend


def _valid_rubric_response(score: int = 4) -> RubricScoreResponse:
    """Build a fully valid RubricScoreResponse for any criterion score."""
    return RubricScoreResponse(
        scores={c: score for c in CRITERIA},
        justifications={c: f"Solid evidence for {c} found in the candidate resume." for c in CRITERIA},
    )


def _mock_llm_backend_returning(response_str: str) -> MockLLMBackend:
    return MockLLMBackend(
        build_llm_response(
            scores={c: 4 for c in CRITERIA},
            justifications={c: "Good evidence provided." for c in CRITERIA},
        )
        if not response_str
        else response_str
    )


@contextmanager
def capture_audit_events(logger_name: str = "pipeline.audit") -> Generator[list[dict], None, None]:
    """Context manager that collects structured JSON events from the audit logger."""
    events: list[dict] = []

    class _JsonHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            msg = record.getMessage()
            if msg.strip().startswith("{"):
                try:
                    events.append(json.loads(msg))
                except json.JSONDecodeError:
                    pass

    handler = _JsonHandler()
    log = logging.getLogger(logger_name)
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    try:
        yield events
    finally:
        log.removeHandler(handler)


def _make_fallback_backend(
    primary_side_effects=None,
    fallback_side_effects=None,
    primary_model: str = "gpt-4o-mini",
    fallback_model: str = "claude-haiku-4-5-20251001",
    audit_logger: StructuredAuditLogger | None = None,
) -> FallbackLLMBackend:
    """
    Build a FallbackLLMBackend with fully-mocked inner clients.

    Args:
        primary_side_effects: List of return values / exceptions for the primary
                              client's chat.completions.create side_effect.
        fallback_side_effects: Same for the fallback client.
    """
    primary = _mock_openai_backend(model=primary_model)
    fallback = _mock_anthropic_backend(model=fallback_model)

    # Patch the primary's complete() directly so we bypass tenacity:
    # call it as a simple mock.
    primary.complete = MagicMock(
        side_effect=primary_side_effects if primary_side_effects is not None else [_valid_rubric_response()]
    )
    fallback.complete = MagicMock(
        side_effect=fallback_side_effects if fallback_side_effects is not None else [_valid_rubric_response()]
    )

    return FallbackLLMBackend(
        primary=primary,
        fallback=fallback,
        audit_logger=audit_logger,
    )


# ---------------------------------------------------------------------------
# Test class 1: Primary succeeds — no handoff
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFallbackLLMBackendPrimarySucceeds:
    """When primary.complete() returns a valid response, the fallback is never touched."""

    @pytest.fixture
    def valid_response(self) -> RubricScoreResponse:
        return _valid_rubric_response(score=4)

    @pytest.fixture
    def backend(self, valid_response: RubricScoreResponse) -> FallbackLLMBackend:
        return _make_fallback_backend(primary_side_effects=[valid_response])

    def test_result_is_primary_response(self, backend: FallbackLLMBackend, valid_response: RubricScoreResponse) -> None:
        result = backend.complete("sys", "user")
        assert result is valid_response

    def test_used_fallback_is_false(self, backend: FallbackLLMBackend) -> None:
        backend.complete("sys", "user")
        assert backend.used_fallback is False

    def test_model_name_is_primary(self, backend: FallbackLLMBackend) -> None:
        backend.complete("sys", "user")
        assert backend.model_name == "gpt-4o-mini"

    def test_fallback_complete_never_called(self, backend: FallbackLLMBackend) -> None:
        backend.complete("sys", "user")
        backend._fallback.complete.assert_not_called()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Test class 2: RateLimitError → fallback
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFallbackLLMBackendRateLimitHandoff:
    """RateLimitError from the primary should transparently engage the fallback."""

    @pytest.fixture
    def openai_rate_limit_error(self):
        import openai
        return openai.RateLimitError(
            "rate limit exceeded",
            response=MagicMock(status_code=429),
            body={},
        )

    @pytest.fixture
    def fallback_response(self) -> RubricScoreResponse:
        return _valid_rubric_response(score=3)

    @pytest.fixture
    def backend(
        self,
        openai_rate_limit_error,
        fallback_response: RubricScoreResponse,
    ) -> FallbackLLMBackend:
        return _make_fallback_backend(
            primary_side_effects=[openai_rate_limit_error],
            fallback_side_effects=[fallback_response],
        )

    def test_fallback_response_returned(
        self,
        backend: FallbackLLMBackend,
        fallback_response: RubricScoreResponse,
    ) -> None:
        result = backend.complete("sys", "user")
        assert result is fallback_response

    def test_used_fallback_is_true(self, backend: FallbackLLMBackend) -> None:
        backend.complete("sys", "user")
        assert backend.used_fallback is True

    def test_model_name_is_fallback_after_handoff(self, backend: FallbackLLMBackend) -> None:
        backend.complete("sys", "user")
        assert "claude" in backend.model_name

    def test_last_primary_error_is_rate_limit(
        self,
        backend: FallbackLLMBackend,
        openai_rate_limit_error,
    ) -> None:
        backend.complete("sys", "user")
        assert backend.last_primary_error is openai_rate_limit_error

    def test_primary_failed_event_emitted(self, backend: FallbackLLMBackend) -> None:
        audit = StructuredAuditLogger()
        backend._audit = audit
        with capture_audit_events() as events:
            backend.complete("sys", "user")
        assert any(e.get("event") == "primary_llm_failed" for e in events)

    def test_fallback_engaged_event_emitted(self, backend: FallbackLLMBackend) -> None:
        with capture_audit_events() as events:
            backend.complete("sys", "user")
        assert any(e.get("event") == "fallback_llm_engaged" for e in events)

    def test_fallback_succeeded_event_emitted(self, backend: FallbackLLMBackend) -> None:
        with capture_audit_events() as events:
            backend.complete("sys", "user")
        assert any(e.get("event") == "fallback_llm_succeeded" for e in events)


# ---------------------------------------------------------------------------
# Test class 3: APITimeoutError → fallback
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFallbackLLMBackendTimeoutHandoff:

    @pytest.fixture
    def timeout_error(self):
        import openai
        return openai.APITimeoutError(request=MagicMock())

    @pytest.fixture
    def fallback_response(self) -> RubricScoreResponse:
        return _valid_rubric_response(score=4)

    @pytest.fixture
    def backend(self, timeout_error, fallback_response):
        return _make_fallback_backend(
            primary_side_effects=[timeout_error],
            fallback_side_effects=[fallback_response],
        )

    def test_timeout_triggers_fallback(self, backend: FallbackLLMBackend) -> None:
        backend.complete("sys", "user")
        assert backend.used_fallback is True

    def test_primary_failed_event_has_timeout_error_type(self, backend: FallbackLLMBackend) -> None:
        with capture_audit_events() as events:
            backend.complete("sys", "user")
        failed_events = [e for e in events if e.get("event") == "primary_llm_failed"]
        assert len(failed_events) == 1
        assert failed_events[0]["error_type"] == "APITimeoutError"


# ---------------------------------------------------------------------------
# Test class 4: APIConnectionError → fallback
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFallbackLLMBackendConnectionHandoff:

    @pytest.fixture
    def connection_error(self):
        import openai
        return openai.APIConnectionError(request=MagicMock())

    @pytest.fixture
    def fallback_response(self) -> RubricScoreResponse:
        return _valid_rubric_response(score=4)

    @pytest.fixture
    def backend(self, connection_error, fallback_response):
        return _make_fallback_backend(
            primary_side_effects=[connection_error],
            fallback_side_effects=[fallback_response],
        )

    def test_connection_error_triggers_fallback(self, backend: FallbackLLMBackend) -> None:
        backend.complete("sys", "user")
        assert backend.used_fallback is True

    def test_primary_failed_event_has_connection_error_type(self, backend: FallbackLLMBackend) -> None:
        with capture_audit_events() as events:
            backend.complete("sys", "user")
        failed = [e for e in events if e.get("event") == "primary_llm_failed"]
        assert failed[0]["error_type"] == "APIConnectionError"


# ---------------------------------------------------------------------------
# Test class 5: Both providers fail
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFallbackLLMBackendBothFail:
    """When both primary and fallback fail, the exception must propagate and
    a fallback_llm_exhausted audit event must be emitted."""

    @pytest.fixture
    def primary_error(self):
        import openai
        return openai.RateLimitError("primary rate limit", response=MagicMock(), body={})

    @pytest.fixture
    def fallback_error(self):
        return RuntimeError("Anthropic service unavailable")

    @pytest.fixture
    def backend(self, primary_error, fallback_error):
        return _make_fallback_backend(
            primary_side_effects=[primary_error],
            fallback_side_effects=[fallback_error],
        )

    def test_raises_exception(self, backend: FallbackLLMBackend, fallback_error) -> None:
        with pytest.raises(RuntimeError, match="Anthropic service unavailable"):
            backend.complete("sys", "user")

    def test_used_fallback_is_false_on_total_failure(self, backend: FallbackLLMBackend) -> None:
        # used_fallback must be False — the fallback was attempted but did not succeed.
        with pytest.raises(RuntimeError):
            backend.complete("sys", "user")
        assert backend.used_fallback is False

    def test_fallback_exhausted_event_emitted(self, backend: FallbackLLMBackend) -> None:
        with capture_audit_events() as events:
            with pytest.raises(RuntimeError):
                backend.complete("sys", "user")
        assert any(e.get("event") == "fallback_llm_exhausted" for e in events)

    def test_no_fallback_succeeded_event_on_total_failure(self, backend: FallbackLLMBackend) -> None:
        with capture_audit_events() as events:
            with pytest.raises(RuntimeError):
                backend.complete("sys", "user")
        assert not any(e.get("event") == "fallback_llm_succeeded" for e in events)


# ---------------------------------------------------------------------------
# Test class 6: Audit event payload assertions
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFallbackAuditEventPayloads:
    """Assert the exact JSON shapes of all four audit event types."""

    @pytest.fixture
    def rate_limit_error(self):
        import openai
        return openai.RateLimitError("rate limited", response=MagicMock(), body={})

    @pytest.fixture
    def fallback_response(self) -> RubricScoreResponse:
        return _valid_rubric_response(score=4)

    @pytest.fixture
    def fallback_error(self):
        return RuntimeError("fallback also down")

    def test_primary_failed_event_has_provider_field(
        self, rate_limit_error, fallback_response
    ) -> None:
        backend = _make_fallback_backend(
            primary_side_effects=[rate_limit_error],
            fallback_side_effects=[fallback_response],
        )
        with capture_audit_events() as events:
            backend.complete("sys", "user")
        evt = next(e for e in events if e.get("event") == "primary_llm_failed")
        assert evt["provider"] == "gpt-4o-mini"

    def test_primary_failed_event_has_error_type_field(
        self, rate_limit_error, fallback_response
    ) -> None:
        backend = _make_fallback_backend(
            primary_side_effects=[rate_limit_error],
            fallback_side_effects=[fallback_response],
        )
        with capture_audit_events() as events:
            backend.complete("sys", "user")
        evt = next(e for e in events if e.get("event") == "primary_llm_failed")
        assert evt["error_type"] == "RateLimitError"

    def test_primary_failed_event_has_retry_count_field(
        self, rate_limit_error, fallback_response
    ) -> None:
        backend = _make_fallback_backend(
            primary_side_effects=[rate_limit_error],
            fallback_side_effects=[fallback_response],
        )
        with capture_audit_events() as events:
            backend.complete("sys", "user")
        evt = next(e for e in events if e.get("event") == "primary_llm_failed")
        # retry_count comes from _primary._max_retries
        assert "retry_count" in evt

    def test_fallback_engaged_event_has_both_provider_names(
        self, rate_limit_error, fallback_response
    ) -> None:
        backend = _make_fallback_backend(
            primary_side_effects=[rate_limit_error],
            fallback_side_effects=[fallback_response],
        )
        with capture_audit_events() as events:
            backend.complete("sys", "user")
        evt = next(e for e in events if e.get("event") == "fallback_llm_engaged")
        assert evt["primary_provider"] == "gpt-4o-mini"
        assert evt["target_provider"] == "claude-haiku-4-5-20251001"

    def test_fallback_exhausted_event_has_both_provider_names(
        self, rate_limit_error, fallback_error
    ) -> None:
        backend = _make_fallback_backend(
            primary_side_effects=[rate_limit_error],
            fallback_side_effects=[fallback_error],
        )
        with capture_audit_events() as events:
            with pytest.raises(RuntimeError):
                backend.complete("sys", "user")
        evt = next(e for e in events if e.get("event") == "fallback_llm_exhausted")
        assert evt["primary_provider"] == "gpt-4o-mini"
        assert evt["fallback_provider"] == "claude-haiku-4-5-20251001"
        assert "error_type" in evt


# ---------------------------------------------------------------------------
# Test class 7: Integration with RubricEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFallbackIntegrationWithRubricEvaluator:
    """
    Verifies that RubricEvaluator correctly stamps RubricResult with the
    is_evaluated_via_fallback flag from the underlying FallbackLLMBackend.
    """

    @pytest.fixture
    def resume_parsed(self) -> dict:
        return {
            "total_experience_years": 7,
            "experience": "Senior Python Engineer 2017-2024",
            "skills": "Python Django PostgreSQL REST APIs",
        }

    @pytest.fixture
    def job_requirements(self) -> dict:
        return {"required_skills": ["Python", "Django"], "minimum_experience_years": 5}

    def test_is_evaluated_via_fallback_true_when_fallback_used(
        self, resume_parsed, job_requirements
    ) -> None:
        import openai
        rate_limit = openai.RateLimitError("rl", response=MagicMock(), body={})
        fallback_resp = _valid_rubric_response(score=4)

        backend = _make_fallback_backend(
            primary_side_effects=[rate_limit],
            fallback_side_effects=[fallback_resp],
        )
        evaluator = RubricEvaluator(backend)
        result = evaluator.evaluate(resume_parsed, job_requirements)

        assert result.is_evaluated_via_fallback is True

    def test_is_evaluated_via_fallback_false_when_primary_used(
        self, resume_parsed, job_requirements
    ) -> None:
        primary_resp = _valid_rubric_response(score=4)
        backend = _make_fallback_backend(primary_side_effects=[primary_resp])
        evaluator = RubricEvaluator(backend)
        result = evaluator.evaluate(resume_parsed, job_requirements)

        assert result.is_evaluated_via_fallback is False

    def test_rubric_scores_are_valid_when_fallback_used(
        self, resume_parsed, job_requirements
    ) -> None:
        import openai
        rate_limit = openai.RateLimitError("rl", response=MagicMock(), body={})
        fallback_resp = _valid_rubric_response(score=3)

        backend = _make_fallback_backend(
            primary_side_effects=[rate_limit],
            fallback_side_effects=[fallback_resp],
        )
        evaluator = RubricEvaluator(backend)
        result = evaluator.evaluate(resume_parsed, job_requirements)

        assert 0.0 < result.normalized_score <= 1.0
        assert set(result.criterion_scores.keys()) == set(CRITERIA)


# ---------------------------------------------------------------------------
# Test class 8: make_rubric_backend() factory
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMakeRubricBackendFactory:
    """Verifies the factory wires FallbackLLMBackend when LLM_BACKEND_FALLBACK is set."""

    def test_no_fallback_env_returns_single_backend(self) -> None:
        with patch.dict(os.environ, {"LLM_BACKEND": "mock"}, clear=False):
            os.environ.pop("LLM_BACKEND_FALLBACK", None)
            backend = make_rubric_backend()
        assert not isinstance(backend, FallbackLLMBackend)

    def test_fallback_env_set_returns_fallback_backend(self) -> None:
        with patch.dict(
            os.environ,
            {"LLM_BACKEND": "openai", "LLM_BACKEND_FALLBACK": "anthropic"},
            clear=False,
        ):
            backend = make_rubric_backend()
        assert isinstance(backend, FallbackLLMBackend)

    def test_fallback_backend_primary_is_openai(self) -> None:
        with patch.dict(
            os.environ,
            {"LLM_BACKEND": "openai", "LLM_BACKEND_FALLBACK": "anthropic"},
            clear=False,
        ):
            backend = make_rubric_backend()
        assert isinstance(backend, FallbackLLMBackend)
        assert isinstance(backend.primary, OpenAIRubricBackend)

    def test_fallback_backend_secondary_is_anthropic(self) -> None:
        with patch.dict(
            os.environ,
            {"LLM_BACKEND": "openai", "LLM_BACKEND_FALLBACK": "anthropic"},
            clear=False,
        ):
            backend = make_rubric_backend()
        assert isinstance(backend, FallbackLLMBackend)
        assert isinstance(backend.fallback_backend, AnthropicRubricBackend)

    def test_explicit_args_override_env_vars(self) -> None:
        backend = make_rubric_backend(backend="openai", fallback="anthropic")
        assert isinstance(backend, FallbackLLMBackend)
        assert isinstance(backend.primary, OpenAIRubricBackend)
        assert isinstance(backend.fallback_backend, AnthropicRubricBackend)

    def test_same_primary_and_fallback_no_wrapper(self) -> None:
        # If someone mistakenly sets both to the same value, no FallbackLLMBackend
        # should be created (it would be pointless and would double-charge latency).
        with patch.dict(
            os.environ,
            {"LLM_BACKEND": "openai", "LLM_BACKEND_FALLBACK": "openai"},
            clear=False,
        ):
            backend = make_rubric_backend()
        assert not isinstance(backend, FallbackLLMBackend)
