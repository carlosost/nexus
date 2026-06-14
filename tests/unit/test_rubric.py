"""
Unit tests for M3: LLM Rubric Scoring (Stage 3).

Inner TDD loop — these tests must all PASS after implementation.

Coverage:
  - RUBRIC_WEIGHTS invariant (sum to 1.0, all criteria present)
  - _parse_response: valid JSON, JSON in markdown block, bad JSON → fallback
  - _score: normalization formula, score clamping, evidence quality formula
  - evaluate: end-to-end with MockLLMBackend
  - RubricEvaluator satisfies RubricEvaluatorProtocol (isinstance)
  - RubricResult fields are in valid ranges
"""

from __future__ import annotations

import json
import math
from unittest.mock import MagicMock

import pytest

from resume_pipeline.pipeline.rubric_score import (
    RUBRIC_WEIGHTS,
    CRITERIA,
    FALLBACK_SCORE,
    RubricEvaluator,
    MockLLMBackend,
    build_llm_response,
)
from resume_pipeline.pipeline.rubric_protocol import RubricEvaluatorProtocol, RubricResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evaluator(response_text: str = "") -> RubricEvaluator:
    backend = MockLLMBackend(response_text)
    return RubricEvaluator(llm_backend=backend)


def _all_score_response(score: float, justification: str = "") -> str:
    """Build a JSON response with the same score for all criteria."""
    return build_llm_response(
        scores={c: score for c in CRITERIA},
        justifications={c: justification for c in CRITERIA},
    )


RESUME = {"experience": "5 years Python", "skills": "Django, PostgreSQL"}
JOB_REQ = {"required_skills": ["Python", "Django"]}


# ---------------------------------------------------------------------------
# RUBRIC_WEIGHTS invariant
# ---------------------------------------------------------------------------

class TestRubricWeightsInvariant:
    def test_weights_sum_to_1(self):
        total = sum(RUBRIC_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"Weights sum to {total:.10f}, expected 1.0"

    def test_all_criteria_present(self):
        expected = {"core_skills", "relevant_experience", "scope_impact", "domain_alignment", "education_certs"}
        assert set(RUBRIC_WEIGHTS.keys()) == expected

    def test_criteria_list_matches_weights(self):
        assert set(CRITERIA) == set(RUBRIC_WEIGHTS.keys())

    def test_all_weights_positive(self):
        for criterion, weight in RUBRIC_WEIGHTS.items():
            assert weight > 0, f"Weight for '{criterion}' must be positive"

    def test_weight_values(self):
        assert abs(RUBRIC_WEIGHTS["core_skills"] - 0.30) < 1e-9
        assert abs(RUBRIC_WEIGHTS["relevant_experience"] - 0.30) < 1e-9
        assert abs(RUBRIC_WEIGHTS["scope_impact"] - 0.20) < 1e-9
        assert abs(RUBRIC_WEIGHTS["domain_alignment"] - 0.10) < 1e-9
        assert abs(RUBRIC_WEIGHTS["education_certs"] - 0.10) < 1e-9


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:
    def setup_method(self):
        self.ev = _make_evaluator()

    def test_valid_json_parsed(self):
        payload = {"scores": {"core_skills": 4}, "justifications": {"core_skills": "great"}}
        result = self.ev._parse_response(json.dumps(payload))
        assert result["scores"]["core_skills"] == 4

    def test_json_in_backtick_block(self):
        payload = {"scores": {"core_skills": 5}, "justifications": {}}
        raw = f"```json\n{json.dumps(payload)}\n```"
        result = self.ev._parse_response(raw)
        assert result["scores"]["core_skills"] == 5

    def test_json_in_plain_backtick_block(self):
        payload = {"scores": {"core_skills": 3}, "justifications": {}}
        raw = f"```\n{json.dumps(payload)}\n```"
        result = self.ev._parse_response(raw)
        assert result["scores"]["core_skills"] == 3

    def test_bad_json_returns_fallback(self):
        result = self.ev._parse_response("this is not json")
        assert result["scores"]["core_skills"] == FALLBACK_SCORE

    def test_empty_string_returns_fallback(self):
        result = self.ev._parse_response("")
        for c in CRITERIA:
            assert result["scores"][c] == FALLBACK_SCORE

    def test_fallback_justifications_are_empty(self):
        result = self.ev._parse_response("bad json!")
        for c in CRITERIA:
            assert result["justifications"].get(c, "") == ""

    def test_partial_scores_kept(self):
        # Only some criteria provided — others should fall back to FALLBACK_SCORE
        payload = {"scores": {"core_skills": 5}, "justifications": {}}
        result = self.ev._parse_response(json.dumps(payload))
        # The raw parse is preserved; _score() handles missing keys.
        assert result["scores"]["core_skills"] == 5


# ---------------------------------------------------------------------------
# _score (normalization, clamping, evidence quality)
# ---------------------------------------------------------------------------

class TestScoreNormalization:
    def setup_method(self):
        self.ev = _make_evaluator()

    def _parsed(self, scores: dict, justifications: dict | None = None) -> dict:
        return {
            "scores": scores,
            "justifications": justifications or {c: "" for c in CRITERIA},
        }

    def test_all_5_normalizes_to_1(self):
        parsed = self._parsed({c: 5.0 for c in CRITERIA})
        result = self.ev._score(parsed)
        assert abs(result.normalized_score - 1.0) < 1e-9

    def test_all_1_normalizes_to_0_2(self):
        parsed = self._parsed({c: 1.0 for c in CRITERIA})
        result = self.ev._score(parsed)
        assert abs(result.normalized_score - 0.2) < 1e-9

    def test_all_3_5_normalizes_to_0_70(self):
        """Matches StubRubricEvaluator.DEFAULT_NORMALIZED_SCORE."""
        parsed = self._parsed({c: 3.5 for c in CRITERIA})
        result = self.ev._score(parsed)
        assert abs(result.normalized_score - 0.70) < 1e-9

    def test_mixed_scores(self):
        # core=5, relevant=4, scope=3, domain=2, edu=1
        # weighted = 0.30*5 + 0.30*4 + 0.20*3 + 0.10*2 + 0.10*1
        #          = 1.5 + 1.2 + 0.6 + 0.2 + 0.1 = 3.6
        # normalized = 3.6 / 5.0 = 0.72
        parsed = self._parsed({
            "core_skills": 5, "relevant_experience": 4,
            "scope_impact": 3, "domain_alignment": 2, "education_certs": 1,
        })
        result = self.ev._score(parsed)
        assert abs(result.normalized_score - 0.72) < 1e-9

    def test_missing_criterion_defaults_to_fallback(self):
        parsed = self._parsed({"core_skills": 5})  # others missing
        result = self.ev._score(parsed)
        assert 0.0 <= result.normalized_score <= 1.0

    def test_score_above_5_clamped(self):
        parsed = self._parsed({c: 5 for c in CRITERIA} | {"core_skills": 10})
        result = self.ev._score(parsed)
        assert result.criterion_scores["core_skills"] == 5.0

    def test_score_below_1_clamped(self):
        parsed = self._parsed({c: 3 for c in CRITERIA} | {"relevant_experience": -2})
        result = self.ev._score(parsed)
        assert result.criterion_scores["relevant_experience"] == 1.0

    def test_score_zero_clamped_to_1(self):
        parsed = self._parsed({c: 0 for c in CRITERIA})
        result = self.ev._score(parsed)
        for c in CRITERIA:
            assert result.criterion_scores[c] == 1.0

    def test_normalized_score_clamped_between_0_and_1(self):
        parsed = self._parsed({c: 5 for c in CRITERIA})
        result = self.ev._score(parsed)
        assert 0.0 <= result.normalized_score <= 1.0

    def test_criterion_scores_returned_for_all_criteria(self):
        parsed = self._parsed({c: 3.0 for c in CRITERIA})
        result = self.ev._score(parsed)
        assert set(result.criterion_scores.keys()) == set(CRITERIA)


class TestEvidenceQuality:
    def setup_method(self):
        self.ev = _make_evaluator()

    def _parsed(self, scores: dict, justifications: dict) -> dict:
        return {"scores": scores, "justifications": justifications}

    def test_all_substantive_justifications_quality_1(self):
        # 11 words — over the 10-word threshold
        just = {c: "Candidate demonstrates strong technical proficiency across all relevant core competencies here" for c in CRITERIA}
        parsed = self._parsed({c: 4 for c in CRITERIA}, just)
        result = self.ev._score(parsed)
        assert abs(result.evidence_quality - 1.0) < 1e-9

    def test_no_justifications_quality_0(self):
        parsed = self._parsed({c: 4 for c in CRITERIA}, {c: "" for c in CRITERIA})
        result = self.ev._score(parsed)
        assert abs(result.evidence_quality - 0.0) < 1e-9

    def test_partial_justifications_proportional(self):
        # 2 of 5 criteria have substantive justification (>= 10 words)
        just = {c: "" for c in CRITERIA}
        criteria_list = list(CRITERIA)
        # 11 words each — over the threshold
        just[criteria_list[0]] = "The candidate has proven expertise in this competency area through work"
        just[criteria_list[1]] = "Extensive experience clearly visible across multiple high-impact projects throughout career"
        parsed = self._parsed({c: 4 for c in CRITERIA}, just)
        result = self.ev._score(parsed)
        assert abs(result.evidence_quality - 0.40) < 1e-9

    def test_short_justification_does_not_count(self):
        # 9 words — one under the threshold of 10
        just = {c: "one two three four five six seven eight nine" for c in CRITERIA}  # 9 words
        parsed = self._parsed({c: 4 for c in CRITERIA}, just)
        result = self.ev._score(parsed)
        assert abs(result.evidence_quality - 0.0) < 1e-9

    def test_exactly_10_words_counts(self):
        # Exactly 10 words
        just = {c: "one two three four five six seven eight nine ten" for c in CRITERIA}
        parsed = self._parsed({c: 4 for c in CRITERIA}, just)
        result = self.ev._score(parsed)
        assert abs(result.evidence_quality - 1.0) < 1e-9

    def test_evidence_quality_bounded_0_to_1(self):
        # Many words — definitely over threshold
        long_just = " ".join(f"word{i}" for i in range(50))
        parsed = self._parsed({c: 5 for c in CRITERIA}, {c: long_just for c in CRITERIA})
        result = self.ev._score(parsed)
        assert 0.0 <= result.evidence_quality <= 1.0


# ---------------------------------------------------------------------------
# evaluate() — end-to-end with MockLLMBackend
# ---------------------------------------------------------------------------

class TestEvaluateEndToEnd:
    def test_perfect_scores_end_to_end(self):
        # 11 words — over the 10-word threshold
        just = "Candidate demonstrates strong technical proficiency across all relevant core competencies here"
        response = _all_score_response(5.0, justification=just)
        ev = _make_evaluator(response)
        result = ev.evaluate(RESUME, JOB_REQ)
        assert abs(result.normalized_score - 1.0) < 1e-9
        assert result.evidence_quality == 1.0

    def test_minimum_scores_end_to_end(self):
        response = _all_score_response(1.0)
        ev = _make_evaluator(response)
        result = ev.evaluate(RESUME, JOB_REQ)
        assert abs(result.normalized_score - 0.20) < 1e-9

    def test_bad_llm_response_falls_back(self):
        ev = _make_evaluator("oops I forgot JSON")
        result = ev.evaluate(RESUME, JOB_REQ)
        # FALLBACK_SCORE = 3.0 → normalized = 3.0/5.0 = 0.60
        assert abs(result.normalized_score - FALLBACK_SCORE / 5.0) < 1e-9
        assert result.evidence_quality == 0.0

    def test_markdown_code_block_parsed(self):
        # 11 words — over the 10-word threshold
        just = "Candidate demonstrates strong technical proficiency across all relevant core competencies here"
        payload = build_llm_response(
            scores={c: 4.0 for c in CRITERIA},
            justifications={c: just for c in CRITERIA},
        )
        wrapped = f"```json\n{payload}\n```"
        ev = _make_evaluator(wrapped)
        result = ev.evaluate(RESUME, JOB_REQ)
        assert result.normalized_score > 0.0
        assert result.evidence_quality == 1.0

    def test_returns_rubric_result(self):
        response = _all_score_response(3.0)
        ev = _make_evaluator(response)
        result = ev.evaluate(RESUME, JOB_REQ)
        assert isinstance(result, RubricResult)

    def test_criterion_scores_in_result(self):
        response = _all_score_response(4.0)
        ev = _make_evaluator(response)
        result = ev.evaluate(RESUME, JOB_REQ)
        assert set(result.criterion_scores.keys()) == set(CRITERIA)

    def test_resume_and_requirements_passed_to_llm(self):
        """MockLLMBackend records the prompts it receives."""
        response = _all_score_response(3.0)
        backend = MockLLMBackend(response)
        ev = RubricEvaluator(llm_backend=backend)
        ev.evaluate(RESUME, JOB_REQ)
        assert backend.last_user_prompt is not None
        assert backend.last_system_prompt is not None

    def test_llm_called_once_per_evaluate(self):
        response = _all_score_response(3.0)
        backend = MockLLMBackend(response)
        ev = RubricEvaluator(llm_backend=backend)
        ev.evaluate(RESUME, JOB_REQ)
        assert backend.call_count == 1

    def test_multiple_evaluate_calls_independent(self):
        ev = _make_evaluator(_all_score_response(5.0))
        r1 = ev.evaluate(RESUME, JOB_REQ)
        r2 = ev.evaluate(RESUME, JOB_REQ)
        assert abs(r1.normalized_score - r2.normalized_score) < 1e-9


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestProtocolConformance:
    def test_rubric_evaluator_satisfies_protocol(self):
        ev = _make_evaluator()
        assert isinstance(ev, RubricEvaluatorProtocol)

    def test_evaluate_method_exists(self):
        ev = _make_evaluator()
        assert callable(ev.evaluate)

    def test_result_has_normalized_score(self):
        response = _all_score_response(3.0)
        ev = _make_evaluator(response)
        result = ev.evaluate(RESUME, JOB_REQ)
        assert hasattr(result, "normalized_score")

    def test_result_has_evidence_quality(self):
        response = _all_score_response(3.0)
        ev = _make_evaluator(response)
        result = ev.evaluate(RESUME, JOB_REQ)
        assert hasattr(result, "evidence_quality")

    def test_result_has_criterion_scores(self):
        response = _all_score_response(3.0)
        ev = _make_evaluator(response)
        result = ev.evaluate(RESUME, JOB_REQ)
        assert hasattr(result, "criterion_scores")
        assert isinstance(result.criterion_scores, dict)


# ---------------------------------------------------------------------------
# MockLLMBackend
# ---------------------------------------------------------------------------

class TestMockLLMBackend:
    def test_returns_configured_response(self):
        backend = MockLLMBackend("hello")
        result = backend.complete("system", "user")
        assert result == "hello"

    def test_model_name_property(self):
        backend = MockLLMBackend("x")
        assert isinstance(backend.model_name, str)
        assert len(backend.model_name) > 0

    def test_records_prompts(self):
        backend = MockLLMBackend("resp")
        backend.complete("sys", "usr")
        assert backend.last_system_prompt == "sys"
        assert backend.last_user_prompt == "usr"

    def test_call_count_increments(self):
        backend = MockLLMBackend("resp")
        backend.complete("s", "u")
        backend.complete("s", "u")
        assert backend.call_count == 2


# ---------------------------------------------------------------------------
# M3 Upgrade — RubricScoreResponse (Pydantic), backends, factory
# ---------------------------------------------------------------------------

class TestRubricScoreResponse:
    """
    Tests for the Pydantic schema that instructor enforces on LLM output.
    All five criteria must be present; scores must be integers 1-5.
    """

    @pytest.fixture(autouse=True)
    def _import(self):
        from resume_pipeline.pipeline.rubric_score import RubricScoreResponse, CRITERIA
        self.RubricScoreResponse = RubricScoreResponse
        self.CRITERIA = CRITERIA

    def _valid_scores(self, override: dict | None = None) -> dict[str, int]:
        base = {c: 3 for c in self.CRITERIA}
        if override:
            base.update(override)
        return base

    def _valid_justifications(self) -> dict[str, str]:
        return {c: f"Justification for {c} criterion." for c in self.CRITERIA}

    def test_valid_response_accepted(self):
        resp = self.RubricScoreResponse(
            scores=self._valid_scores(),
            justifications=self._valid_justifications(),
        )
        assert set(resp.scores.keys()) == set(self.CRITERIA)

    def test_score_below_1_raises_validation_error(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.RubricScoreResponse(
                scores=self._valid_scores({"core_skills": 0}),
                justifications=self._valid_justifications(),
            )

    def test_score_above_5_raises_validation_error(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.RubricScoreResponse(
                scores=self._valid_scores({"core_skills": 6}),
                justifications=self._valid_justifications(),
            )

    def test_missing_required_criterion_raises_validation_error(self):
        from pydantic import ValidationError
        scores = {c: 3 for c in self.CRITERIA if c != "scope_impact"}
        with pytest.raises(ValidationError):
            self.RubricScoreResponse(
                scores=scores,
                justifications=self._valid_justifications(),
            )

    def test_all_five_criteria_required(self):
        """Scores dict with only four criteria must fail validation."""
        from pydantic import ValidationError
        scores = {c: 3 for c in list(self.CRITERIA)[:4]}
        with pytest.raises(ValidationError):
            self.RubricScoreResponse(
                scores=scores,
                justifications=self._valid_justifications(),
            )

    def test_score_of_1_is_accepted(self):
        """Boundary: minimum valid score."""
        resp = self.RubricScoreResponse(
            scores=self._valid_scores({c: 1 for c in self.CRITERIA}),
            justifications=self._valid_justifications(),
        )
        assert all(v == 1 for v in resp.scores.values())

    def test_score_of_5_is_accepted(self):
        """Boundary: maximum valid score."""
        resp = self.RubricScoreResponse(
            scores=self._valid_scores({c: 5 for c in self.CRITERIA}),
            justifications=self._valid_justifications(),
        )
        assert all(v == 5 for v in resp.scores.values())


class TestMakeRubricBackend:
    """
    Tests for the make_rubric_backend() factory function.
    Real backends (openai, anthropic) are instantiated but their underlying
    clients are never called here — lazy imports mean openai/anthropic packages
    don't need to be installed for these tests.
    """

    @pytest.fixture(autouse=True)
    def _import(self):
        from resume_pipeline.pipeline.rubric_score import (
            make_rubric_backend,
            MockLLMBackend,
            LLMBackendProtocol,
            OpenAIRubricBackend,
            AnthropicRubricBackend,
        )
        self.make_rubric_backend = make_rubric_backend
        self.MockLLMBackend = MockLLMBackend
        self.LLMBackendProtocol = LLMBackendProtocol
        self.OpenAIRubricBackend = OpenAIRubricBackend
        self.AnthropicRubricBackend = AnthropicRubricBackend

    def test_mock_backend_returns_mock_llm(self):
        backend = self.make_rubric_backend("mock")
        assert isinstance(backend, self.MockLLMBackend)

    def test_mock_backend_satisfies_protocol(self):
        backend = self.make_rubric_backend("mock")
        assert isinstance(backend, self.LLMBackendProtocol)

    def test_openai_backend_returns_correct_type(self):
        backend = self.make_rubric_backend("openai")
        assert isinstance(backend, self.OpenAIRubricBackend)

    def test_openai_backend_satisfies_protocol(self):
        backend = self.make_rubric_backend("openai")
        assert isinstance(backend, self.LLMBackendProtocol)

    def test_anthropic_backend_returns_correct_type(self):
        backend = self.make_rubric_backend("anthropic")
        assert isinstance(backend, self.AnthropicRubricBackend)

    def test_anthropic_backend_satisfies_protocol(self):
        backend = self.make_rubric_backend("anthropic")
        assert isinstance(backend, self.LLMBackendProtocol)

    def test_default_falls_back_to_mock(self, monkeypatch):
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        backend = self.make_rubric_backend()
        assert isinstance(backend, self.MockLLMBackend)

    def test_env_var_selects_openai(self, monkeypatch):
        monkeypatch.setenv("LLM_BACKEND", "openai")
        backend = self.make_rubric_backend()
        assert isinstance(backend, self.OpenAIRubricBackend)

    def test_env_var_selects_anthropic(self, monkeypatch):
        monkeypatch.setenv("LLM_BACKEND", "anthropic")
        backend = self.make_rubric_backend()
        assert isinstance(backend, self.AnthropicRubricBackend)

    def test_openai_model_name_property(self):
        backend = self.make_rubric_backend("openai")
        assert isinstance(backend.model_name, str)
        assert len(backend.model_name) > 0

    def test_anthropic_model_name_property(self):
        backend = self.make_rubric_backend("anthropic")
        assert isinstance(backend.model_name, str)
        assert len(backend.model_name) > 0


class TestOpenAIRubricBackendRetry:
    """
    Tests for tenacity retry behaviour on OpenAIRubricBackend.complete().

    All tests mock the underlying instructor client — no real API calls.
    """

    @pytest.fixture(autouse=True)
    def _import(self):
        from resume_pipeline.pipeline.rubric_score import (
            OpenAIRubricBackend,
            RubricScoreResponse,
            CRITERIA,
        )
        self.OpenAIRubricBackend = OpenAIRubricBackend
        self.RubricScoreResponse = RubricScoreResponse
        self.CRITERIA = CRITERIA

    def _valid_response(self) -> "RubricScoreResponse":
        return self.RubricScoreResponse(
            scores={c: 4 for c in self.CRITERIA},
            justifications={c: f"Strong evidence for {c} from resume." for c in self.CRITERIA},
        )

    def _make_backend(self, client_mock) -> "OpenAIRubricBackend":
        backend = self.OpenAIRubricBackend.__new__(self.OpenAIRubricBackend)
        backend._model = "gpt-4o-mini"
        backend._max_retries = 3
        backend._client = client_mock
        return backend

    def test_retries_on_rate_limit_then_succeeds(self):
        """Backend retries twice on RateLimitError, then returns the successful response."""
        import openai

        valid = self._valid_response()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            openai.RateLimitError("rate limit", response=MagicMock(), body={}),
            openai.RateLimitError("rate limit", response=MagicMock(), body={}),
            valid,
        ]
        backend = self._make_backend(mock_client)
        result = backend.complete("system", "user")

        assert result is valid
        assert mock_client.chat.completions.create.call_count == 3

    def test_reraises_after_max_retries_exhausted(self):
        """After 3 failed attempts tenacity reraises the original exception."""
        import openai

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = openai.RateLimitError(
            "rate limit", response=MagicMock(), body={}
        )
        backend = self._make_backend(mock_client)

        with pytest.raises(openai.RateLimitError):
            backend.complete("system", "user")

        assert mock_client.chat.completions.create.call_count == 3

    def test_complete_passes_prompts_to_client(self):
        """Prompts are forwarded to the instructor client unchanged."""
        valid = self._valid_response()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = valid
        backend = self._make_backend(mock_client)

        backend.complete("my_system", "my_user")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert any(m["role"] == "system" and "my_system" in m["content"] for m in messages)
        assert any(m["role"] == "user" and "my_user" in m["content"] for m in messages)


class TestRubricEvaluatorWithPydanticResponse:
    """
    RubricEvaluator must correctly handle a RubricScoreResponse object
    returned by a real backend (instructor returns the Pydantic model directly,
    not a raw JSON string).
    """

    @pytest.fixture(autouse=True)
    def _import(self):
        from resume_pipeline.pipeline.rubric_score import (
            RubricEvaluator,
            RubricScoreResponse,
            CRITERIA,
        )
        self.RubricEvaluator = RubricEvaluator
        self.RubricScoreResponse = RubricScoreResponse
        self.CRITERIA = CRITERIA

    def _make_evaluator_with_pydantic_response(self, scores: dict[str, int]) -> "RubricEvaluator":
        """Returns an evaluator whose mock backend returns a RubricScoreResponse object."""
        response = self.RubricScoreResponse(
            scores=scores,
            justifications={
                c: f"Detailed justification with more than ten words for {c} criterion here."
                for c in self.CRITERIA
            },
        )
        mock_backend = MagicMock()
        mock_backend.complete.return_value = response
        mock_backend.model_name = "mock-pydantic-v1"
        return self.RubricEvaluator(mock_backend)

    def test_evaluator_accepts_pydantic_response(self):
        evaluator = self._make_evaluator_with_pydantic_response({c: 4 for c in self.CRITERIA})
        result = evaluator.evaluate({"skills": "Python"}, {"required_skills": ["Python"]})
        assert result.normalized_score > 0.0

    def test_pydantic_response_scores_used_correctly(self):
        """All scores = 5 → normalized_score = 1.0."""
        evaluator = self._make_evaluator_with_pydantic_response({c: 5 for c in self.CRITERIA})
        result = evaluator.evaluate({}, {})
        assert abs(result.normalized_score - 1.0) < 1e-6

    def test_pydantic_response_evidence_quality_computed(self):
        evaluator = self._make_evaluator_with_pydantic_response({c: 3 for c in self.CRITERIA})
        result = evaluator.evaluate({}, {})
        assert result.evidence_quality > 0.0
