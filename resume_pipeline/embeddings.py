"""
Embedding Client — adapter over embedding model backends.

Design:
  EmbeddingClient depends on an injected backend (duck-typed).
  In production: OpenAIEmbeddingBackend or LocalModelBackend.
  In tests: MockEmbeddingBackend (deterministic, no network).

This keeps all API coupling at the backend layer and makes the client
trivially swappable — essential when we benchmark different embedding
models or move to a self-hosted model.

Usage::

    # Production
    from openai import OpenAI
    client = EmbeddingClient(backend=OpenAIEmbeddingBackend(OpenAI()))

    # Tests
    client = EmbeddingClient(backend=MockEmbeddingBackend(dim=1536))
    vector = client.embed("Senior Python Engineer with 7 years experience")
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Protocol


# ---------------------------------------------------------------------------
# Backend protocol — duck-typed interface
# ---------------------------------------------------------------------------

class EmbeddingBackend(Protocol):
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


# ---------------------------------------------------------------------------
# Production backend — OpenAI
# ---------------------------------------------------------------------------

class OpenAIEmbeddingBackend:
    """
    Wraps the OpenAI embeddings API.

    Args:
        client: An `openai.OpenAI` instance (injected for testability).
        model: Embedding model name.
    """

    def __init__(self, client, model: str = "text-embedding-ada-002") -> None:
        self._client = client
        self._model = model

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(input=[text], model=self._model)
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(input=texts, model=self._model)
        # Response preserves input order.
        return [item.embedding for item in response.data]


# ---------------------------------------------------------------------------
# Test backend — deterministic mock
# ---------------------------------------------------------------------------

class MockEmbeddingBackend:
    """
    Returns deterministic unit vectors derived from a hash of the input text.

    Properties:
      - Same text always produces the same vector (deterministic).
      - Different texts produce different vectors (hash collision probability is
        negligible for reasonable test cases).
      - Vectors are L2-normalized (unit length), so cosine_similarity between
        identical texts is exactly 1.0.

    Args:
        dim: Embedding dimension (must match the dimension used in production).
    """

    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    def embed(self, text: str) -> list[float]:
        return self._hash_to_unit_vector(text, self._dim)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    @staticmethod
    def _hash_to_unit_vector(text: str, dim: int) -> list[float]:
        """
        Produce a deterministic unit vector from text using a seeded PRNG.

        We derive an integer seed from the SHA-256 hash of the input text,
        then draw Gaussian samples from Python's standard Random. This avoids
        IEEE 754 NaN bit-patterns that raw byte unpacking can produce.
        """
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        values = [rng.gauss(0.0, 1.0) for _ in range(dim)]

        # L2-normalize to produce a unit vector.
        norm = math.sqrt(sum(v * v for v in values))
        if norm == 0.0:
            return [0.0] * dim
        return [v / norm for v in values]


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class EmbeddingClient:
    """
    Thin client wrapping an EmbeddingBackend.

    Responsibilities:
      - Text preprocessing (strip, truncate to model token limit).
      - Delegating to the backend.
      - (Future) caching layer.

    Args:
        backend: Any object satisfying the EmbeddingBackend protocol.
        max_chars: Soft character limit before truncation (not token count).
                   Default is conservative for ada-002's 8191-token limit.
    """

    # ~8000 tokens * ~4 chars/token — conservative truncation guard.
    DEFAULT_MAX_CHARS = 32_000

    def __init__(
        self,
        backend: EmbeddingBackend,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> None:
        self._backend = backend
        self._max_chars = max_chars

    def embed(self, text: str) -> list[float]:
        """
        Embed a single text string.

        Args:
            text: Raw text to embed.

        Returns:
            Embedding vector as a list of floats.
        """
        prepared = self._prepare(text)
        return self._backend.embed(prepared)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of texts in a single API call.

        Returns:
            List of embedding vectors, in the same order as input texts.
        """
        prepared = [self._prepare(t) for t in texts]
        return self._backend.embed_batch(prepared)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prepare(self, text: str) -> str:
        """Strip whitespace and truncate to max_chars."""
        text = text.strip()
        if len(text) > self._max_chars:
            text = text[: self._max_chars]
        return text
