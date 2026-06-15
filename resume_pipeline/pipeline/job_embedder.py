"""
Job section embedding pipeline.

Exports:
    embed_job_sections(job: Job) -> list[JobSectionEmbedding]

Embeds four sections of a Job record:
    title         — the job title as a short phrase
    description   — the full job description
    requirements  — JSON-serialised requirements_raw dict
    must_haves    — JSON-serialised must_haves dict

Each section is upserted into JobSectionEmbedding (get_or_create + update),
so calling this function after a PATCH does NOT create duplicate rows.

The embedding API call is isolated in _call_embedding_api() so that tests
can patch it without touching the ORM:

    with patch("resume_pipeline.pipeline.job_embedder._call_embedding_api",
               return_value=[0.0] * 1536):
        embed_job_sections(job)
"""

from __future__ import annotations

import json
import os


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def embed_job_sections(job) -> list:
    """
    Compute embeddings for all sections of ``job`` and persist them as
    ``JobSectionEmbedding`` rows.

    Args:
        job: A saved ``resume_pipeline.models.Job`` instance.

    Returns:
        A list of the upserted ``JobSectionEmbedding`` instances.

    Notes:
        - Uses upsert semantics (get_or_create + update), so it is safe to
          call this after every PATCH without ballooning row count.
        - Network / API errors are NOT caught here — the caller (view or
          Celery task) is responsible for handling TimeoutError etc.
    """
    # Import here to keep this module importable without Django setup
    # (the module-level import would run during test collection).
    from resume_pipeline.models import JobSectionEmbedding

    sections = _build_sections(job)
    results: list = []

    for section_name, text in sections.items():
        vector = _call_embedding_api(text)

        embedding_obj, _ = JobSectionEmbedding.objects.get_or_create(
            job=job,
            section=section_name,
            defaults={
                "content":    text,
                "embedding":  vector,
                "model_name": _model_name(),
            },
        )
        # Update if it already existed (PATCH scenario)
        if embedding_obj.content != text or embedding_obj.embedding != vector:
            embedding_obj.content   = text
            embedding_obj.embedding = vector
            embedding_obj.model_name = _model_name()
            embedding_obj.save(update_fields=["content", "embedding", "model_name"])

        results.append(embedding_obj)

    return results


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_sections(job) -> dict[str, str]:
    """
    Convert a Job's fields into the four text sections to embed.
    requirements_raw and must_haves are serialised to compact JSON so
    that the embedding captures the structure.
    """
    return {
        "title":        job.title,
        "description":  job.description,
        "requirements": json.dumps(job.requirements_raw, sort_keys=True),
        "must_haves":   json.dumps(job.must_haves, sort_keys=True),
    }


def _call_embedding_api(text: str) -> list[float]:
    """
    Call the configured embedding API and return the float vector.

    Backend selection mirrors LLM_BACKEND logic:
      - "mock"       → deterministic zero vector (default, no network)
      - "openai"     → OpenAI text-embedding-ada-002
      - "anthropic"  → Not supported for embeddings; falls back to mock

    This function is intentionally isolated so tests can patch it:
        patch("resume_pipeline.pipeline.job_embedder._call_embedding_api",
              return_value=[0.0] * 1536)
    """
    backend = os.environ.get("LLM_BACKEND", "mock").lower()

    if backend == "openai":
        return _openai_embed(text)

    # mock / anthropic / anything else → deterministic mock vector
    return _mock_embed(text)


def _openai_embed(text: str) -> list[float]:
    """Call the OpenAI embeddings API. Requires OPENAI_API_KEY in the environment."""
    import openai

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.embeddings.create(
        input=[text],
        model=os.environ.get("EMBEDDING_MODEL", "text-embedding-ada-002"),
    )
    return response.data[0].embedding


def _mock_embed(text: str) -> list[float]:
    """
    Deterministic mock embedding: L2-normalised vector derived from the
    text hash so that repeated calls for the same text return identical vectors.
    """
    import hashlib, math

    dim = 1536
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16)
    # Simple deterministic pseudo-random via LCG seeded with text hash
    state = seed
    raw: list[float] = []
    for _ in range(dim):
        state = (state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        raw.append((state / 2**64) * 2 - 1)

    # L2-normalise
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


def _model_name() -> str:
    backend = os.environ.get("LLM_BACKEND", "mock").lower()
    if backend == "openai":
        return os.environ.get("EMBEDDING_MODEL", "text-embedding-ada-002")
    return "mock"
