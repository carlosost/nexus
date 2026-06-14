"""
Rubric Evaluator Protocol + Stub — Stage 3 interface definition.

The orchestrator depends on this protocol, not on a concrete implementation.
This allows M4 (orchestration) to be fully implemented and tested before
M3 (LLM rubric scoring) is built. The StubRubricEvaluator is a drop-in
placeholder that returns deterministic scores.

In M3, replace StubRubricEvaluator with LLMRubricEvaluator(model="gpt-4o").
The orchestrator requires no changes.

Rubric weights (reference — normalization is the evaluator's responsibility):
    core_skills          0.30
    relevant_experience  0.30
    scope_impact         0.20
    domain_alignment     0.10
    education_certs      0.10
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Result data class
# ---------------------------------------------------------------------------

@dataclass
class RubricResult:
    """
    Output from any rubric evaluator.

    Attributes:
        normalized_score: Weighted average of raw competency scores,
                          normalized to [0, 1].
        evidence_quality: Heuristic measure of how well the resume's text
                          supports the assigned scores. In [0, 1].
        criterion_scores: Raw per-competency scores on a [1, 5] scale.
                          May be empty for stub implementations.
        is_evaluated_via_fallback: True when a primary LLM provider failure
                          caused the result to be produced by a secondary
                          (fallback) provider. Surfaced to the DB and API
                          so reviewers can see a visual alert.
    """
    normalized_score: float
    evidence_quality: float
    criterion_scores: dict[str, float] = field(default_factory=dict)
    is_evaluated_via_fallback: bool = False


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class RubricEvaluatorProtocol(Protocol):
    """
    Interface that any rubric evaluator must satisfy.

    The orchestrator accepts any object implementing this protocol via
    structural subtyping — no explicit inheritance needed.
    """

    def evaluate(
        self,
        resume_parsed: dict,
        job_requirements: dict,
    ) -> RubricResult:
        """
        Evaluate a candidate's resume against role-specific rubric criteria.

        Args:
            resume_parsed: Structured resume data (same shape as
                           Candidate.resume_parsed in models.py).
            job_requirements: Job requirements blob (Job.requirements_raw).

        Returns:
            RubricResult with normalized score, evidence quality, and
            per-criterion raw scores.
        """
        ...


# ---------------------------------------------------------------------------
# Stub — placeholder until M3 is implemented
# ---------------------------------------------------------------------------

class StubRubricEvaluator:
    """
    Returns fixed mid-range scores.

    Use during development and integration tests when a real LLM rubric
    evaluator is not yet available.

    Scores are deliberately not perfect (1.0) to avoid masking bugs where
    the formula would produce correct results by coincidence.
    """

    # Swap these constants in tests that need predictable formula verification.
    DEFAULT_NORMALIZED_SCORE: float = 0.70
    DEFAULT_EVIDENCE_QUALITY: float = 0.65

    def evaluate(
        self,
        resume_parsed: dict,
        job_requirements: dict,
    ) -> RubricResult:
        return RubricResult(
            normalized_score=self.DEFAULT_NORMALIZED_SCORE,
            evidence_quality=self.DEFAULT_EVIDENCE_QUALITY,
            criterion_scores={
                "core_skills": 3.5,
                "relevant_experience": 3.5,
                "scope_impact": 3.5,
                "domain_alignment": 3.5,
                "education_certs": 3.5,
            },
        )
