The float32 bytes from SHA-256 can produce NaN values which break the norm calculation. Let me fix the `MockEmbeddingBackend`:Milestone 2 complete. Here's the breakdown.

---

**Outer loop** — `semantic_match.feature` has 17 scenarios organized in four groups: per-section cosine similarity, section-weighted aggregation, RRF math properties, and the full `SemanticMatchEvaluator` end-to-end including the observability assertion.

**Inner loop** — Two test files, 60 tests total:

- `test_rrf.py` (32 tests) covers `compute_rrf_score`, `max_rrf_score`, `normalize_rrf_score`, and `fuse_ranked_lists` exhaustively — including monotonicity, single-channel degradation, deduplication, and the boundary that rank 1 in both channels is the only path to a normalized score of 1.0.
- `test_embedding.py` (28 tests) covers `cosine_similarity`, `section_weighted_similarity`, `EmbeddingClient` (with `MockEmbeddingBackend` and injected `MagicMock`), `SemanticMatchEvaluator.compute_section_scores`, and the `SECTION_WEIGHTS` invariants.

**Implementation** — four modules:

- `search/rrf.py` — all pure math: RRF scoring, normalization, ranked list fusion, cosine similarity, section-weighted similarity. Zero Django imports; fully unit-testable.
- `embeddings.py` — `EmbeddingClient` over a swappable backend protocol. `OpenAIEmbeddingBackend` for production; `MockEmbeddingBackend` (deterministic PRNG-seeded unit vectors) for tests.
- `pipeline/semantic_match.py` — `SemanticMatchEvaluator` blends 60% embedding signal + 40% RRF. When no ranks are available (embeddings-only mode), the RRF term collapses and embedding similarity carries full weight. Observability is wired at construction time via `@pipeline_observability.instrument("semantic_match")`.
- `search/hybrid_search.py` — `HybridSearchEngine` with the raw PostgreSQL FTS and pgvector queries. This is the one module that needs a live DB for integration tests — cleanly separated so all unit tests remain DB-free.

One design decision worth flagging: the `section_weighted_similarity` function normalizes by the sum of weights for *present* sections only, not by 1.0. This means a candidate who has no `education` section doesn't get penalized — the remaining section weights redistribute proportionally. The unit tests encode this as a contract.