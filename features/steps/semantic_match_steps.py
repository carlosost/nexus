"""
Step definitions for features/semantic_match.feature.

Delegates entirely to domain objects — no logic here.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, then, when

from resume_pipeline.observability import PipelineObservability
from resume_pipeline.pipeline.semantic_match import SemanticMatchEvaluator
from resume_pipeline.search.rrf import (
    compute_rrf_score,
    cosine_similarity,
    normalize_rrf_score,
    section_weighted_similarity,
)


# ---------------------------------------------------------------------------
# Shared state fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx() -> dict:
    return {}


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

@given("the semantic match evaluator is initialized", target_fixture="ctx")
def init_evaluator() -> dict:
    obs = PipelineObservability()
    evaluator = SemanticMatchEvaluator()
    # Wire a fresh observability instance so tests can inspect records.
    evaluator.evaluate = obs.instrument("semantic_match")(evaluator._evaluate_impl)
    return {"evaluator": evaluator, "obs": obs}


@given(parsers.parse("the standard section weights are:\n{raw_table}"))
def standard_section_weights(ctx: dict, raw_table: str) -> None:
    rows = _parse_table(raw_table)
    ctx["section_weights"] = {
        row["section"]: float(row["weight"]) for row in rows
    }


# ---------------------------------------------------------------------------
# Given — per-section embeddings
# ---------------------------------------------------------------------------

@given(parsers.parse('a candidate section "{section}" has embedding vector {vector}'))
def candidate_section_vector(ctx: dict, section: str, vector: str) -> None:
    ctx.setdefault("candidate_embeddings", {})[section] = _parse_vector(vector)


@given(parsers.parse('the job section "{section}" has embedding vector {vector}'))
def job_section_vector(ctx: dict, section: str, vector: str) -> None:
    ctx.setdefault("job_embeddings", {})[section] = _parse_vector(vector)


@given(parsers.parse("candidate section embeddings:\n{raw_table}"))
def candidate_section_embeddings_table(ctx: dict, raw_table: str) -> None:
    rows = _parse_table(raw_table)
    ctx["candidate_embeddings"] = {
        row["section"]: _parse_vector(row["vector"]) for row in rows
    }


@given(parsers.parse("job section embeddings:\n{raw_table}"))
def job_section_embeddings_table(ctx: dict, raw_table: str) -> None:
    rows = _parse_table(raw_table)
    ctx["job_embeddings"] = {
        row["section"]: _parse_vector(row["vector"]) for row in rows
    }


# ---------------------------------------------------------------------------
# Given — RRF rank inputs
# ---------------------------------------------------------------------------

@given(parsers.parse("a candidate has lexical rank {lex:d} and semantic rank {sem:d}"))
def both_ranks(ctx: dict, lex: int, sem: int) -> None:
    ctx["lexical_rank"] = lex
    ctx["semantic_rank"] = sem


@given(parsers.parse("a candidate has lexical rank {lex:d} and no semantic rank"))
def only_lexical_rank(ctx: dict, lex: int) -> None:
    ctx["lexical_rank"] = lex
    ctx["semantic_rank"] = None


@given(parsers.parse("a candidate has no lexical rank and semantic rank {sem:d}"))
def only_semantic_rank(ctx: dict, sem: int) -> None:
    ctx["lexical_rank"] = None
    ctx["semantic_rank"] = sem


@given("a candidate has no lexical rank and no semantic rank")
def no_ranks(ctx: dict) -> None:
    ctx["lexical_rank"] = None
    ctx["semantic_rank"] = None


# ---------------------------------------------------------------------------
# Given — candidate comparison scenarios
# ---------------------------------------------------------------------------

@given("a candidate A has perfect match on \"experience\" and zero match on \"skills\"")
def candidate_a_exp_dominant(ctx: dict) -> None:
    ctx["candidate_a_embeddings"] = {
        "experience": [1.0, 0.0],
        "skills": [0.0, 1.0],   # orthogonal to job skills vec
    }
    ctx.setdefault("job_embeddings_cmp", {
        "experience": [1.0, 0.0],
        "skills": [1.0, 0.0],
    })


@given("a candidate B has zero match on \"experience\" and perfect match on \"skills\"")
def candidate_b_skills_dominant(ctx: dict) -> None:
    ctx["candidate_b_embeddings"] = {
        "experience": [0.0, 1.0],  # orthogonal to job exp vec
        "skills": [1.0, 0.0],
    }
    ctx.setdefault("job_embeddings_cmp", {
        "experience": [1.0, 0.0],
        "skills": [1.0, 0.0],
    })


# ---------------------------------------------------------------------------
# When — execute computations
# ---------------------------------------------------------------------------

@when(parsers.parse('the cosine similarity is computed for section "{section}"'))
def compute_cosine_for_section(ctx: dict, section: str) -> None:
    a = ctx["candidate_embeddings"][section]
    b = ctx["job_embeddings"][section]
    ctx["section_similarity"] = cosine_similarity(a, b)
    ctx["computed_section"] = section


@when("the section-weighted similarity is computed")
def compute_section_weighted(ctx: dict) -> None:
    evaluator: SemanticMatchEvaluator = ctx["evaluator"]
    section_scores = evaluator.compute_section_scores(
        ctx.get("candidate_embeddings", {}),
        ctx.get("job_embeddings", {}),
    )
    weights = ctx.get("section_weights", evaluator._section_weights)
    ctx["weighted_similarity"] = section_weighted_similarity(section_scores, weights)


@when("both candidates' section-weighted similarities are computed")
def compute_both_candidate_similarities(ctx: dict) -> None:
    evaluator: SemanticMatchEvaluator = ctx["evaluator"]
    job_emb = ctx["job_embeddings_cmp"]

    scores_a = evaluator.compute_section_scores(ctx["candidate_a_embeddings"], job_emb)
    scores_b = evaluator.compute_section_scores(ctx["candidate_b_embeddings"], job_emb)

    weights = evaluator._section_weights
    ctx["similarity_a"] = section_weighted_similarity(scores_a, weights)
    ctx["similarity_b"] = section_weighted_similarity(scores_b, weights)


@when(parsers.parse("the RRF score is computed with k={k:d}"))
def compute_rrf(ctx: dict, k: int) -> None:
    raw = compute_rrf_score(
        lexical_rank=ctx.get("lexical_rank"),
        semantic_rank=ctx.get("semantic_rank"),
        k=k,
    )
    num_sources = (
        (1 if ctx.get("lexical_rank") is not None else 0)
        + (1 if ctx.get("semantic_rank") is not None else 0)
    )
    ctx["rrf_score"] = normalize_rrf_score(raw, k=k, num_sources=num_sources)
    ctx["rrf_k"] = k


@when("the full semantic match evaluation runs")
def run_full_evaluation(ctx: dict) -> None:
    evaluator: SemanticMatchEvaluator = ctx["evaluator"]
    ctx["match_result"] = evaluator.evaluate(
        candidate_embeddings=ctx.get("candidate_embeddings", {}),
        job_embeddings=ctx.get("job_embeddings", {}),
        lexical_rank=ctx.get("lexical_rank"),
        semantic_rank=ctx.get("semantic_rank"),
    )


# ---------------------------------------------------------------------------
# Then — assertions
# ---------------------------------------------------------------------------

@then(parsers.parse("the section similarity score is {expected:f}"))
def assert_section_similarity(ctx: dict, expected: float) -> None:
    actual = ctx["section_similarity"]
    assert actual == pytest.approx(expected, abs=1e-3), (
        f"Section similarity: expected {expected}, got {actual}"
    )


@then(parsers.parse("the section similarity score is approximately {expected:f}"))
def assert_section_similarity_approx(ctx: dict, expected: float) -> None:
    actual = ctx["section_similarity"]
    assert actual == pytest.approx(expected, abs=0.001), (
        f"Section similarity: expected ≈ {expected}, got {actual}"
    )


@then(parsers.parse("the weighted similarity is greater than {threshold:f}"))
def assert_weighted_sim_gt(ctx: dict, threshold: float) -> None:
    assert ctx["weighted_similarity"] > threshold


@then(parsers.parse("the weighted similarity is less than {threshold:f}"))
def assert_weighted_sim_lt(ctx: dict, threshold: float) -> None:
    assert ctx["weighted_similarity"] < threshold


@then(parsers.parse("the weighted similarity is {expected:f}"))
def assert_weighted_sim_eq(ctx: dict, expected: float) -> None:
    assert ctx["weighted_similarity"] == pytest.approx(expected, abs=1e-9)


@then("candidate A weighted similarity is greater than candidate B weighted similarity")
def assert_a_beats_b(ctx: dict) -> None:
    assert ctx["similarity_a"] > ctx["similarity_b"], (
        f"Expected A ({ctx['similarity_a']:.4f}) > B ({ctx['similarity_b']:.4f})"
    )


@then(parsers.parse("the normalized RRF score is {expected:f}"))
def assert_rrf_eq(ctx: dict, expected: float) -> None:
    assert ctx["rrf_score"] == pytest.approx(expected, abs=1e-9)


@then(parsers.parse("the normalized RRF score is less than the score for ranks 1 and 1"))
def assert_rrf_lt_rank1(ctx: dict) -> None:
    k = ctx.get("rrf_k", 60)
    from resume_pipeline.search.rrf import compute_rrf_score, normalize_rrf_score
    raw_top = compute_rrf_score(1, 1, k=k)
    top_score = normalize_rrf_score(raw_top, k=k, num_sources=2)
    assert ctx["rrf_score"] < top_score


@then(parsers.parse("the normalized RRF score is greater than {threshold:f}"))
def assert_rrf_gt(ctx: dict, threshold: float) -> None:
    assert ctx["rrf_score"] > threshold


@then(parsers.parse("the normalized RRF score is less than {threshold:f}"))
def assert_rrf_lt(ctx: dict, threshold: float) -> None:
    assert ctx["rrf_score"] < threshold


@then(parsers.parse("the normalized RRF score is greater than or equal to {threshold:f}"))
def assert_rrf_gte(ctx: dict, threshold: float) -> None:
    assert ctx["rrf_score"] >= threshold


@then(parsers.parse("the normalized RRF score is less than or equal to {threshold:f}"))
def assert_rrf_lte(ctx: dict, threshold: float) -> None:
    assert ctx["rrf_score"] <= threshold


@then(parsers.parse("the final semantic match score is {expected:f}"))
def assert_final_match_score(ctx: dict, expected: float) -> None:
    actual = ctx["match_result"].final_score
    assert actual == pytest.approx(expected, abs=1e-6), (
        f"Final semantic score: expected {expected}, got {actual}"
    )


@then(parsers.parse('a latency record exists for stage "{stage}"'))
def assert_latency_record_exists(ctx: dict, stage: str) -> None:
    records = ctx["obs"].get_stage_records(stage)
    assert len(records) >= 1, f"No latency record found for stage '{stage}'"


@then(parsers.parse("the latency record has latency_ms greater than or equal to {threshold:f}"))
def assert_latency_gte(ctx: dict, threshold: float) -> None:
    records = ctx["obs"].get_records()
    assert records, "No latency records found"
    assert records[-1].latency_ms >= threshold


# ---------------------------------------------------------------------------
# Table and vector parsers
# ---------------------------------------------------------------------------

def _parse_table(raw: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    if not lines:
        return []
    headers = [h.strip() for h in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[1:]:
        values = [v.strip() for v in line.strip("|").split("|")]
        rows.append(dict(zip(headers, values)))
    return rows


def _parse_vector(raw: str) -> list[float]:
    """Parse '[1.0, 0.0, 0.0]' → [1.0, 0.0, 0.0]."""
    raw = raw.strip().lstrip("[").rstrip("]")
    return [float(x.strip()) for x in raw.split(",")]
