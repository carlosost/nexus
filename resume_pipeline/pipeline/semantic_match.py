"""
Semantic Match Evaluator — Stage 2 of the resume evaluation pipeline.

Produces a [0, 1] semantic match score by combining:
  1. Section-weighted cosine similarity (candidate vs. job section embeddings).
  2. Reciprocal Rank Fusion score from the hybrid search phase.

The two signals are blended:
    semantic_score = EMBEDDING_WEIGHT * section_similarity
                   + RRF_WEIGHT       * rrf_score

When the pipeline has no RRF ranks (embeddings-only mode), RRF_WEIGHT
contribution falls to 0 and section_similarity carries full weight via
automatic weight redistribution.

Observability: the evaluator is instrumented at construction time.
Every call to evaluate() emits a LatencyRecord to pipeline_observability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from resume_pipeline.observability import pipeline_observability
from resume_pipeline.search.rrf import (
    compute_rrf_score,
    cosine_similarity,
    normalize_rrf_score,
    section_weighted_similarity,
)


# ---------------------------------------------------------------------------
# Section weights
# ---------------------------------------------------------------------------

#: Weights for each resume section when computing section-level similarity.
#: Must sum to 1.0 — validated by the unit test in test_embedding.py.
SECTION_WEIGHTS: dict[str, float] = {
    "experience": 0.40,
    "skills": 0.30,
    "summary": 0.15,
    "education": 0.05,
    "certifications": 0.05,
    "projects": 0.05,
}

_WEIGHTS_SUM = sum(SECTION_WEIGHTS.values())
assert abs(_WEIGHTS_SUM - 1.0) < 1e-9, (
    f"SECTION_WEIGHTS must sum to 1.0; got {_WEIGHTS_SUM}"
)


# ---------------------------------------------------------------------------
# Blend weights — how much each signal contributes to the final score
# ---------------------------------------------------------------------------

#: Weight given to the section-weighted embedding similarity.
EMBEDDING_BLEND_WEIGHT: float = 0.60

#: Weight given to the normalized RRF rank fusion score.
RRF_BLEND_WEIGHT: float = 0.40

assert abs(EMBEDDING_BLEND_WEIGHT + RRF_BLEND_WEIGHT - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Result data class
# ---------------------------------------------------------------------------

@dataclass
class SemanticMatchScore:
    """
    All signals produced by Stage 2, available for Stage 4 and human review.
    """
    # Per-section cosine similarities {section: similarity}.
    section_scores: dict[str, float] = field(default_factory=dict)

    # Section-weighted similarity ∈ [0, 1] (or [-1, 1] if embeddings are poor).
    section_weighted_similarity: float = 0.0

    # Normalized RRF score ∈ [0, 1]. 0.0 when no ranks are available.
    rrf_score: float = 0.0

    # Lexical and semantic ranks from the search phase (nullable).
    lexical_rank: Optional[int] = None
    semantic_rank: Optional[int] = None

    # Final blended score fed into Stage 4.
    final_score: float = 0.0


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class SemanticMatchEvaluator:
    """
    Computes the semantic match score for a single candidate–job pair.

    Usage::

        evaluator = SemanticMatchEvaluator()
        result = evaluator.evaluate(
            candidate_embeddings={"experience": [...], "skills": [...]},
            job_embeddings={"experience": [...], "skills": [...]},
            lexical_rank=3,
            semantic_rank=1,
        )
        # result.final_score → float in [0, 1]
    """

    def __init__(
        self,
        section_weights: dict[str, float] = SECTION_WEIGHTS,
        embedding_blend: float = EMBEDDING_BLEND_WEIGHT,
        rrf_blend: float = RRF_BLEND_WEIGHT,
        rrf_k: int = 60,
        rrf_num_sources: int = 2,
    ) -> None:
        self._section_weights = section_weights
        self._embedding_blend = embedding_blend
        self._rrf_blend = rrf_blend
        self._rrf_k = rrf_k
        self._rrf_num_sources = rrf_num_sources

        # Instrument the public evaluate() at construction time so subclasses
        # and test instances are also wrapped automatically.
        self.evaluate = pipeline_observability.instrument("semantic_match")(
            self._evaluate_impl
        )

    # ------------------------------------------------------------------
    # Public API — evaluate() is replaced by the instrumented wrapper above.
    # ------------------------------------------------------------------

    def _evaluate_impl(
        self,
        candidate_embeddings: dict[str, list[float]],
        job_embeddings: dict[str, list[float]],
        lexical_rank: Optional[int] = None,
        semantic_rank: Optional[int] = None,
    ) -> SemanticMatchScore:
        """
        Args:
            candidate_embeddings: {section_name: vector} for the candidate.
            job_embeddings: {section_name: vector} for the job description.
            lexical_rank: Candidate's 1-based rank in full-text search results.
                          None if candidate was not retrieved lexically.
            semantic_rank: Candidate's 1-based rank in pgvector cosine results.
                           None if candidate was not retrieved semantically.

        Returns:
            SemanticMatchScore with all intermediate signals and a final_score.
        """
        # Stage 2a: per-section cosine similarities.
        section_scores = self.compute_section_scores(
            candidate_embeddings, job_embeddings
        )

        # Stage 2b: section-weighted aggregate similarity.
        sim = section_weighted_similarity(section_scores, self._section_weights)

        # Stage 2c: RRF rank fusion.
        raw_rrf = compute_rrf_score(
            lexical_rank=lexical_rank,
            semantic_rank=semantic_rank,
            k=self._rrf_k,
        )
        norm_rrf = normalize_rrf_score(
            raw_rrf,
            k=self._rrf_k,
            num_sources=self._active_sources(lexical_rank, semantic_rank),
        )

        # Stage 2d: blend the two signals.
        # If no ranks are available, collapse RRF contribution to zero and
        # normalize the remaining weight to embedding similarity.
        if lexical_rank is None and semantic_rank is None:
            final = sim  # 100% embedding signal
        else:
            final = self._embedding_blend * sim + self._rrf_blend * norm_rrf

        # Clamp to [0, 1] — cosine can be negative for adversarial embeddings.
        final = max(0.0, min(1.0, final))

        return SemanticMatchScore(
            section_scores=section_scores,
            section_weighted_similarity=sim,
            rrf_score=norm_rrf,
            lexical_rank=lexical_rank,
            semantic_rank=semantic_rank,
            final_score=final,
        )

    def compute_section_scores(
        self,
        candidate_embeddings: dict[str, list[float]],
        job_embeddings: dict[str, list[float]],
    ) -> dict[str, float]:
        """
        Compute cosine similarity for each section present in both dicts.

        Sections in candidate but not in job (or vice-versa) are excluded.
        """
        scores: dict[str, float] = {}
        for section, candidate_vec in candidate_embeddings.items():
            job_vec = job_embeddings.get(section)
            if job_vec is not None:
                scores[section] = cosine_similarity(candidate_vec, job_vec)
        return scores

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _active_sources(
        lexical_rank: Optional[int],
        semantic_rank: Optional[int],
    ) -> int:
        return (1 if lexical_rank is not None else 0) + (
            1 if semantic_rank is not None else 0
        )
