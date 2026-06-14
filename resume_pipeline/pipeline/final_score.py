"""
Final Score Calculator — Stage 4 of the resume evaluation pipeline.

Formula:
    FinalScore = 0.0                                          if gate_outcome == FAIL
    FinalScore = (0.45 * semantic_match)
               + (0.45 * rubric_score_norm)
               + (0.10 * evidence_quality)                    otherwise

All inputs must be in [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass

from resume_pipeline.pipeline.hard_gate import GateOutcome


# ---------------------------------------------------------------------------
# Weights — declare as a named dataclass so they can be tested independently
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FinalScoreWeights:
    semantic_match: float = 0.45
    rubric_score_norm: float = 0.45
    evidence_quality: float = 0.10

    def __post_init__(self) -> None:
        total = self.semantic_match + self.rubric_score_norm + self.evidence_quality
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"FinalScoreWeights must sum to 1.0; got {total:.10f}"
            )


DEFAULT_WEIGHTS = FinalScoreWeights()


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

class FinalScoreCalculator:
    """
    Computes the final composite score for a pipeline run.

    Usage::

        calculator = FinalScoreCalculator()
        score = calculator.calculate(
            gate_outcome=GateOutcome.PASS,
            semantic_match=0.82,
            rubric_score_norm=0.74,
            evidence_quality=0.65,
        )
        # → 0.45*0.82 + 0.45*0.74 + 0.10*0.65 = 0.790
    """

    def __init__(self, weights: FinalScoreWeights = DEFAULT_WEIGHTS) -> None:
        self._weights = weights

    def calculate(
        self,
        gate_outcome: GateOutcome,
        semantic_match: float,
        rubric_score_norm: float,
        evidence_quality: float,
    ) -> float:
        """
        Args:
            gate_outcome: Outcome from Stage 1. FAIL short-circuits to 0.0.
            semantic_match: RRF-combined score from Stage 2 in [0, 1].
            rubric_score_norm: Normalized weighted rubric score from Stage 3 in [0, 1].
            evidence_quality: Heuristic evidence quality in [0, 1].

        Returns:
            Final composite score in [0, 1].
        """
        if gate_outcome == GateOutcome.FAIL:
            return 0.0

        return (
            self._weights.semantic_match * semantic_match
            + self._weights.rubric_score_norm * rubric_score_norm
            + self._weights.evidence_quality * evidence_quality
        )
