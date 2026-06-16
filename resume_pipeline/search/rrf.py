"""
Reciprocal Rank Fusion (RRF) — pure math module.

All functions are stateless and DB-free. This module is the single source of
truth for RRF math in the pipeline. No Django imports allowed here.

Reference: Cormack, G.V., Clarke, C.L.A., & Buettcher, S. (2009).
           Reciprocal rank fusion outperforms condorcet and individual ranked
           retrieval results. SIGIR '09.

Formula:
    raw_rrf(d) = Σ_i  1 / (k + rank_i(d))

    Normalization to [0, 1]:
        max_raw = num_sources * (1 / (k + 1))   ← all channels, rank = 1
        norm_rrf = min(raw_rrf / max_raw, 1.0)
"""

from __future__ import annotations

import math
import time
from typing import Optional

from resume_pipeline.logging_module import audit_logger
from resume_pipeline.observability import pipeline_observability


# ---------------------------------------------------------------------------
# Core RRF math
# ---------------------------------------------------------------------------

def compute_rrf_score(
    lexical_rank: Optional[int],
    semantic_rank: Optional[int],
    k: int = 60,
) -> float:
    """
    Compute the raw (unnormalized) RRF score for a candidate.

    Args:
        lexical_rank: 1-based rank from PostgreSQL full-text search.
                      None if the candidate did not appear in lexical results.
        semantic_rank: 1-based rank from pgvector cosine search.
                       None if the candidate did not appear in semantic results.
        k: RRF smoothing constant (standard: 60).

    Returns:
        Raw RRF score ≥ 0. Call normalize_rrf_score() to map to [0, 1].
    """
    score = 0.0
    if lexical_rank is not None:
        score += 1.0 / (k + lexical_rank)
    if semantic_rank is not None:
        score += 1.0 / (k + semantic_rank)
    return score


def max_rrf_score(k: int = 60, num_sources: int = 2) -> float:
    """
    Maximum possible raw RRF score (all channels contribute, rank = 1).

    Args:
        k: RRF smoothing constant.
        num_sources: Number of retrieval channels (2 = lexical + semantic).

    Returns:
        Upper bound on compute_rrf_score() output.
    """
    if num_sources == 0:
        return 0.0
    return num_sources * (1.0 / (k + 1))


def normalize_rrf_score(
    rrf_score: float,
    k: int = 60,
    num_sources: int = 2,
) -> float:
    """
    Normalize a raw RRF score to [0, 1].

    Args:
        rrf_score: Raw score from compute_rrf_score().
        k: Must match the k used in compute_rrf_score().
        num_sources: Number of active retrieval channels.

    Returns:
        Normalized score in [0.0, 1.0].
    """
    max_score = max_rrf_score(k=k, num_sources=num_sources)
    if max_score == 0.0:
        return 0.0
    return min(rrf_score / max_score, 1.0)


# ---------------------------------------------------------------------------
# Ranked list fusion
# ---------------------------------------------------------------------------

def fuse_ranked_lists(
    lexical_results: list[str],
    semantic_results: list[str],
    k: int = 60,
) -> list[tuple[str, float]]:
    """
    Fuse two ranked candidate lists using RRF.

    Candidates appearing in only one list receive a rank from that list
    and None from the other — they are not excluded.

    Args:
        lexical_results: Candidate IDs in lexical rank order (best first).
                         Duplicates are deduplicated, keeping first occurrence rank.
        semantic_results: Candidate IDs in semantic rank order (best first).
        k: RRF smoothing constant.

    Returns:
        List of (candidate_id, normalized_rrf_score) sorted by score descending.
    """
    t_start = time.perf_counter()

    with pipeline_observability.timed("rrf_fusion"):
        # Build rank maps (1-based, deduplicated — first occurrence wins).
        lexical_ranks: dict[str, int] = {}
        for i, candidate_id in enumerate(lexical_results, start=1):
            if candidate_id not in lexical_ranks:
                lexical_ranks[candidate_id] = i

        semantic_ranks: dict[str, int] = {}
        for i, candidate_id in enumerate(semantic_results, start=1):
            if candidate_id not in semantic_ranks:
                semantic_ranks[candidate_id] = i

        # Union of all candidate IDs across both lists.
        all_candidates = set(lexical_ranks) | set(semantic_ranks)

        num_sources = (1 if lexical_results else 0) + (1 if semantic_results else 0)

        fused: list[tuple[str, float]] = []
        for candidate_id in all_candidates:
            raw = compute_rrf_score(
                lexical_rank=lexical_ranks.get(candidate_id),
                semantic_rank=semantic_ranks.get(candidate_id),
                k=k,
            )
            norm = normalize_rrf_score(raw, k=k, num_sources=num_sources)
            fused.append((candidate_id, norm))

        # Sort by score descending; tie-break by candidate_id for determinism.
        fused.sort(key=lambda x: (-x[1], x[0]))

    latency_ms = (time.perf_counter() - t_start) * 1000
    top_score = fused[0][1] if fused else None

    audit_logger.log_rrf_fusion_done(
        lexical_count=len(lexical_results),
        semantic_count=len(semantic_results),
        union_count=len(fused),
        num_sources=num_sources,
        top_score=top_score,
        latency_ms=latency_ms,
    )

    return fused


# ---------------------------------------------------------------------------
# Cosine similarity and section scoring utilities
# (co-located here because they are shared by search and pipeline modules)
# ---------------------------------------------------------------------------

def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    Returns 0.0 when either vector is the zero vector (undefined cosine).
    Result is clamped to [-1.0, 1.0] to guard against floating-point drift.
    """
    if not vec_a or not vec_b:
        return 0.0

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    raw = dot / (norm_a * norm_b)
    # Clamp for floating-point safety.
    return max(-1.0, min(1.0, raw))


def section_weighted_similarity(
    section_scores: dict[str, float],
    weights: dict[str, float],
) -> float:
    """
    Compute a weighted average of per-section cosine similarities.

    Only sections present in both section_scores and weights contribute.
    The denominator is the sum of weights for present sections (not 1.0),
    so absent sections do not drag the score down.

    Args:
        section_scores: {section_name: cosine_similarity} for sections that
                        appear in both the candidate and the job.
        weights: {section_name: weight} — e.g. SECTION_WEIGHTS.

    Returns:
        Weighted average in [min_similarity, max_similarity].
        Returns 0.0 when no sections contribute.
    """
    total_weight = 0.0
    weighted_sum = 0.0

    for section, score in section_scores.items():
        w = weights.get(section, 0.0)
        if w > 0.0:
            weighted_sum += score * w
            total_weight += w

    if total_weight == 0.0:
        return 0.0

    return weighted_sum / total_weight
