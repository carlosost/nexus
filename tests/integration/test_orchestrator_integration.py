"""
M4 Re-verification — Orchestrator integration tests.

Two test tiers:
  1. Mock-LLM wiring tests (no API key needed — always run):
     Confirms the full stage sequence executes correctly with
     RubricEvaluator(make_rubric_backend("mock")) as the rubric stage.
     These are the M4 re-verification tests: they replace StubRubricEvaluator
     with the real RubricEvaluator class wired to the mock backend.

  2. Real-LLM tests (@pytest.mark.integration @pytest.mark.slow):
     Skipped unless LLM_BACKEND env var is set to "openai" or "anthropic".
     Run in CI only: LLM_BACKEND=openai pytest -m integration

Run all (mock only):
    pytest tests/integration/test_orchestrator_integration.py -v

Run including real-LLM:
    LLM_BACKEND=openai OPENAI_API_KEY=... pytest tests/integration/ -m integration -v
"""

from __future__ import annotations

import json
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from resume_pipeline.pipeline.hard_gate import GateOutcome
from resume_pipeline.pipeline.orchestrator import PipelineInput, PipelineOrchestrator
from resume_pipeline.pipeline.rubric_score import (
    CRITERIA,
    MockLLMBackend,
    RubricEvaluator,
    RubricScoreResponse,
    make_rubric_backend,
    build_llm_response,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _mock_semantic_evaluator(score: float = 0.75) -> MagicMock:
    """Fake SemanticMatchEvaluator returning a fixed score."""
    mock = MagicMock()
    semantic_result = MagicMock()
    semantic_result.final_score = score
    semantic_result.section_scores = {"skills": score, "experience": score}
    mock.evaluate.return_value = semantic_result
    return mock


def _pass_pipeline_input(application_id: str = "app-001") -> PipelineInput:
    """
    PipelineInput that produces gate=PASS for a Senior Backend Engineer role.
    Uses the same criteria as JOB_SPEC in _seed_data.py.
    """
    return PipelineInput(
        application_id=application_id,
        job_must_haves={
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
        },
        resume_parsed={
            "total_experience_years": 7,
            "experience": "Senior Python Engineer at Acme Corp 2017-2024. Led Django migration.",
            "skills": "Python Django PostgreSQL Redis Docker REST APIs",
            "education": "BSc Computer Science 2016",
        },
        candidate_embeddings={"skills": [0.1] * 10, "experience": [0.2] * 10},
        job_embeddings={"skills": [0.1] * 10, "experience": [0.2] * 10},
        lexical_rank=1,
        semantic_rank=1,
        job_requirements={
            "required_skills": ["Python", "Django", "PostgreSQL"],
            "minimum_experience_years": 5,
        },
    )


def _fail_pipeline_input(application_id: str = "app-002") -> PipelineInput:
    """PipelineInput that produces gate=FAIL (2y < 5, no Django)."""
    return PipelineInput(
        application_id=application_id,
        job_must_haves={
            "min_experience": {"type": "years_experience", "minimum_years": 5},
            "django_required": {
                "type": "keyword_presence",
                "keywords": ["Django"],
                "sections": ["skills", "experience"],
            },
        },
        resume_parsed={
            "total_experience_years": 2,
            "experience": "Junior Python developer 2022-2024.",
            "skills": "Python Flask SQLite",
        },
        candidate_embeddings={},
        job_embeddings={},
        lexical_rank=None,
        semantic_rank=None,
        job_requirements={},
    )


def _mock_llm_response_json(score: int = 4) -> str:
    """Build a valid JSON string for MockLLMBackend with all criteria at `score`."""
    return build_llm_response(
        scores={c: score for c in CRITERIA},
        justifications={
            c: f"Strong evidence for {c}: candidate demonstrated this clearly in resume."
            for c in CRITERIA
        },
    )


def _capture_audit_events(logger_name: str = "pipeline.audit"):
    """Context manager that captures structured JSON audit events."""
    class _Capture:
        def __init__(self):
            self.events: list[dict] = []
            self._handler = None

        def __enter__(self):
            class _H(logging.Handler):
                def emit(inner_self, record):
                    msg = record.getMessage()
                    if msg.strip().startswith("{"):
                        try:
                            self.events.append(json.loads(msg))
                        except json.JSONDecodeError:
                            pass
            self._handler = _H()
            log = logging.getLogger(logger_name)
            log.setLevel(logging.INFO)
            log.addHandler(self._handler)
            return self

        def __exit__(self, *_):
            logging.getLogger(logger_name).removeHandler(self._handler)

    return _Capture()


# ---------------------------------------------------------------------------
# 1. Mock-LLM wiring tests (no API key required)
# ---------------------------------------------------------------------------

class TestOrchestratorWithRealRubricEvaluatorMockLLM:
    """
    M4 re-verification: confirms the orchestrator correctly wires
    RubricEvaluator backed by MockLLMBackend instead of StubRubricEvaluator.

    These tests are the concrete proof that M3 and M4 are integrated:
    - RubricEvaluator.evaluate() is called (not StubRubricEvaluator.evaluate())
    - LLM prompt is built and passed to the backend
    - Response is parsed into RubricResult
    - FinalScoreCalculator uses the RubricResult
    """

    @pytest.fixture
    def orchestrator(self):
        rubric_backend = MockLLMBackend(_mock_llm_response_json(score=4))
        return PipelineOrchestrator(
            semantic_evaluator=_mock_semantic_evaluator(score=0.75),
            rubric_evaluator=RubricEvaluator(rubric_backend),
        )

    def test_pass_path_executes_all_three_stages(self, orchestrator):
        result = orchestrator.run(_pass_pipeline_input())
        assert "hard_gate" in result.stages_executed
        assert "semantic_match" in result.stages_executed
        assert "rubric" in result.stages_executed
        assert len(result.stages_executed) == 3

    def test_pass_path_gate_outcome_is_pass(self, orchestrator):
        result = orchestrator.run(_pass_pipeline_input())
        assert result.gate_outcome == GateOutcome.PASS
        assert result.gate_passed is True

    def test_pass_path_rubric_score_is_populated(self, orchestrator):
        result = orchestrator.run(_pass_pipeline_input())
        assert result.rubric_score is not None
        assert 0.0 < result.rubric_score <= 1.0

    def test_pass_path_final_score_is_nonzero(self, orchestrator):
        result = orchestrator.run(_pass_pipeline_input())
        assert result.final_score > 0.0

    def test_pass_path_evidence_quality_is_populated(self, orchestrator):
        """All justifications have >= 10 words → evidence_quality > 0."""
        result = orchestrator.run(_pass_pipeline_input())
        assert result.evidence_quality is not None
        assert result.evidence_quality > 0.0

    def test_fail_path_short_circuits_after_gate(self, orchestrator):
        result = orchestrator.run(_fail_pipeline_input())
        assert result.gate_outcome == GateOutcome.FAIL
        assert result.stages_executed == ["hard_gate"]
        assert result.final_score == 0.0
        assert result.rubric_score is None

    def test_fail_path_semantic_and_rubric_are_none(self, orchestrator):
        result = orchestrator.run(_fail_pipeline_input())
        assert result.semantic_score is None
        assert result.rubric_score is None
        assert result.evidence_quality is None

    def test_rubric_criterion_scores_all_present(self, orchestrator):
        result = orchestrator.run(_pass_pipeline_input())
        assert result.rubric_criterion_scores is not None
        assert set(result.rubric_criterion_scores.keys()) == set(CRITERIA)

    def test_llm_backend_actually_called(self):
        """Confirm RubricEvaluator.evaluate() (not StubRubricEvaluator) is in the hot path."""
        backend = MockLLMBackend(_mock_llm_response_json(score=3))
        orchestrator = PipelineOrchestrator(
            semantic_evaluator=_mock_semantic_evaluator(),
            rubric_evaluator=RubricEvaluator(backend),
        )
        orchestrator.run(_pass_pipeline_input())
        assert backend.call_count == 1, (
            "MockLLMBackend.complete() should have been called exactly once "
            "(confirms RubricEvaluator is wired, not StubRubricEvaluator)"
        )

    def test_llm_prompt_contains_resume_data(self):
        """The user prompt passed to the LLM must include resume content."""
        backend = MockLLMBackend(_mock_llm_response_json(score=3))
        orchestrator = PipelineOrchestrator(
            semantic_evaluator=_mock_semantic_evaluator(),
            rubric_evaluator=RubricEvaluator(backend),
        )
        orchestrator.run(_pass_pipeline_input())
        assert backend.last_user_prompt is not None
        assert "Python" in backend.last_user_prompt

    def test_observability_records_all_stages(self, orchestrator):
        from resume_pipeline.observability import PipelineObservability
        obs = PipelineObservability()
        orchestrator._obs = obs
        orchestrator.run(_pass_pipeline_input())
        stage_names = [r.stage for r in obs._records]
        assert "hard_gate" in stage_names
        assert "semantic_match" in stage_names
        assert "rubric" in stage_names

    def test_audit_log_emits_score_computed_event(self, orchestrator):
        with _capture_audit_events() as cap:
            orchestrator.run(_pass_pipeline_input())
        score_events = [e for e in cap.events if e.get("event") == "score_computed"]
        assert len(score_events) >= 1

    def test_audit_log_score_computed_has_model_name(self, orchestrator):
        """After M4 re-verify, score_computed audit event must include model_name."""
        with _capture_audit_events() as cap:
            orchestrator.run(_pass_pipeline_input())
        score_event = next(
            (e for e in cap.events if e.get("event") == "score_computed"), None
        )
        assert score_event is not None
        assert "model_name" in score_event, (
            f"score_computed audit event missing 'model_name' field. "
            f"Event was: {score_event}"
        )

    def test_confidence_is_pass_on_gate_pass(self, orchestrator):
        from resume_pipeline.pipeline.orchestrator import CONFIDENCE_GATE_PASS
        result = orchestrator.run(_pass_pipeline_input())
        assert result.confidence == CONFIDENCE_GATE_PASS

    def test_multiple_applications_are_independent(self):
        """Two pipeline runs on different inputs produce independent results."""
        backend = MockLLMBackend(_mock_llm_response_json(score=4))
        evaluator = RubricEvaluator(backend)
        orchestrator = PipelineOrchestrator(
            semantic_evaluator=_mock_semantic_evaluator(),
            rubric_evaluator=evaluator,
        )
        pass_result = orchestrator.run(_pass_pipeline_input("app-pass"))
        fail_result = orchestrator.run(_fail_pipeline_input("app-fail"))

        assert pass_result.final_score > 0.0
        assert fail_result.final_score == 0.0
        assert pass_result.application_id == "app-pass"
        assert fail_result.application_id == "app-fail"


class TestOrchestratorDefaultRubricBackend:
    """
    Confirms PipelineOrchestrator() with no arguments uses
    RubricEvaluator(make_rubric_backend()) as the rubric stage,
    NOT StubRubricEvaluator.
    """

    def test_default_rubric_is_rubric_evaluator_not_stub(self, monkeypatch):
        from resume_pipeline.pipeline.rubric_protocol import StubRubricEvaluator

        monkeypatch.setenv("LLM_BACKEND", "mock")
        # Inject mock semantic to avoid embedding model download
        orchestrator = PipelineOrchestrator(
            semantic_evaluator=_mock_semantic_evaluator(),
        )
        assert isinstance(orchestrator._rubric, RubricEvaluator), (
            f"Expected orchestrator._rubric to be RubricEvaluator; "
            f"got {type(orchestrator._rubric)}. "
            f"StubRubricEvaluator must no longer be the default."
        )
        assert not isinstance(orchestrator._rubric, StubRubricEvaluator)

    def test_default_backend_is_mock_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        orchestrator = PipelineOrchestrator(
            semantic_evaluator=_mock_semantic_evaluator(),
        )
        # _rubric._llm should be a MockLLMBackend when env var is unset
        assert isinstance(orchestrator._rubric._llm, MockLLMBackend)


# ---------------------------------------------------------------------------
# 2. Real-LLM integration tests (skipped unless LLM_BACKEND is set)
# ---------------------------------------------------------------------------

_REAL_LLM_BACKEND = os.environ.get("LLM_BACKEND", "mock")
_SKIP_REAL_LLM = _REAL_LLM_BACKEND == "mock"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(
    _SKIP_REAL_LLM,
    reason="Set LLM_BACKEND=openai or LLM_BACKEND=anthropic to run real-LLM tests",
)
class TestOrchestratorRealLLM:
    """
    Integration tests against real OpenAI / Anthropic APIs.

    Requires:
        LLM_BACKEND=openai OPENAI_API_KEY=<key> pytest -m integration
        LLM_BACKEND=anthropic ANTHROPIC_API_KEY=<key> pytest -m integration

    These tests are NOT run in the standard test suite.
    They exist to verify the real wiring before a production deployment.
    """

    @pytest.fixture
    def orchestrator(self):
        return PipelineOrchestrator(
            semantic_evaluator=_mock_semantic_evaluator(score=0.75),
        )

    def test_real_llm_pass_path_executes_all_stages(self, orchestrator):
        result = orchestrator.run(_pass_pipeline_input())
        assert result.stages_executed == ["hard_gate", "semantic_match", "rubric"]

    def test_real_llm_rubric_score_is_nonzero(self, orchestrator):
        result = orchestrator.run(_pass_pipeline_input())
        assert result.rubric_score is not None
        assert result.rubric_score > 0.0

    def test_real_llm_criterion_scores_all_present(self, orchestrator):
        result = orchestrator.run(_pass_pipeline_input())
        assert result.rubric_criterion_scores is not None
        assert set(result.rubric_criterion_scores.keys()) == set(CRITERIA)

    def test_real_llm_audit_event_has_model_name(self, orchestrator):
        with _capture_audit_events() as cap:
            orchestrator.run(_pass_pipeline_input())
        score_event = next(
            (e for e in cap.events if e.get("event") == "score_computed"), None
        )
        assert score_event is not None
        model_name = score_event.get("model_name")
        assert model_name and model_name != "unknown", (
            f"Expected real model name in audit log; got: {model_name}"
        )
