"""
Hybrid Search Engine — PostgreSQL full-text search + pgvector cosine similarity,
fused via Reciprocal Rank Fusion.

Architecture
────────────
                    ┌─────────────────────┐
                    │  HybridSearchEngine  │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
      _lexical_search  _semantic_search   fuse_ranked_lists
      (PostgreSQL FTS)  (pgvector cosine)     (rrf.py)
              │               │               ▲
              └───────────────┴───────────────┘
                     ranked candidate IDs

The engine operates at the retrieval layer — it returns ranked candidate IDs
and their normalized RRF scores. The SemanticMatchEvaluator then computes per-
section embedding scores for individual applications.

PostgreSQL queries
──────────────────
Lexical (FTS):
    SELECT candidate_id,
           ts_rank(to_tsvector('english', resume_raw), query) AS ts_rank
    FROM   resume_pipeline_candidate,
           plainto_tsquery('english', %(query_text)s) query
    WHERE  to_tsvector('english', resume_raw) @@ query
    ORDER  BY ts_rank DESC
    LIMIT  %(top_k)s;

Semantic (pgvector):
    SELECT se.candidate_id,
           1 - (se.embedding <=> %(query_vector)s::vector) AS cosine_sim
    FROM   resume_pipeline_sectionembedding se
    WHERE  se.section = %(section)s
    ORDER  BY se.embedding <=> %(query_vector)s::vector
    LIMIT  %(top_k)s;

Both return ordered lists of candidate_ids that are fed to fuse_ranked_lists().

NOTE: This module contains Django ORM / raw SQL calls. It cannot be unit-tested
without a live database. Integration tests for this class live in
tests/integration/test_hybrid_search.py (not yet written — Milestone 2 scope).

Unit-testable logic (RRF math, cosine similarity) lives in search/rrf.py.
"""

from __future__ import annotations

from typing import Optional

from resume_pipeline.search.rrf import fuse_ranked_lists


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class SearchResult:
    """Ranked candidate from the hybrid search."""

    __slots__ = ("candidate_id", "rrf_score", "lexical_rank", "semantic_rank")

    def __init__(
        self,
        candidate_id: str,
        rrf_score: float,
        lexical_rank: Optional[int] = None,
        semantic_rank: Optional[int] = None,
    ) -> None:
        self.candidate_id = candidate_id
        self.rrf_score = rrf_score
        self.lexical_rank = lexical_rank
        self.semantic_rank = semantic_rank

    def __repr__(self) -> str:
        return (
            f"SearchResult(candidate_id={self.candidate_id!r}, "
            f"rrf_score={self.rrf_score:.4f}, "
            f"lexical_rank={self.lexical_rank}, "
            f"semantic_rank={self.semantic_rank})"
        )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class HybridSearchEngine:
    """
    Retrieves and ranks candidates for a given job using hybrid search.

    Args:
        top_k: Number of candidates to retrieve from each channel before fusion.
               Higher values improve recall at the cost of query latency.
        rrf_k: RRF smoothing constant (standard: 60).
        primary_embedding_section: Resume section whose embedding is used as the
                                   semantic query vector (typically "experience"
                                   or a concatenated summary embedding).
    """

    def __init__(
        self,
        top_k: int = 100,
        rrf_k: int = 60,
        primary_embedding_section: str = "experience",
    ) -> None:
        self._top_k = top_k
        self._rrf_k = rrf_k
        self._primary_section = primary_embedding_section

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        job_id: str,
        query_text: str,
        query_embedding: list[float],
        connection=None,
    ) -> list[SearchResult]:
        """
        Execute hybrid search for a job and return ranked candidates.

        Args:
            job_id: UUID of the job (used to scope results to existing applications).
            query_text: Plain-text job description or requirements for FTS.
            query_embedding: Dense vector embedding of the job's primary section.
            connection: Django DB connection (injectable for testability).
                        Defaults to django.db.connection.

        Returns:
            List of SearchResult ordered by descending RRF score.
        """
        if connection is None:
            from django.db import connection as _conn
            connection = _conn

        lexical_ids = self._lexical_search(query_text, connection)
        semantic_ids = self._semantic_search(query_embedding, connection)

        fused = fuse_ranked_lists(
            lexical_results=lexical_ids,
            semantic_results=semantic_ids,
            k=self._rrf_k,
        )

        # Build rank lookup for populating SearchResult metadata.
        lexical_rank_map = {id_: rank for rank, id_ in enumerate(lexical_ids, 1)}
        semantic_rank_map = {id_: rank for rank, id_ in enumerate(semantic_ids, 1)}

        return [
            SearchResult(
                candidate_id=candidate_id,
                rrf_score=score,
                lexical_rank=lexical_rank_map.get(candidate_id),
                semantic_rank=semantic_rank_map.get(candidate_id),
            )
            for candidate_id, score in fused
        ]

    # ------------------------------------------------------------------
    # Private — database queries
    # ------------------------------------------------------------------

    def _lexical_search(
        self,
        query_text: str,
        connection,
    ) -> list[str]:
        """
        Full-text search over candidate resume_raw using PostgreSQL tsvector.

        Returns candidate IDs ordered by ts_rank descending.
        """
        sql = """
            SELECT  c.id::text
            FROM    resume_pipeline_candidate c,
                    plainto_tsquery('english', %(query_text)s) AS query
            WHERE   to_tsvector('english', c.resume_raw) @@ query
            ORDER   BY ts_rank(
                        to_tsvector('english', c.resume_raw),
                        query
                    ) DESC
            LIMIT   %(top_k)s;
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, {"query_text": query_text, "top_k": self._top_k})
            return [row[0] for row in cursor.fetchall()]

    def _semantic_search(
        self,
        query_embedding: list[float],
        connection,
    ) -> list[str]:
        """
        Vector similarity search over SectionEmbedding using pgvector (<=> operator).

        Returns candidate IDs ordered by cosine distance ascending (closest first).

        Requires: CREATE INDEX ON resume_pipeline_sectionembedding
                  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
        """
        # Format the embedding as a Postgres vector literal.
        vector_literal = "[" + ",".join(str(v) for v in query_embedding) + "]"

        sql = """
            SELECT  se.candidate_id::text
            FROM    resume_pipeline_sectionembedding se
            WHERE   se.section = %(section)s
            ORDER   BY se.embedding <=> %(vector)s::vector
            LIMIT   %(top_k)s;
        """
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                {
                    "section": self._primary_section,
                    "vector": vector_literal,
                    "top_k": self._top_k,
                },
            )
            return [row[0] for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Convenience — retrieve ranks for a specific candidate post-search
    # ------------------------------------------------------------------

    @staticmethod
    def get_candidate_ranks(
        candidate_id: str,
        search_results: list[SearchResult],
    ) -> tuple[Optional[int], Optional[int]]:
        """
        Extract (lexical_rank, semantic_rank) for a candidate from a prior search.

        Returns (None, None) if the candidate does not appear in results.
        """
        for result in search_results:
            if result.candidate_id == candidate_id:
                return result.lexical_rank, result.semantic_rank
        return None, None
