"""
Inner-loop unit tests for embedding utilities and the EmbeddingClient adapter.

All tests run without a real embedding API.
The EmbeddingClient accepts an injected backend for testability — tests use a
MockEmbeddingBackend that returns deterministic vectors.

Test surface:
  1. cosine_similarity — pure math, no mocking needed
  2. section_weighted_similarity — weighted average over a dict of scores
  3. EmbeddingClient.embed() — delegates to backend, returns correct shape
  4. EmbeddingClient.embed_batch() — batch path
  5. SemanticMatchEvaluator.compute_section_scores() — per-section cosine pass
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

from resume_pipeline.embeddings import EmbeddingClient, MockEmbeddingBackend
from resume_pipeline.search.rrf import cosine_similarity, section_weighted_similarity
from resume_pipeline.pipeline.semantic_match import (
    SemanticMatchEvaluator,
    SECTION_WEIGHTS,
)


# ===========================================================================
# 1. cosine_similarity — pure math
# ===========================================================================

class TestCosineSimilarity:

    def test_identical_vectors_score_1(self):
        v = [1.0, 0.0, 0.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-9)

    def test_orthogonal_vectors_score_0(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-9)

    def test_anti_parallel_vectors_score_minus_1(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0, abs=1e-9)

    def test_zero_vector_a_returns_0(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 0.0

    def test_zero_vector_b_returns_0(self):
        a = [1.0, 2.0, 3.0]
        b = [0.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == 0.0

    def test_known_45_degree_angle(self):
        """45° angle between [1,0] and [1,1] → cos(45°) ≈ 0.7071."""
        a = [1.0, 0.0]
        b = [1.0, 1.0]
        expected = 1.0 / math.sqrt(2)
        assert cosine_similarity(a, b) == pytest.approx(expected, abs=1e-6)

    def test_scaling_does_not_affect_similarity(self):
        """Cosine similarity is scale-invariant."""
        a = [1.0, 0.0]
        b = [10.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(1.0, abs=1e-9)

    def test_high_dimensional_vector(self):
        dim = 1536
        a = [1.0 / math.sqrt(dim)] * dim
        b = [1.0 / math.sqrt(dim)] * dim
        assert cosine_similarity(a, b) == pytest.approx(1.0, abs=1e-6)

    def test_result_is_always_in_minus1_to_1(self):
        import random
        rng = random.Random(42)
        for _ in range(20):
            a = [rng.gauss(0, 1) for _ in range(10)]
            b = [rng.gauss(0, 1) for _ in range(10)]
            sim = cosine_similarity(a, b)
            assert -1.0 - 1e-9 <= sim <= 1.0 + 1e-9


# ===========================================================================
# 2. section_weighted_similarity
# ===========================================================================

class TestSectionWeightedSimilarity:

    def test_equal_similarities_returns_any_of_them(self):
        scores = {"experience": 0.8, "skills": 0.8}
        weights = {"experience": 0.6, "skills": 0.4}
        result = section_weighted_similarity(scores, weights)
        assert result == pytest.approx(0.8, abs=1e-9)

    def test_zero_similarity_sections_return_zero(self):
        scores = {"experience": 0.0, "skills": 0.0}
        weights = {"experience": 0.5, "skills": 0.5}
        assert section_weighted_similarity(scores, weights) == pytest.approx(0.0)

    def test_perfect_similarity_returns_1(self):
        scores = {"experience": 1.0, "skills": 1.0}
        weights = {"experience": 0.7, "skills": 0.3}
        assert section_weighted_similarity(scores, weights) == pytest.approx(1.0)

    def test_weights_sum_does_not_need_to_be_1(self):
        """Weights are normalized by the sum of present-section weights."""
        scores = {"experience": 1.0}
        weights = {"experience": 0.40, "skills": 0.30}
        # Only experience present → full weight goes to experience → score = 1.0
        result = section_weighted_similarity(scores, weights)
        assert result == pytest.approx(1.0, abs=1e-9)

    def test_missing_section_is_excluded_from_average(self):
        """Absent candidate sections don't drag the score down — they're excluded."""
        scores = {"skills": 1.0}         # experience missing
        weights = {"experience": 0.40, "skills": 0.30}
        result = section_weighted_similarity(scores, weights)
        # Only skills contributes → 1.0
        assert result == pytest.approx(1.0, abs=1e-9)

    def test_empty_section_scores_returns_zero(self):
        weights = {"experience": 0.40, "skills": 0.30}
        result = section_weighted_similarity({}, weights)
        assert result == 0.0

    def test_high_weight_section_dominates(self):
        """Experience (0.40) > skills (0.30): experience score should dominate."""
        scores = {"experience": 1.0, "skills": 0.0}
        result = section_weighted_similarity(scores, SECTION_WEIGHTS)
        assert result > 0.5

    def test_explicit_weighted_average_correctness(self):
        """
        experience: sim=0.9, weight=0.40
        skills:     sim=0.5, weight=0.30
        ─────────────────────────────────
        weighted = (0.9*0.40 + 0.5*0.30) / (0.40 + 0.30)
                 = (0.36 + 0.15) / 0.70
                 = 0.51 / 0.70
                 ≈ 0.7286
        """
        scores = {"experience": 0.9, "skills": 0.5}
        weights = {"experience": 0.40, "skills": 0.30}
        expected = (0.9 * 0.40 + 0.5 * 0.30) / (0.40 + 0.30)
        result = section_weighted_similarity(scores, weights)
        assert result == pytest.approx(expected, abs=1e-9)


# ===========================================================================
# 3. EmbeddingClient — adapter interface
# ===========================================================================

class TestEmbeddingClient:

    def test_embed_returns_list_of_floats(self):
        backend = MockEmbeddingBackend(dim=4)
        client = EmbeddingClient(backend=backend)
        vector = client.embed("some text")
        assert isinstance(vector, list)
        assert all(isinstance(x, float) for x in vector)

    def test_embed_returns_correct_dimension(self):
        backend = MockEmbeddingBackend(dim=1536)
        client = EmbeddingClient(backend=backend)
        vector = client.embed("hello world")
        assert len(vector) == 1536

    def test_embed_batch_returns_one_vector_per_text(self):
        backend = MockEmbeddingBackend(dim=8)
        client = EmbeddingClient(backend=backend)
        texts = ["text one", "text two", "text three"]
        vectors = client.embed_batch(texts)
        assert len(vectors) == len(texts)

    def test_embed_batch_all_vectors_same_dimension(self):
        backend = MockEmbeddingBackend(dim=16)
        client = EmbeddingClient(backend=backend)
        vectors = client.embed_batch(["a", "b", "c"])
        assert all(len(v) == 16 for v in vectors)

    def test_identical_texts_produce_identical_vectors(self):
        """MockEmbeddingBackend is deterministic — same text → same vector."""
        backend = MockEmbeddingBackend(dim=8)
        client = EmbeddingClient(backend=backend)
        v1 = client.embed("machine learning engineer")
        v2 = client.embed("machine learning engineer")
        assert v1 == v2

    def test_embed_empty_string_does_not_raise(self):
        backend = MockEmbeddingBackend(dim=4)
        client = EmbeddingClient(backend=backend)
        vector = client.embed("")
        assert len(vector) == 4

    def test_embed_calls_backend_once(self):
        mock_backend = MagicMock()
        mock_backend.embed.return_value = [0.1, 0.2, 0.3]
        client = EmbeddingClient(backend=mock_backend)
        client.embed("test")
        mock_backend.embed.assert_called_once_with("test")

    def test_embed_batch_calls_backend_batch_method(self):
        mock_backend = MagicMock()
        mock_backend.embed_batch.return_value = [[0.1], [0.2]]
        client = EmbeddingClient(backend=mock_backend)
        client.embed_batch(["a", "b"])
        mock_backend.embed_batch.assert_called_once_with(["a", "b"])


# ===========================================================================
# 4. SemanticMatchEvaluator — section score computation
# ===========================================================================

class TestSemanticMatchEvaluatorSectionScores:
    evaluator = SemanticMatchEvaluator()

    def test_compute_section_scores_returns_dict_per_section(self):
        candidate_embeddings = {
            "experience": [1.0, 0.0],
            "skills": [1.0, 0.0],
        }
        job_embeddings = {
            "experience": [1.0, 0.0],
            "skills": [0.0, 1.0],
        }
        scores = self.evaluator.compute_section_scores(
            candidate_embeddings, job_embeddings
        )
        assert "experience" in scores
        assert "skills" in scores

    def test_matching_section_scores_1(self):
        emb = {"experience": [1.0, 0.0]}
        scores = self.evaluator.compute_section_scores(emb, emb)
        assert scores["experience"] == pytest.approx(1.0, abs=1e-9)

    def test_orthogonal_section_scores_0(self):
        candidate = {"experience": [1.0, 0.0]}
        job = {"experience": [0.0, 1.0]}
        scores = self.evaluator.compute_section_scores(candidate, job)
        assert scores["experience"] == pytest.approx(0.0, abs=1e-9)

    def test_candidate_section_not_in_job_is_excluded(self):
        candidate = {"experience": [1.0, 0.0], "projects": [0.5, 0.5]}
        job = {"experience": [1.0, 0.0]}  # no "projects"
        scores = self.evaluator.compute_section_scores(candidate, job)
        assert "projects" not in scores
        assert "experience" in scores

    def test_job_section_not_in_candidate_is_excluded(self):
        candidate = {"skills": [1.0, 0.0]}
        job = {"skills": [1.0, 0.0], "experience": [0.5, 0.5]}
        scores = self.evaluator.compute_section_scores(candidate, job)
        assert "experience" not in scores

    def test_empty_candidate_embeddings_return_empty_scores(self):
        scores = self.evaluator.compute_section_scores(
            candidate_embeddings={},
            job_embeddings={"experience": [1.0, 0.0]},
        )
        assert scores == {}


# ===========================================================================
# 5. SECTION_WEIGHTS invariant
# ===========================================================================

class TestSectionWeightsConstant:

    def test_section_weights_sum_to_1(self):
        total = sum(SECTION_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_experience_has_highest_weight(self):
        max_section = max(SECTION_WEIGHTS, key=SECTION_WEIGHTS.get)
        assert max_section == "experience"

    def test_skills_has_second_highest_weight(self):
        sorted_sections = sorted(SECTION_WEIGHTS, key=SECTION_WEIGHTS.get, reverse=True)
        assert sorted_sections[1] == "skills"

    def test_all_weights_are_positive(self):
        assert all(w > 0 for w in SECTION_WEIGHTS.values())
