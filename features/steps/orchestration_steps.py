"""
Step definitions for features/pipeline_orchestration.feature.

Uses a real HardGateEvaluator (stateless, no DB) and a StubRubricEvaluator.
SemanticMatchEvaluator is used with pre-built embeddings from step state.
All evaluator calls are tracked via a spy wrapper so the 'was executed' steps work.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch, wraps

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from resume_pipeline.logging_module import StructuredAuditLogger
from resume_pipeline.observability import PipelineObservability
from resume_pipeline.pipeline.hard_gate import GateOutcome, HardGateEvaluator
from resume_pipeline.pipeline.orchestrator import PipelineInput, PipelineOrchestrator
from resume_pipeline.pipeline.rubric_protocol import RubricResult, StubRubricEvaluator
from resume_pipeline.pipeline.semantic_match import SemanticMatchEvaluator, SemanticMatchScore

pytestmark = pytest.mark.bdd

scenarios("pipeline_orchestration.feature")


# ---------------------------------------------------------------------------
# Shared context fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx() -> dict:
    return {}


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

@given("the pipeline orchestrator is initialized with all stage evaluators", target_fixture="ctx")
def init_orchestrator() -> dict:
    obs = PipelineObservability(sink=lambda _: None)

    # Real evaluators — not mocks.
    gate_ev = HardGateEvaluator()
    semantic_ev = SemanticMatchEvaluator()
    rubric_ev = StubRubricEvaluator()

    # Spy wrappers to track whether each stage was called.
    class _CallSpy:
        def __init__(self, target, method_name):
            self._target = target
            self._method_name = method_name
            self.called = False
            original = getattr(target, method_name)

            @wraps(original)
            def _spy(*args, **kwargs):
                self.called = True
                return original(*args, **kwargs)

            setattr(target, method_name, _spy)

    semantic_spy = _CallSpy(semantic_ev, "_evaluate_impl")
    rubric_spy = _CallSpy(rubric_ev, "evaluate")

    # Capture log output for audit assertions.
    audit_log_capture = []
    logger = logging.getLogger("pipeline.audit")

    class _CapturingHandler(logging.Handler):
        def emit(self, record):
            audit_log_capture.append(record.getMessage())

    handler = _CapturingHandler()
    logger.addHandler(handler)

    orch = PipelineOrchestrator(
        gate_evaluator=gate_ev,
        semantic_evaluator=semantic_ev,
        rubric_evaluator=rubric_ev,
        observability=obs,
    )

    return {
        "orchestrator": orch,
        "obs": obs,
        "semantic_spy": semantic_spy,
        "rubric_spy": rubric_spy,
        "audit_log": audit_log_capture,
        "audit_handler": handler,
        "must_haves": {},
        "resume_parsed": {},
        "candidate_embeddings": {},
        "job_embeddings": {},
        "lexical_rank": None,
        "semantic_rank": None,
        "semantic_score_override": None,
        "rubric_score_override": None,
        "evidence_quality_override": None,
    }


# ---------------------------------------------------------------------------
# Given — resume fields
# ---------------------------------------------------------------------------

@given(parsers.parse("a candidate resumes with total experience years of {years:d}"))
def candidate_experience(ctx: dict, years: int) -> None:
    ctx["resume_parsed"]["total_experience_years"] = float(years)


@given("a candidate resume has no parseable experience field")
def candidate_no_experience(ctx: dict) -> None:
    ctx["resume_parsed"].pop("total_experience_years", None)


@given(parsers.parse('a candidate has skills "{skills}"'))
def candidate_skills(ctx: dict, skills: str) -> None:
    ctx["resume_parsed"]["skills"] = skills


# ---------------------------------------------------------------------------
# Given — job must-haves
# ---------------------------------------------------------------------------

@given(parsers.parse("a job requires minimum {years:d} years experience"))
def job_requires_years(ctx: dict, years: int) -> None:
    ctx["must_haves"]["exp"] = {"type": "years_experience", "minimum_years": years}


@given(parsers.parse('a job requires keyword "{keyword}" in skills'))
def job_requires_keyword(ctx: dict, keyword: str) -> None:
    ctx["must_haves"]["keyword"] = {
        "type": "keyword_presence",
        "keywords": [keyword],
        "sections": ["skills"],
    }


# ---------------------------------------------------------------------------
# Given — embeddings
# ---------------------------------------------------------------------------

@given("the candidate has matching section embeddings for the job")
def matching_embeddings(ctx: dict) -> None:
    ctx["candidate_embeddings"] = {"experience": [1.0, 0.0], "skills": [1.0, 0.0]}
    ctx["job_embeddings"] = {"experience": [1.0, 0.0], "skills": [1.0, 0.0]}
    ctx["lexical_rank"] = 1
    ctx["semantic_rank"] = 1


# ---------------------------------------------------------------------------
# Given — score overrides (for formula tests)
# ---------------------------------------------------------------------------

@given(parsers.parse("the semantic match score will be {score:f}"))
def semantic_score_override(ctx: dict, score: float) -> None:
    ctx["semantic_score_override"] = score


@given(parsers.parse("the rubric normalized score will be {score:f}"))
def rubric_score_override(ctx: dict, score: float) -> None:
    ctx["rubric_score_override"] = score


@given(parsers.parse("the evidence quality will be {score:f}"))
def evidence_quality_override(ctx: dict, score: float) -> None:
    ctx["evidence_quality_override"] = score


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------

@when("the pipeline runs")
def run_pipeline(ctx: dict) -> None:
    orch: PipelineOrchestrator = ctx["orchestrator"]

    # Apply score overrides by patching the rubric stub if requested.
    if ctx.get("rubric_score_override") is not None or ctx.get("evidence_quality_override") is not None:
        original_evaluate = orch._rubric.evaluate

        def _overridden_evaluate(resume_parsed, job_requirements):
            result = original_evaluate(resume_parsed, job_requirements)
            if ctx.get("rubric_score_override") is not None:
                result = RubricResult(
                    normalized_score=ctx["rubric_score_override"],
                    evidence_quality=ctx.get("evidence_quality_override", result.evidence_quality),
                    criterion_scores=result.criterion_scores,
                )
            return result

        orch._rubric.evaluate = _overridden_evaluate

    if ctx.get("semantic_score_override") is not None:
        original_sem = orch._semantic._evaluate_impl

        def _overridden_sem(*args, **kwargs):
            result = original_sem(*args, **kwargs)
            result.final_score = ctx["semantic_score_override"]
            return result

        orch._semantic._evaluate_impl = _overridden_sem
        orch._semantic.evaluate = orch._obs.instrument("semantic_match")(orch._semantic._evaluate_impl)

    pipeline_input = PipelineInput(
        application_id="test-app-001",
        job_must_haves=ctx["must_haves"],
        resume_parsed=ctx["resume_parsed"],
        candidate_embeddings=ctx.get("candidate_embeddings", {}),
        job_embeddings=ctx.get("job_embeddings", {}),
        lexical_rank=ctx.get("lexical_rank"),
        semantic_rank=ctx.get("semantic_rank"),
        job_requirements={},
    )

    ctx["result"] = orch.run(pipeline_input)


# ---------------------------------------------------------------------------
# Then — final score
# ---------------------------------------------------------------------------

@then(parsers.parse("the final score is {expected:f}"))
def assert_final_score_exact(ctx: dict, expected: float) -> None:
    assert ctx["result"].final_score == pytest.approx(expected, abs=1e-9)


@then(parsers.parse("the final score is approximately {expected:f}"))
def assert_final_score_approx(ctx: dict, expected: float) -> None:
    assert ctx["result"].final_score == pytest.approx(expected, abs=1e-3)


@then(parsers.parse("the final score is greater than {threshold:f}"))
def assert_final_score_gt(ctx: dict, threshold: float) -> None:
    assert ctx["result"].final_score > threshold


# ---------------------------------------------------------------------------
# Then — gate outcome
# ---------------------------------------------------------------------------

@then(parsers.parse('the gate outcome is "{expected}"'))
def assert_gate_outcome(ctx: dict, expected: str) -> None:
    assert ctx["result"].gate_outcome == GateOutcome(expected)


# ---------------------------------------------------------------------------
# Then — stage execution
# ---------------------------------------------------------------------------

@then("the semantic match stage was not executed")
def assert_semantic_not_executed(ctx: dict) -> None:
    assert "semantic_match" not in ctx["result"].stages_executed


@then("the rubric scoring stage was not executed")
def assert_rubric_not_executed(ctx: dict) -> None:
    assert "rubric" not in ctx["result"].stages_executed


@then("the semantic match stage was executed")
def assert_semantic_executed(ctx: dict) -> None:
    assert "semantic_match" in ctx["result"].stages_executed


@then("the rubric scoring stage was executed")
def assert_rubric_executed(ctx: dict) -> None:
    assert "rubric" in ctx["result"].stages_executed


@then(parsers.parse('the stages executed are "{expected_csv}"'))
def assert_stages_executed(ctx: dict, expected_csv: str) -> None:
    expected = [s.strip() for s in expected_csv.split(",")]
    assert ctx["result"].stages_executed == expected


# ---------------------------------------------------------------------------
# Then — observability
# ---------------------------------------------------------------------------

@then(parsers.parse("there are exactly {count:d} observability latency records"))
def assert_latency_record_count(ctx: dict, count: int) -> None:
    actual = len(ctx["obs"].get_records())
    assert actual == count, f"Expected {count} records, got {actual}"


@then(parsers.parse("there is exactly {count:d} observability latency record"))
def assert_single_latency_record(ctx: dict, count: int) -> None:
    actual = len(ctx["obs"].get_records())
    assert actual == count, f"Expected {count} record, got {actual}"


# ---------------------------------------------------------------------------
# Then — audit log
# ---------------------------------------------------------------------------

@then(parsers.parse('the audit log contains a "{event_type}" event'))
def assert_audit_event(ctx: dict, event_type: str) -> None:
    matching = [line for line in ctx["audit_log"] if f'"event": "{event_type}"' in line]
    assert len(matching) >= 1, (
        f'No "{event_type}" event found in audit log.\n'
        f"Log contents: {ctx['audit_log']}"
    )


@then(parsers.parse('the audit log contains at least {count:d} "{event_type}" event'))
def assert_audit_event_count_min(ctx: dict, count: int, event_type: str) -> None:
    matching = [line for line in ctx["audit_log"] if f'"event": "{event_type}"' in line]
    assert len(matching) >= count


# ---------------------------------------------------------------------------
# Then — confidence
# ---------------------------------------------------------------------------

@then(parsers.parse("the pipeline result confidence is less than {threshold:f}"))
def assert_confidence_lt(ctx: dict, threshold: float) -> None:
    assert ctx["result"].confidence is not None
    assert ctx["result"].confidence < threshold
