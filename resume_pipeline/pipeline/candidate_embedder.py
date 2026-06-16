"""
Candidate section embedding pipeline.

Exports:
    embed_candidate_sections(candidate: Candidate) -> list[SectionEmbedding]

Embeds each text section from candidate.resume_parsed and persists the result
as SectionEmbedding rows (one per section, upsert semantics).

Only sections whose names are in EMBEDDABLE_SECTIONS and whose values are
non-empty strings are embedded; numeric metadata fields like
total_experience_years are skipped.

Mirrors the structure of job_embedder.embed_job_sections().
"""

from __future__ import annotations

import math
import os
import time

from resume_pipeline.logging_module import audit_logger


#: Sections that have a corresponding ResumeSection choice and should be embedded.
EMBEDDABLE_SECTIONS = frozenset(
    ["summary", "experience", "skills", "education", "certifications", "projects"]
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def embed_candidate_sections(candidate) -> list:
    """
    Compute embeddings for all text sections in candidate.resume_parsed and
    persist them as SectionEmbedding rows.

    Args:
        candidate: A saved ``resume_pipeline.models.Candidate`` instance.

    Returns:
        List of upserted SectionEmbedding instances.

    Notes:
        - Safe to call after a resume re-parse — uses upsert semantics.
        - Exceptions from the embedding API are re-raised after logging;
          the caller is responsible for handling or swallowing them.
    """
    from resume_pipeline.models import SectionEmbedding

    candidate_id = str(candidate.id)
    backend = _model_name()
    sections = {
        k: v
        for k, v in candidate.resume_parsed.items()
        if k in EMBEDDABLE_SECTIONS and isinstance(v, str) and v.strip()
    }

    results: list = []
    t_total = time.perf_counter()

    for section_name, text in sections.items():
        try:
            vector = _call_embedding_api(text)
        except Exception as exc:
            audit_logger.log_pipeline_exception(
                application_id=f"candidate:{candidate_id}",
                stage=f"candidate_embedding_{section_name}",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            raise

        embedding_obj, created = SectionEmbedding.objects.get_or_create(
            candidate=candidate,
            section=section_name,
            defaults={
                "content":    text,
                "embedding":  vector,
                "model_name": backend,
            },
        )
        if not created and embedding_obj.content != text:
            embedding_obj.content    = text
            embedding_obj.embedding  = vector
            embedding_obj.model_name = backend
            embedding_obj.save(update_fields=["content", "embedding", "model_name"])

        results.append(embedding_obj)

    total_ms = (time.perf_counter() - t_total) * 1000
    audit_logger._emit_raw(
        event_type="candidate_embeddings_built",
        payload={
            "candidate_id":   candidate_id,
            "sections":       list(sections.keys()),
            "sections_count": len(results),
            "backend":        backend,
            "latency_ms":     round(total_ms, 3),
        },
    )

    return results


# ---------------------------------------------------------------------------
# Private helpers — identical logic to job_embedder
# ---------------------------------------------------------------------------

def _call_embedding_api(text: str) -> list[float]:
    backend = os.environ.get("LLM_BACKEND", "mock").lower()
    if backend == "openai":
        return _openai_embed(text)
    return _mock_embed(text)


def _openai_embed(text: str) -> list[float]:
    import openai
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.embeddings.create(
        input=[text],
        model=os.environ.get("EMBEDDING_MODEL", "text-embedding-ada-002"),
    )
    return response.data[0].embedding


def _mock_embed(text: str) -> list[float]:
    import hashlib
    dim = 1536
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16)
    state = seed
    raw: list[float] = []
    for _ in range(dim):
        state = (state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        raw.append((state / 2**64) * 2 - 1)
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


def _model_name() -> str:
    backend = os.environ.get("LLM_BACKEND", "mock").lower()
    if backend == "openai":
        return os.environ.get("EMBEDDING_MODEL", "text-embedding-ada-002")
    return "mock"
