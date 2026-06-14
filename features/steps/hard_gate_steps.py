"""
Step definitions for features/hard_gate.feature.

Outer-loop BDD — these steps wire Gherkin scenarios to the domain objects.
They must NOT contain logic; they delegate entirely to the implementation layer.

Parsing conventions for the simplified table format used in the feature file:
  - Each Gherkin table row maps column headers to criterion config fields.
  - Empty cells are treated as absent keys (not included in config).
  - The "type" column always populates config["type"].
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from resume_pipeline.pipeline.final_score import FinalScoreCalculator
from resume_pipeline.pipeline.hard_gate import (
    GateOutcome,
    HardGateEvaluation,
    HardGateEvaluator,
)


# ---------------------------------------------------------------------------
# Scenario binding (tie each scenario title to the feature file)
# ---------------------------------------------------------------------------

# Uncomment to bind scenarios explicitly; alternatively use pytest-bdd's
# `scenarios("hard_gate.feature")` in conftest.py for bulk binding.
#
# @scenario("../hard_gate.feature", "Candidate satisfies a single years-of-experience criterion")
# def test_pass_single_exp(): ...


# ---------------------------------------------------------------------------
# Shared state container
# ---------------------------------------------------------------------------
# pytest-bdd passes a "context" namespace dict between steps via fixtures.
# We use a plain dict injected as the `ctx` fixture.


@pytest.fixture
def ctx() -> dict:
    return {}


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

@given("the hard gate evaluator is initialized", target_fixture="ctx")
def init_evaluator() -> dict:
    return {"evaluator": HardGateEvaluator()}


# ---------------------------------------------------------------------------
# Given — job criteria
# ---------------------------------------------------------------------------

@given(parsers.parse("a job has must-have criteria:\n{raw_table}"))
def job_must_have_criteria(ctx: dict, raw_table: str) -> None:
    """
    Parses the simplified Gherkin table into a must_haves dict.

    Table columns (any subset):
        criterion, type, minimum_years, keywords, sections, required
    """
    rows = _parse_table(raw_table)
    must_haves: dict = {}

    for row in rows:
        name = row.pop("criterion")
        criterion_type = row.pop("type")
        config: dict = {"type": criterion_type}

        if row.get("minimum_years"):
            config["minimum_years"] = int(row["minimum_years"])
        if row.get("keywords"):
            config["keywords"] = [k.strip() for k in row["keywords"].split(",")]
        if row.get("sections"):
            config["sections"] = [s.strip() for s in row["sections"].split(",")]
        if row.get("required"):
            config["required"] = [r.strip() for r in row["required"].split(",")]

        must_haves[name] = config

    ctx["must_haves"] = must_haves


# ---------------------------------------------------------------------------
# Given — candidate resume
# ---------------------------------------------------------------------------

@given(parsers.parse("a candidate resume has these fields:\n{raw_table}"))
def candidate_resume_fields(ctx: dict, raw_table: str) -> None:
    """Parses a two-column table (field | value) into the resume_parsed dict."""
    rows = _parse_table(raw_table)
    resume_parsed: dict = {}

    for row in rows:
        field = row.get("field", "").strip()
        value = row.get("value", "").strip()

        if not field:
            continue

        # Coerce known numeric fields.
        if field == "total_experience_years":
            resume_parsed[field] = float(value)
        elif field == "certifications":
            resume_parsed[field] = [c.strip() for c in value.split(",") if c.strip()]
        else:
            resume_parsed[field] = value

    ctx["resume_parsed"] = resume_parsed


# ---------------------------------------------------------------------------
# Given — final score inputs
# ---------------------------------------------------------------------------

@given(parsers.parse('a candidate application has a gate outcome of "{outcome}"'))
def gate_outcome_for_score(ctx: dict, outcome: str) -> None:
    ctx["gate_outcome"] = GateOutcome(outcome)


@given(parsers.parse("the semantic match score is {value:f}"))
def semantic_match_score(ctx: dict, value: float) -> None:
    ctx["semantic_match"] = value


@given(parsers.parse("the rubric normalized score is {value:f}"))
def rubric_normalized_score(ctx: dict, value: float) -> None:
    ctx["rubric_score_norm"] = value


@given(parsers.parse("the evidence quality score is {value:f}"))
def evidence_quality_score(ctx: dict, value: float) -> None:
    ctx["evidence_quality"] = value


# ---------------------------------------------------------------------------
# When — run evaluations
# ---------------------------------------------------------------------------

@when("the hard gate evaluation runs")
def run_hard_gate_evaluation(ctx: dict) -> None:
    ctx["evaluation"] = ctx["evaluator"].evaluate(
        must_haves=ctx["must_haves"],
        resume_parsed=ctx.get("resume_parsed", {}),
    )


@when("the final score is calculated")
def calculate_final_score(ctx: dict) -> None:
    calculator = FinalScoreCalculator()
    ctx["final_score"] = calculator.calculate(
        gate_outcome=ctx["gate_outcome"],
        semantic_match=ctx.get("semantic_match", 0.0),
        rubric_score_norm=ctx.get("rubric_score_norm", 0.0),
        evidence_quality=ctx.get("evidence_quality", 0.0),
    )


# ---------------------------------------------------------------------------
# Then — assertions
# ---------------------------------------------------------------------------

@then(parsers.parse('the overall gate outcome is "{expected}"'))
def assert_overall_outcome(ctx: dict, expected: str) -> None:
    evaluation: HardGateEvaluation = ctx["evaluation"]
    assert evaluation.outcome == GateOutcome(expected), (
        f"Expected overall outcome '{expected}', got '{evaluation.outcome.value}'. "
        f"Criterion results: {[(r.name, r.outcome.value) for r in evaluation.criterion_results]}"
    )


@then(parsers.parse('the criterion "{criterion_name}" outcome is "{expected}"'))
def assert_criterion_outcome(ctx: dict, criterion_name: str, expected: str) -> None:
    evaluation: HardGateEvaluation = ctx["evaluation"]
    by_name = {r.name: r for r in evaluation.criterion_results}

    assert criterion_name in by_name, (
        f"Criterion '{criterion_name}' not found. "
        f"Known criteria: {list(by_name.keys())}"
    )

    actual = by_name[criterion_name].outcome
    assert actual == GateOutcome(expected), (
        f"Criterion '{criterion_name}': expected '{expected}', got '{actual.value}'. "
        f"Evidence: {by_name[criterion_name].evidence}"
    )


@then(parsers.parse("the final score is exactly {expected:f}"))
def assert_final_score(ctx: dict, expected: float) -> None:
    actual = ctx["final_score"]
    assert actual == pytest.approx(expected, abs=1e-9), (
        f"Expected final score {expected}, got {actual}"
    )


# ---------------------------------------------------------------------------
# Table parser utility
# ---------------------------------------------------------------------------

def _parse_table(raw: str) -> list[dict[str, str]]:
    """
    Parses a pipe-delimited Gherkin table string into a list of dicts.

    Input example:
        | criterion | type             | minimum_years |
        | exp       | years_experience | 5             |

    Returns:
        [{"criterion": "exp", "type": "years_experience", "minimum_years": "5"}]
    """
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    if not lines:
        return []

    def split_row(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip("|").split("|")]

    headers = split_row(lines[0])
    rows = []
    for line in lines[1:]:
        values = split_row(line)
        row = {h: v for h, v in zip(headers, values)}
        rows.append(row)

    return rows
