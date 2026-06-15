"""
Step definitions for features/rubric_score.feature.

Drives RubricEvaluator directly via MockLLMBackend — no Django, no HTTP.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from unittest.mock import MagicMock

from resume_pipeline.pipeline.rubric_score import (
    CRITERIA,
    FALLBACK_SCORE,
    RUBRIC_WEIGHTS,
    AnthropicRubricBackend,
    LLMBackendProtocol,
    MockLLMBackend,
    OpenAIRubricBackend,
    RubricEvaluator,
    RubricScoreResponse,
    build_llm_response,
    make_rubric_backend,
)
from resume_pipeline.pipeline.rubric_protocol import RubricEvaluatorProtocol, RubricResult

pytestmark = pytest.mark.bdd

scenarios("rubric_score.feature")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RESUME = {"experience": "5 years of Python and Django", "skills": "PostgreSQL, Docker"}
_JOB_REQ = {"required_skills": ["Python", "Django", "PostgreSQL"]}

# 11-word justification — reliably over the 10-word threshold.
_SUBSTANTIVE_JUST = "Candidate demonstrates strong technical proficiency across all relevant core competencies here"

# 9-word justification — reliably under the threshold.
_EMPTY_JUST = ""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx() -> dict:
    return {}


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

@given("a rubric evaluator backed by a mock LLM")
def rubric_evaluator_with_mock(ctx: dict) -> None:
    # Will be replaced by scenario-specific givens; create a no-op default.
    ctx.setdefault("backend", MockLLMBackend(""))
    ctx["evaluator"] = RubricEvaluator(llm_backend=ctx["backend"])


@given("the rubric weight invariant holds (weights sum to 1.0)")
def weight_invariant_holds(ctx: dict) -> None:
    total = sum(RUBRIC_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total:.10f}, expected 1.0"


# ---------------------------------------------------------------------------
# Given — LLM response configuration
# ---------------------------------------------------------------------------

@given(parsers.parse("the LLM returns all rubric scores as {score:g}"))
def llm_all_scores(ctx: dict, score: float) -> None:
    response = build_llm_response(
        scores={c: score for c in CRITERIA},
        justifications={c: _EMPTY_JUST for c in CRITERIA},
    )
    ctx["backend"] = MockLLMBackend(response)
    ctx["evaluator"] = RubricEvaluator(llm_backend=ctx["backend"])


@given("the LLM returns rubric scores:")
def llm_mixed_scores(ctx: dict, datatable) -> None:
    rows = datatable[1:]  # datatable[0] is the header row
    scores = {row[0]: float(row[1]) for row in rows}
    response = build_llm_response(
        scores=scores,
        justifications={c: _EMPTY_JUST for c in CRITERIA},
    )
    ctx["backend"] = MockLLMBackend(response)
    ctx["evaluator"] = RubricEvaluator(llm_backend=ctx["backend"])


@given(parsers.parse('the LLM returns a score of {score:g} for "{criterion}" and {other:g} for all others'))
def llm_one_score_different(ctx: dict, score: float, criterion: str, other: float) -> None:
    scores = {c: other for c in CRITERIA}
    scores[criterion] = score
    response = build_llm_response(
        scores=scores,
        justifications={c: _EMPTY_JUST for c in CRITERIA},
    )
    ctx["backend"] = MockLLMBackend(response)
    ctx["evaluator"] = RubricEvaluator(llm_backend=ctx["backend"])


@given(parsers.parse('the LLM returns invalid JSON "{text}"'))
def llm_invalid_json(ctx: dict, text: str) -> None:
    ctx["backend"] = MockLLMBackend(text)
    ctx["evaluator"] = RubricEvaluator(llm_backend=ctx["backend"])


@given("the LLM returns valid JSON wrapped in a markdown code block")
def llm_markdown_json(ctx: dict) -> None:
    payload = build_llm_response(
        scores={c: 4.0 for c in CRITERIA},
        justifications={c: _SUBSTANTIVE_JUST for c in CRITERIA},
    )
    wrapped = f"```json\n{payload}\n```"
    ctx["backend"] = MockLLMBackend(wrapped)
    ctx["evaluator"] = RubricEvaluator(llm_backend=ctx["backend"])


@given("the LLM returns an empty string")
def llm_empty_string(ctx: dict) -> None:
    ctx["backend"] = MockLLMBackend("")
    ctx["evaluator"] = RubricEvaluator(llm_backend=ctx["backend"])


# ---------------------------------------------------------------------------
# Given — justification modifiers (compound steps applied after score setup)
# ---------------------------------------------------------------------------

@given("all justifications have at least 10 words")
def justifications_substantive(ctx: dict) -> None:
    # Re-build the response using the scores already set in the backend,
    # but with substantive justifications.
    prev_response = ctx["backend"]._response
    try:
        data = json.loads(prev_response)
        scores = data.get("scores", {c: 3.0 for c in CRITERIA})
    except (json.JSONDecodeError, ValueError):
        scores = {c: 3.0 for c in CRITERIA}

    response = build_llm_response(
        scores=scores,
        justifications={c: _SUBSTANTIVE_JUST for c in CRITERIA},
    )
    ctx["backend"] = MockLLMBackend(response)
    ctx["evaluator"] = RubricEvaluator(llm_backend=ctx["backend"])


@given("all justifications are empty strings")
def justifications_empty(ctx: dict) -> None:
    prev_response = ctx["backend"]._response
    try:
        data = json.loads(prev_response)
        scores = data.get("scores", {c: 3.0 for c in CRITERIA})
    except (json.JSONDecodeError, ValueError):
        scores = {c: 3.0 for c in CRITERIA}

    response = build_llm_response(
        scores=scores,
        justifications={c: "" for c in CRITERIA},
    )
    ctx["backend"] = MockLLMBackend(response)
    ctx["evaluator"] = RubricEvaluator(llm_backend=ctx["backend"])


@given(parsers.parse("{n:d} of 5 justifications have at least 10 words"))
def justifications_partial(ctx: dict, n: int) -> None:
    prev_response = ctx["backend"]._response
    try:
        data = json.loads(prev_response)
        scores = data.get("scores", {c: 3.0 for c in CRITERIA})
    except (json.JSONDecodeError, ValueError):
        scores = {c: 3.0 for c in CRITERIA}

    criteria_list = list(CRITERIA)
    justifications = {c: "" for c in CRITERIA}
    for i in range(n):
        justifications[criteria_list[i]] = _SUBSTANTIVE_JUST

    response = build_llm_response(scores=scores, justifications=justifications)
    ctx["backend"] = MockLLMBackend(response)
    ctx["evaluator"] = RubricEvaluator(llm_backend=ctx["backend"])


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------

@when("I evaluate a resume against job requirements")
def evaluate_resume(ctx: dict) -> None:
    ctx["result"] = ctx["evaluator"].evaluate(_RESUME, _JOB_REQ)


# ---------------------------------------------------------------------------
# Then — normalized_score assertions
# ---------------------------------------------------------------------------

@then(parsers.parse("the normalized_score is {expected:g}"))
def assert_normalized_score_exact(ctx: dict, expected: float) -> None:
    actual = ctx["result"].normalized_score
    assert abs(actual - expected) < 1e-9, (
        f"normalized_score: expected {expected}, got {actual}"
    )


@then(parsers.parse("the normalized_score is approximately {expected:g}"))
def assert_normalized_score_approx(ctx: dict, expected: float) -> None:
    actual = ctx["result"].normalized_score
    assert abs(actual - expected) < 1e-6, (
        f"normalized_score: expected ~{expected}, got {actual}"
    )


@then(parsers.parse("the normalized_score is greater than {threshold:g}"))
def assert_normalized_score_gt(ctx: dict, threshold: float) -> None:
    actual = ctx["result"].normalized_score
    assert actual > threshold, f"normalized_score {actual} is not > {threshold}"


@then(parsers.parse("the normalized_score is between {lo:g} and {hi:g}"))
def assert_normalized_score_range(ctx: dict, lo: float, hi: float) -> None:
    actual = ctx["result"].normalized_score
    assert lo <= actual <= hi, f"normalized_score {actual} not in [{lo}, {hi}]"


# ---------------------------------------------------------------------------
# Then — evidence_quality assertions
# ---------------------------------------------------------------------------

@then(parsers.parse("the evidence_quality is {expected:g}"))
def assert_evidence_quality_exact(ctx: dict, expected: float) -> None:
    actual = ctx["result"].evidence_quality
    assert abs(actual - expected) < 1e-9, (
        f"evidence_quality: expected {expected}, got {actual}"
    )


@then(parsers.parse("the evidence_quality is approximately {expected:g}"))
def assert_evidence_quality_approx(ctx: dict, expected: float) -> None:
    actual = ctx["result"].evidence_quality
    assert abs(actual - expected) < 1e-6, (
        f"evidence_quality: expected ~{expected}, got {actual}"
    )


@then(parsers.parse("the evidence_quality is between {lo:g} and {hi:g}"))
def assert_evidence_quality_range(ctx: dict, lo: float, hi: float) -> None:
    actual = ctx["result"].evidence_quality
    assert lo <= actual <= hi, f"evidence_quality {actual} not in [{lo}, {hi}]"


# ---------------------------------------------------------------------------
# Then — criterion_scores assertions
# ---------------------------------------------------------------------------

@then(parsers.parse('the criterion_scores contains "{criterion}" with value {expected:g}'))
def assert_criterion_score(ctx: dict, criterion: str, expected: float) -> None:
    scores = ctx["result"].criterion_scores
    assert criterion in scores, f"criterion_scores missing key '{criterion}'"
    actual = scores[criterion]
    assert abs(actual - expected) < 1e-9, (
        f"criterion_scores['{criterion}']: expected {expected}, got {actual}"
    )


# ---------------------------------------------------------------------------
# Then — protocol conformance
# ---------------------------------------------------------------------------

@then("the evaluator is an instance of RubricEvaluatorProtocol")
def assert_protocol_conformance(ctx: dict) -> None:
    assert isinstance(ctx["evaluator"], RubricEvaluatorProtocol), (
        f"{type(ctx['evaluator'])} does not satisfy RubricEvaluatorProtocol"
    )


# ---------------------------------------------------------------------------
# M3 Upgrade — RubricScoreResponse, backends, factory
# ---------------------------------------------------------------------------

def _valid_scores(override: dict | None = None) -> dict[str, int]:
    base = {c: 3 for c in CRITERIA}
    if override:
        base.update(override)
    return base


def _valid_justifications() -> dict[str, str]:
    return {c: f"Justification for {c}." for c in CRITERIA}


@when(parsers.parse('I construct a RubricScoreResponse with score {score:d} for "{criterion}"'))
def construct_response_with_invalid_score(ctx: dict, score: int, criterion: str) -> None:
    from pydantic import ValidationError
    ctx["validation_error"] = None
    try:
        scores = _valid_scores({criterion: score})
        ctx["rubric_response"] = RubricScoreResponse(
            scores=scores,
            justifications=_valid_justifications(),
        )
    except ValidationError as exc:
        ctx["validation_error"] = exc


@when(parsers.parse('I construct a RubricScoreResponse with "{criterion}" omitted from scores'))
def construct_response_missing_criterion(ctx: dict, criterion: str) -> None:
    from pydantic import ValidationError
    ctx["validation_error"] = None
    try:
        scores = {c: 3 for c in CRITERIA if c != criterion}
        ctx["rubric_response"] = RubricScoreResponse(
            scores=scores,
            justifications=_valid_justifications(),
        )
    except ValidationError as exc:
        ctx["validation_error"] = exc


@when("I construct a valid RubricScoreResponse with all scores set to 4")
def construct_valid_response(ctx: dict) -> None:
    from pydantic import ValidationError
    ctx["validation_error"] = None
    try:
        ctx["rubric_response"] = RubricScoreResponse(
            scores=_valid_scores({c: 4 for c in CRITERIA}),
            justifications=_valid_justifications(),
        )
    except ValidationError as exc:
        ctx["validation_error"] = exc


@then("a ValidationError is raised")
def assert_validation_error_raised(ctx: dict) -> None:
    assert ctx.get("validation_error") is not None, (
        "Expected a pydantic.ValidationError to be raised, but none was caught. "
        f"Got rubric_response: {ctx.get('rubric_response')}"
    )


@then("no ValidationError is raised")
def assert_no_validation_error(ctx: dict) -> None:
    assert ctx.get("validation_error") is None, (
        f"Unexpected ValidationError: {ctx['validation_error']}"
    )


@then("the RubricScoreResponse has scores for all five criteria")
def assert_response_has_all_criteria(ctx: dict) -> None:
    resp = ctx["rubric_response"]
    assert set(resp.scores.keys()) == set(CRITERIA), (
        f"Expected criteria: {set(CRITERIA)}\nGot: {set(resp.scores.keys())}"
    )


# -- Factory steps -----------------------------------------------------------

@when(parsers.parse('I call make_rubric_backend with backend "{backend_name}"'))
def call_make_rubric_backend(ctx: dict, backend_name: str) -> None:
    ctx["backend"] = make_rubric_backend(backend_name)


@then("the result satisfies LLMBackendProtocol")
def assert_satisfies_protocol(ctx: dict) -> None:
    assert isinstance(ctx["backend"], LLMBackendProtocol), (
        f"{type(ctx['backend'])} does not satisfy LLMBackendProtocol"
    )


@then("the result is an OpenAIRubricBackend")
def assert_is_openai_backend(ctx: dict) -> None:
    assert isinstance(ctx["backend"], OpenAIRubricBackend), (
        f"Expected OpenAIRubricBackend; got {type(ctx['backend'])}"
    )


@then("the result is an AnthropicRubricBackend")
def assert_is_anthropic_backend(ctx: dict) -> None:
    assert isinstance(ctx["backend"], AnthropicRubricBackend), (
        f"Expected AnthropicRubricBackend; got {type(ctx['backend'])}"
    )


# -- Retry steps -------------------------------------------------------------

@given("an OpenAIRubricBackend whose client raises RateLimitError twice then succeeds")
def openai_backend_retry_then_succeed(ctx: dict) -> None:
    import openai

    valid_resp = RubricScoreResponse(
        scores={c: 4 for c in CRITERIA},
        justifications={c: "Evidence." for c in CRITERIA},
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        openai.RateLimitError("rate limit", response=MagicMock(), body={}),
        openai.RateLimitError("rate limit", response=MagicMock(), body={}),
        valid_resp,
    ]
    backend = OpenAIRubricBackend.__new__(OpenAIRubricBackend)
    backend._model = "gpt-4o-mini"
    backend._max_retries = 3
    backend._client = mock_client
    ctx["backend"] = backend
    ctx["mock_client"] = mock_client


@given("an OpenAIRubricBackend whose client always raises RateLimitError")
def openai_backend_always_fail(ctx: dict) -> None:
    import openai

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = openai.RateLimitError(
        "rate limit", response=MagicMock(), body={}
    )
    backend = OpenAIRubricBackend.__new__(OpenAIRubricBackend)
    backend._model = "gpt-4o-mini"
    backend._max_retries = 3
    backend._client = mock_client
    ctx["backend"] = backend
    ctx["mock_client"] = mock_client


@when("I call complete on the backend")
def call_complete_on_backend(ctx: dict) -> None:
    import openai

    ctx["complete_exception"] = None
    ctx["complete_result"] = None
    try:
        ctx["complete_result"] = ctx["backend"].complete("system", "user")
    except openai.RateLimitError as exc:
        ctx["complete_exception"] = exc


@then("the backend returns a valid RubricScoreResponse")
def assert_backend_returns_response(ctx: dict) -> None:
    result = ctx.get("complete_result")
    assert result is not None, (
        f"Expected a RubricScoreResponse but got None. "
        f"Exception: {ctx.get('complete_exception')}"
    )
    assert isinstance(result, RubricScoreResponse)


@then(parsers.parse("the underlying client was called {count:d} times"))
def assert_client_call_count(ctx: dict, count: int) -> None:
    actual = ctx["mock_client"].chat.completions.create.call_count
    assert actual == count, f"Expected {count} client calls; got {actual}"


@then(parsers.parse("a RateLimitError is raised after {count:d} attempts"))
def assert_rate_limit_error_raised(ctx: dict, count: int) -> None:
    import openai

    assert ctx.get("complete_exception") is not None, (
        "Expected a RateLimitError to be raised, but no exception was caught."
    )
    assert isinstance(ctx["complete_exception"], openai.RateLimitError)
    actual = ctx["mock_client"].chat.completions.create.call_count
    assert actual == count, f"Expected {count} client calls before giving up; got {actual}"


# -- Pydantic response direct-intake step ------------------------------------

@given("a rubric evaluator backed by a mock backend returning a RubricScoreResponse object")
def evaluator_with_pydantic_backend(ctx: dict) -> None:
    response = RubricScoreResponse(
        scores={c: 4 for c in CRITERIA},
        justifications={
            c: "Detailed evidence citation with more than ten words appears here."
            for c in CRITERIA
        },
    )
    mock_backend = MagicMock()
    mock_backend.complete.return_value = response
    mock_backend.model_name = "mock-pydantic-v1"
    ctx["evaluator"] = RubricEvaluator(mock_backend)
