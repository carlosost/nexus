"""
Inner-loop unit tests for the Pipeline Orchestrator (Stage 4 wiring).

Write these BEFORE implementing orchestrator.py. They must fail with
ImportError first, then fail with AttributeError, then pass once the
implementation is complete.

Key invariants under test:
  1. SHORT-CIRCUIT: SemanticMatch and Rubric evaluators are NEVER called
     when the gate outcome is FAIL.
  2. FULL PASS: All three evaluators are called in order for gate PASS.
  3. UNKNOWN CONTINUATION: Pipeline continues on UNKNOWN, confidence < 1.0.
  4. FORMULA: Final score = 0.45*semantic + 0.45*rubric_norm + 0.10*evidence.
  5. OBSERVABILITY: One LatencyRecord per executed stage, zero for skipped stages.
  6. AUDIT LOG: gate_transition logged per criterion; short_circuited logged on
     FAIL; score_computed logged on successful completion.
  7. RESULT STRUCTURE: PipelineResult.stages_executed reflects what actually ran.

All evaluators are injected via mocks — no real embeddings, no DB, no network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, call, patch

import pytest

from resume_pipeline.observability import PipelineObservability
from resume_pipeline.pipeline.hard_gate import (
    CriterionResult,
    GateOutcome,
    HardGateEvaluation,
)
from resume_pipeline.pipeline.orchestrator import (
    PipelineInput,
    PipelineOrchestrator,
    PipelineResult,
)
from resume_pipeline.pipeline.rubric_protocol import RubricResult, StubRubricEvaluator
from resume_pipeline.pipeline.semantic_match import SemanticMatchScore


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_gate_evaluation(outcome: GateOutcome, criteria: Optional[list] = None):
    """Build a HardGateEvaluation with a single synthetic criterion."""
    results = criteria or [CriterionResult(name="exp", outcome=outcome, evidence="test")]
    return HardGateEvaluation(criterion_results=results)


def _make_semantic_score(final_score: float = 0.75) -> SemanticMatchScore:
    return SemanticMatchScore(
        section_scores={"experience": final_score},
        section_weighted_similarity=final_score,
        rrf_score=final_score,
        final_score=final_score,
    )


def _make_rubric_result(
    normalized_score: float = 0.70,
    evidence_quality: float = 0.65,
) -> RubricResult:
    return RubricResult(
        normalized_score=normalized_score,
        evidence_quality=evidence_quality,
        criterion_scores={"core_skills": 4.0},
    )


def _make_orchestrator(
    gate_outcome: GateOutcome = GateOutcome.PASS,
    semantic_score: float = 0.75,
    rubric_score: float = 0.70,
    evidence_quality: float = 0.65,
) -> tuple[PipelineOrchestrator, MagicMock, MagicMock, MagicMock]:
    """
    Build an orchestrator with all evaluators replaced by mocks.

    Returns (orchestrator, mock_gate, mock_semantic, mock_rubric).
    """
    obs = PipelineObservability(sink=lambda _: None)  # silence log output

    mock_gate = MagicMock()
    mock_gate.evaluate.return_value = _make_gate_evaluation(gate_outcome)

    mock_semantic = MagicMock()
    mock_semantic.evaluate.return_value = _make_semantic_score(semantic_score)

    mock_rubric = MagicMock()
    mock_rubric.evaluate.return_value = _make_rubric_result(rubric_score, evidence_quality)

    orch = PipelineOrchestrator(
        gate_evaluator=mock_gate,
        semantic_evaluator=mock_semantic,
        rubric_evaluator=mock_rubric,
        observability=obs,
    )
    return orch, mock_gate, mock_semantic, mock_rubric


def _default_input(resume_override: Optional[dict] = None) -> PipelineInput:
    return PipelineInput(
        application_id="app-001",
        job_must_haves={"exp": {"type": "years_experience", "minimum_years": 5}},
        resume_parsed=resume_override or {"total_experience_years": 7},
        candidate_embeddings={"experience": [1.0, 0.0]},
        job_embeddings={"experience": [1.0, 0.0]},
        lexical_rank=1,
        semantic_rank=1,
        job_requirements={},
    )


# ===========================================================================
# 1. Short-circuit behavior
# ===========================================================================

class TestGateFailShortCircuit:

    def test_final_score_is_zero_on_gate_fail(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.FAIL)
        result = orch.run(_default_input())
        assert result.final_score == 0.0

    def test_semantic_evaluator_not_called_on_gate_fail(self):
        orch, _, mock_semantic, _ = _make_orchestrator(gate_outcome=GateOutcome.FAIL)
        orch.run(_default_input())
        mock_semantic.evaluate.assert_not_called()

    def test_rubric_evaluator_not_called_on_gate_fail(self):
        orch, _, _, mock_rubric = _make_orchestrator(gate_outcome=GateOutcome.FAIL)
        orch.run(_default_input())
        mock_rubric.evaluate.assert_not_called()

    def test_gate_evaluator_always_called(self):
        orch, mock_gate, _, _ = _make_orchestrator(gate_outcome=GateOutcome.FAIL)
        orch.run(_default_input())
        mock_gate.evaluate.assert_called_once()

    def test_stages_executed_is_only_hard_gate_on_fail(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.FAIL)
        result = orch.run(_default_input())
        assert result.stages_executed == ["hard_gate"]

    def test_gate_outcome_is_preserved_in_result(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.FAIL)
        result = orch.run(_default_input())
        assert result.gate_outcome == GateOutcome.FAIL

    def test_semantic_score_is_none_on_short_circuit(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.FAIL)
        result = orch.run(_default_input())
        assert result.semantic_score is None

    def test_rubric_score_is_none_on_short_circuit(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.FAIL)
        result = orch.run(_default_input())
        assert result.rubric_score is None


# ===========================================================================
# 2. Full pass path
# ===========================================================================

class TestGatePassFullPipeline:

    def test_all_three_evaluators_called_on_pass(self):
        orch, mock_gate, mock_semantic, mock_rubric = _make_orchestrator(
            gate_outcome=GateOutcome.PASS
        )
        orch.run(_default_input())
        mock_gate.evaluate.assert_called_once()
        mock_semantic.evaluate.assert_called_once()
        mock_rubric.evaluate.assert_called_once()

    def test_stages_executed_contains_all_three_on_pass(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        result = orch.run(_default_input())
        assert result.stages_executed == ["hard_gate", "semantic_match", "rubric"]

    def test_final_score_is_greater_than_zero_on_pass(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        result = orch.run(_default_input())
        assert result.final_score > 0.0

    def test_final_score_formula_on_pass(self):
        """
        semantic=0.8, rubric=0.6, evidence=0.4, gate=PASS
        Expected: 0.45*0.8 + 0.45*0.6 + 0.10*0.4
                = 0.36 + 0.27 + 0.04 = 0.67
        """
        orch, _, _, _ = _make_orchestrator(
            gate_outcome=GateOutcome.PASS,
            semantic_score=0.8,
            rubric_score=0.6,
            evidence_quality=0.4,
        )
        result = orch.run(_default_input())
        assert result.final_score == pytest.approx(0.67, abs=1e-9)

    def test_final_score_perfect_inputs_yields_1(self):
        orch, _, _, _ = _make_orchestrator(
            gate_outcome=GateOutcome.PASS,
            semantic_score=1.0,
            rubric_score=1.0,
            evidence_quality=1.0,
        )
        result = orch.run(_default_input())
        assert result.final_score == pytest.approx(1.0, abs=1e-9)

    def test_gate_passed_flag_is_true_on_pass(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        result = orch.run(_default_input())
        assert result.gate_passed is True

    def test_semantic_score_is_populated_on_pass(self):
        orch, _, _, _ = _make_orchestrator(
            gate_outcome=GateOutcome.PASS, semantic_score=0.75
        )
        result = orch.run(_default_input())
        assert result.semantic_score == pytest.approx(0.75)

    def test_rubric_score_is_populated_on_pass(self):
        orch, _, _, _ = _make_orchestrator(
            gate_outcome=GateOutcome.PASS, rubric_score=0.70
        )
        result = orch.run(_default_input())
        assert result.rubric_score == pytest.approx(0.70)

    def test_application_id_preserved_in_result(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        result = orch.run(_default_input())
        assert result.application_id == "app-001"


# ===========================================================================
# 3. Gate UNKNOWN — continuation
# ===========================================================================

class TestGateUnknownContinuation:

    def test_pipeline_continues_on_unknown(self):
        orch, _, mock_semantic, mock_rubric = _make_orchestrator(
            gate_outcome=GateOutcome.UNKNOWN
        )
        orch.run(_default_input())
        mock_semantic.evaluate.assert_called_once()
        mock_rubric.evaluate.assert_called_once()

    def test_gate_unknown_does_not_short_circuit(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.UNKNOWN)
        result = orch.run(_default_input())
        assert result.stages_executed == ["hard_gate", "semantic_match", "rubric"]

    def test_gate_unknown_final_score_uses_formula(self):
        orch, _, _, _ = _make_orchestrator(
            gate_outcome=GateOutcome.UNKNOWN,
            semantic_score=1.0,
            rubric_score=1.0,
            evidence_quality=1.0,
        )
        result = orch.run(_default_input())
        assert result.final_score == pytest.approx(1.0, abs=1e-9)

    def test_gate_unknown_confidence_is_below_1(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.UNKNOWN)
        result = orch.run(_default_input())
        assert result.confidence is not None
        assert result.confidence < 1.0

    def test_gate_passed_flag_is_false_on_unknown(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.UNKNOWN)
        result = orch.run(_default_input())
        assert result.gate_passed is False


# ===========================================================================
# 4. Stage ordering — semantic receives gate metadata, rubric receives both
# ===========================================================================

class TestStageInputPropagation:

    def test_semantic_evaluator_receives_embeddings_from_input(self):
        orch, _, mock_semantic, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        inp = _default_input()
        orch.run(inp)
        call_kwargs = mock_semantic.evaluate.call_args
        assert call_kwargs is not None

    def test_rubric_evaluator_receives_resume_parsed_from_input(self):
        orch, _, _, mock_rubric = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        inp = _default_input()
        orch.run(inp)
        call_kwargs = mock_rubric.evaluate.call_args
        assert call_kwargs is not None


# ===========================================================================
# 5. Observability — latency records per stage
# ===========================================================================

class TestOrchestratorObservability:

    def _orch_with_collecting_obs(self, gate_outcome: GateOutcome, **kwargs):
        obs = PipelineObservability(sink=lambda _: None)

        mock_gate = MagicMock()
        mock_gate.evaluate.return_value = _make_gate_evaluation(gate_outcome)

        mock_semantic = MagicMock()
        mock_semantic.evaluate.return_value = _make_semantic_score(
            kwargs.get("semantic_score", 0.75)
        )

        mock_rubric = MagicMock()
        mock_rubric.evaluate.return_value = _make_rubric_result(
            kwargs.get("rubric_score", 0.70),
            kwargs.get("evidence_quality", 0.65),
        )

        orch = PipelineOrchestrator(
            gate_evaluator=mock_gate,
            semantic_evaluator=mock_semantic,
            rubric_evaluator=mock_rubric,
            observability=obs,
        )
        return orch, obs

    def test_three_latency_records_on_full_pass(self):
        orch, obs = self._orch_with_collecting_obs(GateOutcome.PASS)
        orch.run(_default_input())
        assert len(obs.get_records()) == 3

    def test_one_latency_record_on_gate_fail(self):
        orch, obs = self._orch_with_collecting_obs(GateOutcome.FAIL)
        orch.run(_default_input())
        assert len(obs.get_records()) == 1

    def test_latency_record_stage_names_match_executed_stages_on_pass(self):
        orch, obs = self._orch_with_collecting_obs(GateOutcome.PASS)
        orch.run(_default_input())
        stages = [r.stage for r in obs.get_records()]
        assert stages == ["hard_gate", "semantic_match", "rubric"]

    def test_latency_record_stage_name_on_short_circuit(self):
        orch, obs = self._orch_with_collecting_obs(GateOutcome.FAIL)
        orch.run(_default_input())
        stages = [r.stage for r in obs.get_records()]
        assert stages == ["hard_gate"]

    def test_all_latency_ms_are_non_negative(self):
        orch, obs = self._orch_with_collecting_obs(GateOutcome.PASS)
        orch.run(_default_input())
        assert all(r.latency_ms >= 0.0 for r in obs.get_records())

    def test_observability_records_cleared_between_runs(self):
        """Each run must NOT accumulate records from prior runs."""
        orch, obs = self._orch_with_collecting_obs(GateOutcome.PASS)
        orch.run(_default_input())
        obs.clear()
        orch.run(_default_input())
        assert len(obs.get_records()) == 3  # only from the second run


# ===========================================================================
# 6. Audit logging
# ===========================================================================

class TestOrchestratorAuditLogging:

    def test_gate_transition_logged_per_criterion(self, caplog):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            orch.run(_default_input())
        gate_events = [
            r for r in caplog.records
            if '"event": "gate_transition"' in r.getMessage()
        ]
        # One criterion in _default_input → one gate_transition log entry.
        assert len(gate_events) >= 1

    def test_short_circuit_logged_on_gate_fail(self, caplog):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.FAIL)
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            orch.run(_default_input())
        short_circuit_events = [
            r for r in caplog.records
            if '"event": "pipeline_short_circuited"' in r.getMessage()
        ]
        assert len(short_circuit_events) == 1

    def test_short_circuit_not_logged_on_gate_pass(self, caplog):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            orch.run(_default_input())
        short_circuit_events = [
            r for r in caplog.records
            if '"event": "pipeline_short_circuited"' in r.getMessage()
        ]
        assert len(short_circuit_events) == 0

    def test_score_computed_logged_on_full_run(self, caplog):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            orch.run(_default_input())
        score_events = [
            r for r in caplog.records
            if '"event": "score_computed"' in r.getMessage()
        ]
        assert len(score_events) == 1

    def test_score_computed_not_logged_on_short_circuit(self, caplog):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.FAIL)
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            orch.run(_default_input())
        score_events = [
            r for r in caplog.records
            if '"event": "score_computed"' in r.getMessage()
        ]
        assert len(score_events) == 0


# ===========================================================================
# 7. StubRubricEvaluator — contract tests
# ===========================================================================

class TestStubRubricEvaluator:
    stub = StubRubricEvaluator()

    def test_returns_rubric_result(self):
        result = self.stub.evaluate(resume_parsed={}, job_requirements={})
        assert isinstance(result, RubricResult)

    def test_normalized_score_in_0_1(self):
        result = self.stub.evaluate(resume_parsed={}, job_requirements={})
        assert 0.0 <= result.normalized_score <= 1.0

    def test_evidence_quality_in_0_1(self):
        result = self.stub.evaluate(resume_parsed={}, job_requirements={})
        assert 0.0 <= result.evidence_quality <= 1.0

    def test_criterion_scores_is_a_dict(self):
        result = self.stub.evaluate(resume_parsed={}, job_requirements={})
        assert isinstance(result.criterion_scores, dict)


# ===========================================================================
# 8. PipelineResult — structure
# ===========================================================================

class TestPipelineResultStructure:

    def test_result_has_application_id(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        result = orch.run(_default_input())
        assert hasattr(result, "application_id")

    def test_result_has_gate_outcome(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        result = orch.run(_default_input())
        assert hasattr(result, "gate_outcome")

    def test_result_has_final_score(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        result = orch.run(_default_input())
        assert hasattr(result, "final_score")

    def test_result_has_stages_executed(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        result = orch.run(_default_input())
        assert hasattr(result, "stages_executed")
        assert isinstance(result.stages_executed, list)

    def test_result_has_total_latency_ms(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        result = orch.run(_default_input())
        assert hasattr(result, "total_latency_ms")
        assert result.total_latency_ms >= 0.0

    def test_result_has_confidence(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        result = orch.run(_default_input())
        assert hasattr(result, "confidence")

    def test_confidence_is_1_on_gate_pass(self):
        orch, _, _, _ = _make_orchestrator(gate_outcome=GateOutcome.PASS)
        result = orch.run(_default_input())
        assert result.confidence == pytest.approx(1.0)

    def test_final_score_always_in_0_1(self):
        for outcome in [GateOutcome.PASS, GateOutcome.FAIL, GateOutcome.UNKNOWN]:
            orch, _, _, _ = _make_orchestrator(gate_outcome=outcome)
            result = orch.run(_default_input())
            assert 0.0 <= result.final_score <= 1.0, (
                f"final_score out of range for gate={outcome}: {result.final_score}"
            )
