"""
Inner-loop unit tests for the Hard Gate (Stage 1).

These tests must ALL be written before the implementation in hard_gate.py exists.
Run them first — confirm they fail with ImportError or AttributeError, then
implement the module until every test is green.

Test structure mirrors the domain:
  1. GateOutcome aggregation on HardGateEvaluation
  2. Individual criterion handlers on HardGateEvaluator
  3. Full evaluate() method integration
  4. FinalScoreCalculator — weights constant and formula
  5. FinalScoreWeights — sum-to-one invariant
"""

from __future__ import annotations

import pytest

from resume_pipeline.pipeline.hard_gate import (
    CriterionResult,
    GateOutcome,
    HardGateEvaluation,
    HardGateEvaluator,
)
from resume_pipeline.pipeline.final_score import (
    FinalScoreCalculator,
    FinalScoreWeights,
)


# ===========================================================================
# 1. GateOutcome — aggregation logic on HardGateEvaluation
# ===========================================================================

class TestGateOutcomeAggregation:

    def test_no_criteria_yields_unknown(self):
        """
        Zero criteria evaluated → UNKNOWN.
        We cannot confirm a pass with zero evidence.
        """
        evaluation = HardGateEvaluation(criterion_results=[])
        assert evaluation.outcome == GateOutcome.UNKNOWN

    def test_all_pass_yields_pass(self):
        evaluation = HardGateEvaluation(criterion_results=[
            CriterionResult(name="exp", outcome=GateOutcome.PASS),
            CriterionResult(name="skills", outcome=GateOutcome.PASS),
        ])
        assert evaluation.outcome == GateOutcome.PASS

    def test_single_fail_yields_fail(self):
        evaluation = HardGateEvaluation(criterion_results=[
            CriterionResult(name="exp", outcome=GateOutcome.FAIL),
            CriterionResult(name="skills", outcome=GateOutcome.PASS),
        ])
        assert evaluation.outcome == GateOutcome.FAIL

    def test_unknown_with_pass_yields_unknown(self):
        evaluation = HardGateEvaluation(criterion_results=[
            CriterionResult(name="certs", outcome=GateOutcome.UNKNOWN),
            CriterionResult(name="skills", outcome=GateOutcome.PASS),
        ])
        assert evaluation.outcome == GateOutcome.UNKNOWN

    def test_fail_takes_precedence_over_unknown(self):
        """FAIL always wins over UNKNOWN — safety-first gate."""
        evaluation = HardGateEvaluation(criterion_results=[
            CriterionResult(name="exp", outcome=GateOutcome.FAIL),
            CriterionResult(name="certs", outcome=GateOutcome.UNKNOWN),
        ])
        assert evaluation.outcome == GateOutcome.FAIL

    def test_all_unknown_yields_unknown(self):
        evaluation = HardGateEvaluation(criterion_results=[
            CriterionResult(name="a", outcome=GateOutcome.UNKNOWN),
            CriterionResult(name="b", outcome=GateOutcome.UNKNOWN),
        ])
        assert evaluation.outcome == GateOutcome.UNKNOWN

    def test_fail_takes_precedence_over_unknown_and_pass(self):
        evaluation = HardGateEvaluation(criterion_results=[
            CriterionResult(name="a", outcome=GateOutcome.PASS),
            CriterionResult(name="b", outcome=GateOutcome.UNKNOWN),
            CriterionResult(name="c", outcome=GateOutcome.FAIL),
        ])
        assert evaluation.outcome == GateOutcome.FAIL


# ===========================================================================
# 2a. years_experience criterion
# ===========================================================================

class TestYearsExperienceCriterion:
    evaluator = HardGateEvaluator()

    def test_candidate_exceeds_minimum(self):
        result = self.evaluator._check_years_experience(
            name="exp",
            config={"minimum_years": 5},
            resume={"total_experience_years": 8},
        )
        assert result.outcome == GateOutcome.PASS

    def test_candidate_exactly_at_minimum(self):
        """Boundary: exactly equal is a PASS."""
        result = self.evaluator._check_years_experience(
            name="exp",
            config={"minimum_years": 5},
            resume={"total_experience_years": 5},
        )
        assert result.outcome == GateOutcome.PASS

    def test_candidate_below_minimum(self):
        result = self.evaluator._check_years_experience(
            name="exp",
            config={"minimum_years": 5},
            resume={"total_experience_years": 3},
        )
        assert result.outcome == GateOutcome.FAIL

    def test_missing_experience_field_is_unknown(self):
        result = self.evaluator._check_years_experience(
            name="exp",
            config={"minimum_years": 5},
            resume={},
        )
        assert result.outcome == GateOutcome.UNKNOWN

    def test_missing_minimum_years_in_config_is_unknown(self):
        result = self.evaluator._check_years_experience(
            name="exp",
            config={},  # no "minimum_years" key
            resume={"total_experience_years": 7},
        )
        assert result.outcome == GateOutcome.UNKNOWN

    def test_result_carries_evidence_string(self):
        result = self.evaluator._check_years_experience(
            name="exp",
            config={"minimum_years": 5},
            resume={"total_experience_years": 3},
        )
        assert result.evidence is not None
        assert len(result.evidence) > 0

    def test_fractional_years_are_compared_correctly(self):
        """Resume may express experience as 4.5 years — still FAIL vs 5."""
        result = self.evaluator._check_years_experience(
            name="exp",
            config={"minimum_years": 5},
            resume={"total_experience_years": 4.5},
        )
        assert result.outcome == GateOutcome.FAIL


# ===========================================================================
# 2b. keyword_presence criterion
# ===========================================================================

class TestKeywordPresenceCriterion:
    evaluator = HardGateEvaluator()

    def test_keyword_found_in_section(self):
        result = self.evaluator._check_keyword_presence(
            name="python",
            config={"keywords": ["Python"], "sections": ["skills"]},
            resume={"skills": "Python Django PostgreSQL"},
        )
        assert result.outcome == GateOutcome.PASS

    def test_keyword_not_found(self):
        result = self.evaluator._check_keyword_presence(
            name="python",
            config={"keywords": ["Python"], "sections": ["skills"]},
            resume={"skills": "Java Spring Boot"},
        )
        assert result.outcome == GateOutcome.FAIL

    def test_keyword_search_is_case_insensitive(self):
        result = self.evaluator._check_keyword_presence(
            name="python",
            config={"keywords": ["PYTHON"], "sections": ["skills"]},
            resume={"skills": "python 3.11"},
        )
        assert result.outcome == GateOutcome.PASS

    def test_partial_keyword_list_fails_by_default(self):
        """Default match_threshold is 1.0 — any missing keyword is a FAIL."""
        result = self.evaluator._check_keyword_presence(
            name="block",
            config={"keywords": ["Python", "Kubernetes"], "sections": ["skills"]},
            resume={"skills": "Python"},
        )
        assert result.outcome == GateOutcome.FAIL

    def test_partial_match_with_lower_threshold_passes(self):
        result = self.evaluator._check_keyword_presence(
            name="block",
            config={
                "keywords": ["Python", "Kubernetes"],
                "sections": ["skills"],
                "match_threshold": 0.5,
            },
            resume={"skills": "Python"},
        )
        assert result.outcome == GateOutcome.PASS

    def test_search_spans_multiple_sections(self):
        result = self.evaluator._check_keyword_presence(
            name="python",
            config={"keywords": ["Python"], "sections": ["skills", "experience"]},
            resume={
                "skills": "Django",
                "experience": "Built ETL pipelines in Python",
            },
        )
        assert result.outcome == GateOutcome.PASS

    def test_empty_keywords_list_is_unknown(self):
        """A criterion with no keywords is misconfigured → UNKNOWN."""
        result = self.evaluator._check_keyword_presence(
            name="misc",
            config={"keywords": [], "sections": ["skills"]},
            resume={"skills": "Python"},
        )
        assert result.outcome == GateOutcome.UNKNOWN

    def test_missing_section_is_treated_as_empty_string(self):
        """Section absent from resume is not an error — treated as empty."""
        result = self.evaluator._check_keyword_presence(
            name="python",
            config={"keywords": ["Python"], "sections": ["skills"]},
            resume={},  # no "skills" key
        )
        assert result.outcome == GateOutcome.FAIL

    def test_result_evidence_lists_missing_keywords_on_fail(self):
        result = self.evaluator._check_keyword_presence(
            name="block",
            config={"keywords": ["Python", "Kubernetes"], "sections": ["skills"]},
            resume={"skills": "Python"},
        )
        assert result.outcome == GateOutcome.FAIL
        assert result.evidence is not None
        assert "Kubernetes" in result.evidence


# ===========================================================================
# 2c. certification criterion
# ===========================================================================

class TestCertificationCriterion:
    evaluator = HardGateEvaluator()

    def test_required_cert_is_present(self):
        result = self.evaluator._check_certification(
            name="aws",
            config={"required": ["AWS Solutions Architect"]},
            resume={"certifications": ["AWS Solutions Architect", "GCP Associate"]},
        )
        assert result.outcome == GateOutcome.PASS

    def test_cert_comparison_is_case_insensitive(self):
        result = self.evaluator._check_certification(
            name="aws",
            config={"required": ["aws solutions architect"]},
            resume={"certifications": ["AWS Solutions Architect"]},
        )
        assert result.outcome == GateOutcome.PASS

    def test_required_cert_is_missing(self):
        result = self.evaluator._check_certification(
            name="aws",
            config={"required": ["AWS Solutions Architect"]},
            resume={"certifications": ["GCP Associate"]},
        )
        assert result.outcome == GateOutcome.FAIL

    def test_empty_certifications_list_is_fail_not_unknown(self):
        """
        resume_parsed["certifications"] = [] means the parser found the section
        but it was empty — that is a FAIL, not UNKNOWN.
        """
        result = self.evaluator._check_certification(
            name="aws",
            config={"required": ["AWS Solutions Architect"]},
            resume={"certifications": []},
        )
        assert result.outcome == GateOutcome.FAIL

    def test_absent_certifications_key_is_unknown(self):
        """
        When the key is completely absent, the parser didn't find the section —
        we cannot confirm absence, so this is UNKNOWN.
        """
        result = self.evaluator._check_certification(
            name="aws",
            config={"required": ["AWS Solutions Architect"]},
            resume={},
        )
        assert result.outcome == GateOutcome.UNKNOWN

    def test_partial_cert_match_fails(self):
        """Having some but not all required certs is a FAIL."""
        result = self.evaluator._check_certification(
            name="multi_cert",
            config={"required": ["AWS Solutions Architect", "CKA"]},
            resume={"certifications": ["AWS Solutions Architect"]},
        )
        assert result.outcome == GateOutcome.FAIL


# ===========================================================================
# 2d. Unknown criterion type
# ===========================================================================

class TestUnknownCriterionType:
    evaluator = HardGateEvaluator()

    def test_unsupported_type_is_unknown(self):
        result = self.evaluator._dispatch(
            name="mystery",
            config={"type": "unsupported_xyz"},
            resume={},
        )
        assert result.outcome == GateOutcome.UNKNOWN

    def test_missing_type_key_is_unknown(self):
        result = self.evaluator._dispatch(
            name="mystery",
            config={},  # no "type" key
            resume={},
        )
        assert result.outcome == GateOutcome.UNKNOWN


# ===========================================================================
# 3. Full evaluate() integration
# ===========================================================================

class TestFullEvaluate:
    evaluator = HardGateEvaluator()

    def test_evaluate_returns_hardgateevaluation(self):
        result = self.evaluator.evaluate(
            must_haves={"exp": {"type": "years_experience", "minimum_years": 5}},
            resume_parsed={"total_experience_years": 7},
        )
        assert isinstance(result, HardGateEvaluation)

    def test_evaluate_produces_one_result_per_criterion(self):
        result = self.evaluator.evaluate(
            must_haves={
                "exp": {"type": "years_experience", "minimum_years": 5},
                "python": {"type": "keyword_presence", "keywords": ["Python"], "sections": ["skills"]},
            },
            resume_parsed={"total_experience_years": 7, "skills": "Python"},
        )
        assert len(result.criterion_results) == 2

    def test_evaluate_empty_must_haves_yields_unknown(self):
        result = self.evaluator.evaluate(must_haves={}, resume_parsed={})
        assert result.outcome == GateOutcome.UNKNOWN

    def test_evaluate_full_pass(self):
        result = self.evaluator.evaluate(
            must_haves={
                "exp": {"type": "years_experience", "minimum_years": 5},
                "python": {"type": "keyword_presence", "keywords": ["Python"], "sections": ["skills"]},
                "aws": {"type": "certification", "required": ["AWS Solutions Architect"]},
            },
            resume_parsed={
                "total_experience_years": 8,
                "skills": "Python Django",
                "certifications": ["AWS Solutions Architect"],
            },
        )
        assert result.outcome == GateOutcome.PASS

    def test_evaluate_full_fail(self):
        result = self.evaluator.evaluate(
            must_haves={"exp": {"type": "years_experience", "minimum_years": 5}},
            resume_parsed={"total_experience_years": 2},
        )
        assert result.outcome == GateOutcome.FAIL


# ===========================================================================
# 4. FinalScoreCalculator
# ===========================================================================

class TestFinalScoreCalculator:
    calculator = FinalScoreCalculator()

    def test_gate_fail_returns_zero(self):
        score = self.calculator.calculate(
            gate_outcome=GateOutcome.FAIL,
            semantic_match=0.90,
            rubric_score_norm=0.85,
            evidence_quality=0.80,
        )
        assert score == 0.0

    def test_gate_fail_is_always_zero_regardless_of_other_scores(self):
        score = self.calculator.calculate(
            gate_outcome=GateOutcome.FAIL,
            semantic_match=1.0,
            rubric_score_norm=1.0,
            evidence_quality=1.0,
        )
        assert score == 0.0

    def test_gate_pass_uses_weighted_formula(self):
        # 0.45*1.0 + 0.45*1.0 + 0.10*1.0 = 1.0
        score = self.calculator.calculate(
            gate_outcome=GateOutcome.PASS,
            semantic_match=1.0,
            rubric_score_norm=1.0,
            evidence_quality=1.0,
        )
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_gate_unknown_uses_weighted_formula(self):
        """UNKNOWN does not short-circuit — pipeline continues with reduced confidence."""
        # 0.45*0.5 + 0.45*0.5 + 0.10*0.5 = 0.5
        score = self.calculator.calculate(
            gate_outcome=GateOutcome.UNKNOWN,
            semantic_match=0.5,
            rubric_score_norm=0.5,
            evidence_quality=0.5,
        )
        assert score == pytest.approx(0.5, abs=1e-9)

    def test_weighted_formula_is_correct(self):
        """
        Explicit formula verification with non-trivial inputs.
        Expected: 0.45*0.8 + 0.45*0.6 + 0.10*0.4 = 0.36 + 0.27 + 0.04 = 0.670
        """
        score = self.calculator.calculate(
            gate_outcome=GateOutcome.PASS,
            semantic_match=0.8,
            rubric_score_norm=0.6,
            evidence_quality=0.4,
        )
        assert score == pytest.approx(0.670, abs=1e-9)

    def test_zero_inputs_yield_zero_score_on_pass(self):
        score = self.calculator.calculate(
            gate_outcome=GateOutcome.PASS,
            semantic_match=0.0,
            rubric_score_norm=0.0,
            evidence_quality=0.0,
        )
        assert score == pytest.approx(0.0, abs=1e-9)


# ===========================================================================
# 5. FinalScoreWeights invariant
# ===========================================================================

class TestFinalScoreWeights:

    def test_default_weights_sum_to_one(self):
        w = FinalScoreWeights()
        total = w.semantic_match + w.rubric_score_norm + w.evidence_quality
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_correct_weight_values(self):
        w = FinalScoreWeights()
        assert w.semantic_match == pytest.approx(0.45)
        assert w.rubric_score_norm == pytest.approx(0.45)
        assert w.evidence_quality == pytest.approx(0.10)

    def test_invalid_weights_raise_on_construction(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            FinalScoreWeights(semantic_match=0.5, rubric_score_norm=0.5, evidence_quality=0.5)

    def test_weights_are_immutable(self):
        w = FinalScoreWeights()
        with pytest.raises((AttributeError, TypeError)):
            w.semantic_match = 0.99  # type: ignore[misc]
