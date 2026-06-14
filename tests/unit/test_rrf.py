"""
Inner-loop unit tests for Reciprocal Rank Fusion (RRF) math.

All tests are pure functions — no DB, no Django, no network.
Write these BEFORE implementing resume_pipeline/search/rrf.py.

Mathematical reference:
    RRF(d) = Σ_i  1 / (k + rank_i(d))

    where k=60 is the standard constant (Cormack et al., 2009).

    For our 2-channel pipeline (lexical + semantic):
        raw_rrf  = 1/(k + lexical_rank) + 1/(k + semantic_rank)
        max_raw  = 2 * 1/(k + 1)         ← both channels, rank = 1
        norm_rrf = raw_rrf / max_raw      → [0, 1]

    When a channel is absent (no rank), its term is omitted and
    max_raw is adjusted proportionally (1-channel max = 1/(k+1)).
"""

from __future__ import annotations

import math
import pytest

from resume_pipeline.search.rrf import (
    compute_rrf_score,
    max_rrf_score,
    normalize_rrf_score,
    fuse_ranked_lists,
)


# ===========================================================================
# 1. compute_rrf_score — raw (unnormalized) score
# ===========================================================================

class TestComputeRrfScore:
    K = 60

    def test_both_channels_rank_1(self):
        raw = compute_rrf_score(lexical_rank=1, semantic_rank=1, k=self.K)
        expected = 1 / (self.K + 1) + 1 / (self.K + 1)
        assert raw == pytest.approx(expected, rel=1e-9)

    def test_both_channels_rank_10(self):
        raw = compute_rrf_score(lexical_rank=10, semantic_rank=10, k=self.K)
        expected = 1 / (self.K + 10) + 1 / (self.K + 10)
        assert raw == pytest.approx(expected, rel=1e-9)

    def test_only_lexical_rank(self):
        raw = compute_rrf_score(lexical_rank=1, semantic_rank=None, k=self.K)
        expected = 1 / (self.K + 1)
        assert raw == pytest.approx(expected, rel=1e-9)

    def test_only_semantic_rank(self):
        raw = compute_rrf_score(lexical_rank=None, semantic_rank=1, k=self.K)
        expected = 1 / (self.K + 1)
        assert raw == pytest.approx(expected, rel=1e-9)

    def test_no_ranks_is_zero(self):
        raw = compute_rrf_score(lexical_rank=None, semantic_rank=None, k=self.K)
        assert raw == 0.0

    def test_score_decreases_as_rank_increases(self):
        raw_1 = compute_rrf_score(lexical_rank=1, semantic_rank=1, k=self.K)
        raw_10 = compute_rrf_score(lexical_rank=10, semantic_rank=10, k=self.K)
        raw_100 = compute_rrf_score(lexical_rank=100, semantic_rank=100, k=self.K)
        assert raw_1 > raw_10 > raw_100

    def test_asymmetric_ranks(self):
        """Rank 1 in lexical + rank 5 in semantic should fall between two equal-rank cases."""
        raw_1_1 = compute_rrf_score(lexical_rank=1, semantic_rank=1, k=self.K)
        raw_1_5 = compute_rrf_score(lexical_rank=1, semantic_rank=5, k=self.K)
        raw_5_5 = compute_rrf_score(lexical_rank=5, semantic_rank=5, k=self.K)
        assert raw_1_1 > raw_1_5 > raw_5_5

    def test_k_parameter_affects_score(self):
        """Larger k reduces score differences between ranks (flattens the curve)."""
        raw_k60 = compute_rrf_score(lexical_rank=1, semantic_rank=1, k=60)
        raw_k10 = compute_rrf_score(lexical_rank=1, semantic_rank=1, k=10)
        # With k=10, rank 1 has proportionally more weight → higher raw score.
        assert raw_k10 > raw_k60

    def test_score_is_always_non_negative(self):
        assert compute_rrf_score(1, 1) >= 0.0
        assert compute_rrf_score(None, None) >= 0.0
        assert compute_rrf_score(1000, 1000) >= 0.0


# ===========================================================================
# 2. max_rrf_score — upper bound for normalization
# ===========================================================================

class TestMaxRrfScore:

    def test_two_sources_at_default_k(self):
        expected = 2 * (1 / (60 + 1))
        assert max_rrf_score(k=60, num_sources=2) == pytest.approx(expected, rel=1e-9)

    def test_one_source(self):
        expected = 1 / (60 + 1)
        assert max_rrf_score(k=60, num_sources=1) == pytest.approx(expected, rel=1e-9)

    def test_zero_sources_is_zero(self):
        assert max_rrf_score(k=60, num_sources=0) == 0.0


# ===========================================================================
# 3. normalize_rrf_score — maps raw score to [0, 1]
# ===========================================================================

class TestNormalizeRrfScore:
    K = 60

    def test_rank_1_both_channels_normalizes_to_1(self):
        raw = compute_rrf_score(lexical_rank=1, semantic_rank=1, k=self.K)
        norm = normalize_rrf_score(raw, k=self.K, num_sources=2)
        assert norm == pytest.approx(1.0, rel=1e-9)

    def test_zero_raw_normalizes_to_zero(self):
        norm = normalize_rrf_score(0.0, k=self.K, num_sources=2)
        assert norm == 0.0

    def test_normalized_score_is_in_0_1(self):
        for rank in [1, 5, 10, 50, 100, 500]:
            raw = compute_rrf_score(lexical_rank=rank, semantic_rank=rank, k=self.K)
            norm = normalize_rrf_score(raw, k=self.K, num_sources=2)
            assert 0.0 <= norm <= 1.0, f"Out of range for rank={rank}: {norm}"

    def test_single_channel_rank_1_normalizes_below_1(self):
        """One channel at rank 1 can never reach 1.0 (max requires both channels)."""
        raw = compute_rrf_score(lexical_rank=1, semantic_rank=None, k=self.K)
        # Normalize against 2-source max — should be 0.5.
        norm = normalize_rrf_score(raw, k=self.K, num_sources=2)
        assert norm == pytest.approx(0.5, rel=1e-9)

    def test_normalized_score_is_monotonically_decreasing_with_rank(self):
        norms = []
        for rank in [1, 5, 10, 50, 100]:
            raw = compute_rrf_score(rank, rank, self.K)
            norms.append(normalize_rrf_score(raw, self.K, 2))
        assert norms == sorted(norms, reverse=True)

    def test_normalization_never_exceeds_1_for_any_valid_input(self):
        """Robustness: raw score should never produce > 1.0 after normalization."""
        raw = compute_rrf_score(lexical_rank=1, semantic_rank=1, k=self.K)
        # Slightly inflate raw to simulate floating-point accumulation.
        inflated = raw * 1.000001
        norm = normalize_rrf_score(inflated, k=self.K, num_sources=2)
        assert norm <= 1.0


# ===========================================================================
# 4. fuse_ranked_lists — combines two ranked candidate lists into RRF scores
# ===========================================================================

class TestFuseRankedLists:
    """
    fuse_ranked_lists(
        lexical_results: list[str],   # candidate IDs in lexical rank order
        semantic_results: list[str],  # candidate IDs in semantic rank order
        k: int = 60,
    ) -> list[tuple[str, float]]     # [(candidate_id, normalized_rrf_score)] sorted desc
    """

    def test_candidate_top_in_both_lists_gets_highest_score(self):
        results = fuse_ranked_lists(
            lexical_results=["A", "B", "C"],
            semantic_results=["A", "C", "B"],
        )
        top_id = results[0][0]
        assert top_id == "A"

    def test_result_is_sorted_descending_by_score(self):
        results = fuse_ranked_lists(
            lexical_results=["A", "B", "C"],
            semantic_results=["A", "B", "C"],
        )
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)

    def test_candidates_only_in_one_list_still_appear_in_results(self):
        results = fuse_ranked_lists(
            lexical_results=["A", "B"],
            semantic_results=["A", "C"],  # C only in semantic
        )
        ids = [id_ for id_, _ in results]
        assert "B" in ids
        assert "C" in ids

    def test_empty_lexical_list_uses_only_semantic_ranks(self):
        results = fuse_ranked_lists(
            lexical_results=[],
            semantic_results=["A", "B", "C"],
        )
        assert len(results) == 3
        top_id = results[0][0]
        assert top_id == "A"

    def test_empty_both_lists_returns_empty(self):
        results = fuse_ranked_lists(lexical_results=[], semantic_results=[])
        assert results == []

    def test_all_scores_in_0_1_range(self):
        results = fuse_ranked_lists(
            lexical_results=["A", "B", "C", "D"],
            semantic_results=["B", "A", "D", "C"],
        )
        for _, score in results:
            assert 0.0 <= score <= 1.0

    def test_candidate_in_both_lists_at_rank_1_scores_1(self):
        results = fuse_ranked_lists(
            lexical_results=["A"],
            semantic_results=["A"],
        )
        assert len(results) == 1
        assert results[0][0] == "A"
        assert results[0][1] == pytest.approx(1.0, rel=1e-9)

    def test_deduplication_same_candidate_appears_once(self):
        results = fuse_ranked_lists(
            lexical_results=["A", "B", "A"],  # A appears twice (edge case guard)
            semantic_results=["A", "B"],
        )
        ids = [id_ for id_, _ in results]
        assert ids.count("A") == 1
