"""
M0.6 — BDD step definitions for features/database_seeding.feature.

Strategy:
  - Spec-validation and gate-outcome scenarios: pure Python, no Django ORM.
  - Idempotency and audit scenarios: mock the ORM with unittest.mock.
  - No factory-boy, no DB transaction — fast, deterministic, zero I/O.

Context keys used across steps:
  ctx["gate_evaluation"]  — HardGateEvaluation returned by HardGateEvaluator
  ctx["mock_job_mgr"]     — Mock for Job.objects
  ctx["mock_cand_mgr"]    — Mock for Candidate.objects
  ctx["mock_app_mgr"]     — Mock for Application.objects
  ctx["seed_log_event"]   — dict parsed from the structured completion log
  ctx["all_exist"]        — bool: whether mock DB is in "all records exist" mode
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pytest_bdd import given, then, when

from resume_pipeline.management.commands._seed_data import (
    CANDIDATES_BY_EMAIL,
    CANDIDATE_SPECS,
    JOB_SPEC,
)
from resume_pipeline.pipeline.hard_gate import GateOutcome, HardGateEvaluator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(created: bool):
    """Return a mock manager whose get_or_create returns (MagicMock(), created)."""
    obj = MagicMock()
    mgr = MagicMock()
    mgr.get_or_create.return_value = (obj, created)
    return mgr, obj


def _run_seed_demo(ctx: dict) -> dict:
    """
    Invoke seed_demo.Command.handle() with fully mocked ORM.
    Captures the structured JSON log event emitted at INFO level.
    Stores mock managers in ctx for later assertions.
    Returns the parsed log event dict.
    """
    all_exist = ctx.get("all_exist", False)
    created = not all_exist

    job_mgr, job_obj = _make_manager(created=created)
    cand_mgr, cand_obj = _make_manager(created=created)
    app_mgr, _ = _make_manager(created=False)

    ctx["mock_job_mgr"] = job_mgr
    ctx["mock_cand_mgr"] = cand_mgr
    ctx["mock_app_mgr"] = app_mgr

    log_events: list[dict] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            msg = record.getMessage()
            if msg.strip().startswith("{"):
                try:
                    log_events.append(json.loads(msg))
                except json.JSONDecodeError:
                    pass

    capture = _Capture()
    seed_logger = logging.getLogger("pipeline.audit")
    seed_logger.setLevel(logging.INFO)
    seed_logger.addHandler(capture)

    try:
        from resume_pipeline.management.commands.seed_demo import Command

        with (
            patch("resume_pipeline.management.commands.seed_demo.Job") as MockJob,
            patch(
                "resume_pipeline.management.commands.seed_demo.Candidate"
            ) as MockCand,
            patch(
                "resume_pipeline.management.commands.seed_demo.Application"
            ) as MockApp,
        ):
            MockJob.objects = job_mgr
            MockCand.objects = cand_mgr
            MockApp.objects = app_mgr

            # Copy managers into ctx while patches are live so assertions can
            # inspect actual call_args (patch replaces the class reference).
            ctx["mock_job_mgr"] = job_mgr
            ctx["mock_cand_mgr"] = cand_mgr
            ctx["mock_app_mgr"] = app_mgr

            cmd = Command()
            cmd.stdout = MagicMock()
            cmd.style = MagicMock()
            cmd.handle(purge=False)
    finally:
        seed_logger.removeHandler(capture)

    completion = next(
        (e for e in log_events if e.get("event") == "demo_seed_completed"),
        {},
    )
    ctx["seed_log_event"] = completion
    return completion


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

@given("the seed data specification is loaded")
def seed_data_loaded(ctx: dict) -> None:
    """No-op — _seed_data is imported at module level; this step just confirms it."""
    ctx["job_spec"] = JOB_SPEC
    ctx["candidate_specs"] = CANDIDATE_SPECS
    ctx["candidates_by_email"] = CANDIDATES_BY_EMAIL


# ---------------------------------------------------------------------------
# Spec-validation steps (no DB)
# ---------------------------------------------------------------------------

@then("the seed spec contains exactly 1 job definition")
def seed_spec_has_one_job(ctx: dict) -> None:
    # JOB_SPEC is a single dict — one job.
    assert isinstance(ctx["job_spec"], dict)
    assert ctx["job_spec"].get("title"), "JOB_SPEC must have a non-empty title"


@then("the seed spec contains exactly 3 candidate definitions")
def seed_spec_has_three_candidates(ctx: dict) -> None:
    specs = ctx["candidate_specs"]
    assert len(specs) == 3, f"Expected 3 candidates; got {len(specs)}"


@then("the job spec has a non-empty title")
def job_spec_has_title(ctx: dict) -> None:
    assert ctx["job_spec"]["title"].strip(), "Job title must not be blank"


@then("the job spec must_haves include a years_experience criterion")
def job_spec_has_years_experience(ctx: dict) -> None:
    must_haves = ctx["job_spec"]["must_haves"]
    types = [v["type"] for v in must_haves.values()]
    assert "years_experience" in types, (
        f"Expected 'years_experience' criterion; found types: {types}"
    )


@then("the job spec must_haves include at least one keyword_presence criterion")
def job_spec_has_keyword_presence(ctx: dict) -> None:
    must_haves = ctx["job_spec"]["must_haves"]
    types = [v["type"] for v in must_haves.values()]
    assert "keyword_presence" in types, (
        f"Expected at least one 'keyword_presence' criterion; found: {types}"
    )


# ---------------------------------------------------------------------------
# Gate outcome steps (no DB)
# ---------------------------------------------------------------------------

@when('the hard gate evaluates candidate "{email}"')
def hard_gate_evaluates_candidate(ctx: dict, email: str) -> None:
    evaluator = HardGateEvaluator()
    spec = CANDIDATES_BY_EMAIL[email]
    ctx["gate_evaluation"] = evaluator.evaluate(
        must_haves=JOB_SPEC["must_haves"],
        resume_parsed=spec["resume_parsed"],
    )
    ctx["evaluated_email"] = email


@then('the gate outcome is "{expected}"')
def assert_gate_outcome(ctx: dict, expected: str) -> None:
    actual = ctx["gate_evaluation"].outcome
    expected_enum = GateOutcome(expected)
    assert actual == expected_enum, (
        f"Expected gate outcome '{expected}' for {ctx.get('evaluated_email')}; "
        f"got '{actual.value}'. Criterion results: "
        + ", ".join(
            f"{r.name}={r.outcome.value}({r.evidence})"
            for r in ctx["gate_evaluation"].criterion_results
        )
    )


@then('the years_experience criterion outcome is "{expected}"')
def assert_years_experience_criterion(ctx: dict, expected: str) -> None:
    evaluation = ctx["gate_evaluation"]
    result = next(
        (r for r in evaluation.criterion_results if r.name == "min_experience"),
        None,
    )
    assert result is not None, (
        "No 'min_experience' criterion found in gate evaluation results. "
        f"Found: {[r.name for r in evaluation.criterion_results]}"
    )
    expected_enum = GateOutcome(expected)
    assert result.outcome == expected_enum, (
        f"Expected years_experience outcome '{expected}'; "
        f"got '{result.outcome.value}': {result.evidence}"
    )


# ---------------------------------------------------------------------------
# Mock-database setup steps
# ---------------------------------------------------------------------------

@given("all demo records already exist in the mock database")
def all_records_exist(ctx: dict) -> None:
    ctx["all_exist"] = True


@given("the mock database is empty")
def mock_db_is_empty(ctx: dict) -> None:
    ctx["all_exist"] = False


# ---------------------------------------------------------------------------
# seed_demo execution step
# ---------------------------------------------------------------------------

@when("seed_demo runs against a mock database")
def seed_demo_runs(ctx: dict) -> None:
    _run_seed_demo(ctx)


# ---------------------------------------------------------------------------
# Idempotency assertion steps
# ---------------------------------------------------------------------------

@then('Job.objects.get_or_create was called with title "{expected_title}"')
def assert_job_get_or_create_title(ctx: dict, expected_title: str) -> None:
    mgr = ctx["mock_job_mgr"]
    mgr.get_or_create.assert_called_once()
    call_kwargs = mgr.get_or_create.call_args.kwargs
    assert call_kwargs.get("title") == expected_title, (
        f"Expected get_or_create(title='{expected_title}'); "
        f"got call_kwargs: {call_kwargs}"
    )


@then("no duplicate Job records were created")
def assert_no_duplicate_jobs(ctx: dict) -> None:
    mgr = ctx["mock_job_mgr"]
    # get_or_create should have been called exactly once
    assert mgr.get_or_create.call_count == 1, (
        f"Expected get_or_create called once; called {mgr.get_or_create.call_count} times"
    )


@then("Candidate.objects.get_or_create was called 3 times")
def assert_candidate_get_or_create_three_times(ctx: dict) -> None:
    mgr = ctx["mock_cand_mgr"]
    assert mgr.get_or_create.call_count == 3, (
        f"Expected Candidate.objects.get_or_create called 3 times; "
        f"called {mgr.get_or_create.call_count} times"
    )


@then("each call used the candidate email as the natural key")
def assert_email_used_as_natural_key(ctx: dict) -> None:
    mgr = ctx["mock_cand_mgr"]
    for c in mgr.get_or_create.call_args_list:
        assert "email" in c.kwargs, (
            f"get_or_create must include 'email' as a positional lookup kwarg; "
            f"call was: {c}"
        )
    called_emails = {c.kwargs["email"] for c in mgr.get_or_create.call_args_list}
    expected_emails = {s["email"] for s in CANDIDATE_SPECS}
    assert called_emails == expected_emails, (
        f"Emails used in get_or_create calls don't match spec.\n"
        f"Expected: {expected_emails}\nGot: {called_emails}"
    )


# ---------------------------------------------------------------------------
# Log event assertion steps
# ---------------------------------------------------------------------------

@then("the log reports jobs_created=0")
def log_jobs_created_zero(ctx: dict) -> None:
    event = ctx.get("seed_log_event", {})
    assert event.get("jobs_created") == 0, (
        f"Expected jobs_created=0; got: {event}"
    )


@then("the log reports candidates_created=0")
def log_candidates_created_zero(ctx: dict) -> None:
    event = ctx.get("seed_log_event", {})
    assert event.get("candidates_created") == 0, (
        f"Expected candidates_created=0; got: {event}"
    )


@then("the log reports idempotent=true")
def log_idempotent_true(ctx: dict) -> None:
    event = ctx.get("seed_log_event", {})
    assert event.get("idempotent") is True, (
        f"Expected idempotent=True; got: {event}"
    )


@then("the log reports jobs_created=1")
def log_jobs_created_one(ctx: dict) -> None:
    event = ctx.get("seed_log_event", {})
    assert event.get("jobs_created") == 1, (
        f"Expected jobs_created=1; got: {event}"
    )


@then("the log reports candidates_created=3")
def log_candidates_created_three(ctx: dict) -> None:
    event = ctx.get("seed_log_event", {})
    assert event.get("candidates_created") == 3, (
        f"Expected candidates_created=3; got: {event}"
    )


@then("the log reports idempotent=false")
def log_idempotent_false(ctx: dict) -> None:
    event = ctx.get("seed_log_event", {})
    assert event.get("idempotent") is False, (
        f"Expected idempotent=False; got: {event}"
    )


@then('a "demo_seed_completed" log event is emitted')
def assert_demo_seed_completed_event(ctx: dict) -> None:
    event = ctx.get("seed_log_event", {})
    assert event.get("event") == "demo_seed_completed", (
        f"Expected 'demo_seed_completed' log event; got: {event}"
    )
