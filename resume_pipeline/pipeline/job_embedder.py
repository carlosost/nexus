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
import math
import os
import time

from resume_pipeline.logging_module import audit_logger
from resume_pipeline.observability import pipeline_observability


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

    job_id    = str(job.id)
    backend   = _model_name()
    sections  = _build_sections(job)

    audit_logger.log_job_embedding_started(
        job_id=job_id,
        job_title=job.title,
        sections=list(sections.keys()),
        backend=backend,
    )

    results: list = []
    t_total_start = time.perf_counter()

    for section_name, text in sections.items():
        t_section_start = time.perf_counter()
        try:
            with pipeline_observability.timed(
                "job_embedding_section", job_id=job_id, section=section_name
            ):
                vector = _call_embedding_api(text)
        except Exception as exc:
            audit_logger.log_job_embedding_failed(
                job_id=job_id,
                section=section_name,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            raise

        section_latency_ms = (time.perf_counter() - t_section_start) * 1000

        embedding_obj, created = JobSectionEmbedding.objects.get_or_create(
            job=job,
            section=section_name,
            defaults={
                "content":    text,
                "embedding":  vector,
                "model_name": backend,
            },
        )
        # Update if it already existed (PATCH scenario)
        if not created and (
            embedding_obj.content != text or embedding_obj.embedding != vector
        ):
            embedding_obj.content    = text
            embedding_obj.embedding  = vector
            embedding_obj.model_name = backend
            embedding_obj.save(update_fields=["content", "embedding", "model_name"])

        vector_norm = math.sqrt(sum(x * x for x in vector)) if vector else 0.0

        audit_logger.log_job_embedding_section_done(
            job_id=job_id,
            section=section_name,
            text_len=len(text),
            vector_dim=len(vector),
            vector_norm=vector_norm,
            is_new=created,
            latency_ms=section_latency_ms,
        )

        results.append(embedding_obj)

    total_latency_ms = (time.perf_counter() - t_total_start) * 1000

    audit_logger.log_job_embedding_completed(
        job_id=job_id,
        sections_count=len(results),
        backend=backend,
        latency_ms=total_latency_ms,
    )

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
    import hashlib

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
