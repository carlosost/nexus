"""
M0.6 — Inner TDD loop: unit tests for seed data and seed_demo logic.

What this tests (no DB required):
  1. Seed data spec structure (JOB_SPEC, CANDIDATE_SPECS, CANDIDATES_BY_EMAIL)
  2. Gate outcomes per candidate via HardGateEvaluator (pure-Python, no Django)
  3. Idempotency pattern — get_or_create called with correct natural unique keys
  4. Purge guard blocks when IS_PRODUCTION=True

Run:
    pytest tests/unit/test_seed_data.py -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest

from resume_pipeline.management.commands._seed_data import (
    CANDIDATES_BY_EMAIL,
    CANDIDATE_SPECS,
    JOB_SPEC,
)
from resume_pipeline.pipeline.hard_gate import GateOutcome, HardGateEvaluator


# ---------------------------------------------------------------------------
# 1. Seed data spec structure
# ---------------------------------------------------------------------------


class TestJobSpec:
    def test_job_spec_has_required_keys(self):
        assert "title" in JOB_SPEC
        assert "description" in JOB_SPEC
        assert "requirements_raw" in JOB_SPEC
        assert "must_haves" in JOB_SPEC

    def test_job_title_is_non_empty_string(self):
        assert isinstance(JOB_SPEC["title"], str)
        assert JOB_SPEC["title"].strip()

    def test_must_haves_has_three_criteria(self):
        assert len(JOB_SPEC["must_haves"]) == 3

    def test_must_haves_contains_expected_criteria(self):
        must_haves = JOB_SPEC["must_haves"]
        assert "min_experience" in must_haves
        assert "python_required" in must_haves
        assert "django_required" in must_haves

    def test_min_experience_criterion_type(self):
        crit = JOB_SPEC["must_haves"]["min_experience"]
        assert crit["type"] == "years_experience"
        assert crit["minimum_years"] >= 5

    def test_python_required_criterion_type(self):
        crit = JOB_SPEC["must_haves"]["python_required"]
        assert crit["type"] == "keyword_presence"
        assert "Python" in crit["keywords"]

    def test_django_required_criterion_type(self):
        crit = JOB_SPEC["must_haves"]["django_required"]
        assert crit["type"] == "keyword_presence"
        assert "Django" in crit["keywords"]

    def test_requirements_raw_has_minimum_experience_years(self):
        req = JOB_SPEC["requirements_raw"]
        assert req["minimum_experience_years"] >= 5


class TestCandidateSpecs:
    def test_exactly_three_candidates(self):
        assert len(CANDIDATE_SPECS) == 3

    def test_all_candidates_have_required_keys(self):
        required = {"name", "email", "resume_raw", "resume_parsed"}
        for spec in CANDIDATE_SPECS:
            assert required.issubset(spec.keys()), (
                f"Candidate {spec.get('email')} missing keys: "
                f"{required - spec.keys()}"
            )

    def test_emails_are_unique(self):
        emails = [s["email"] for s in CANDIDATE_SPECS]
        assert len(emails) == len(set(emails))

    def test_candidates_by_email_has_all_candidates(self):
        assert len(CANDIDATES_BY_EMAIL) == 3
        for spec in CANDIDATE_SPECS:
            assert spec["email"] in CANDIDATES_BY_EMAIL

    def test_candidates_by_email_values_match_specs(self):
        for spec in CANDIDATE_SPECS:
            assert CANDIDATES_BY_EMAIL[spec["email"]] is spec

    def test_alice_has_total_experience_years(self):
        alice = CANDIDATES_BY_EMAIL["alice@demo.example.com"]
        assert "total_experience_years" in alice["resume_parsed"]
        assert alice["resume_parsed"]["total_experience_years"] >= 5

    def test_bob_missing_total_experience_years(self):
        """Bob's missing field is the key design decision for UNKNOWN gate outcome."""
        bob = CANDIDATES_BY_EMAIL["bob@demo.example.com"]
        assert "total_experience_years" not in bob["resume_parsed"], (
            "Bob must NOT have total_experience_years — this drives his UNKNOWN gate outcome."
        )

    def test_carol_has_insufficient_experience(self):
        carol = CANDIDATES_BY_EMAIL["carol@demo.example.com"]
        assert carol["resume_parsed"]["total_experience_years"] < 5

    def test_carol_missing_django(self):
        carol = CANDIDATES_BY_EMAIL["carol@demo.example.com"]
        parsed = carol["resume_parsed"]
        combined = " ".join([
            str(parsed.get("skills", "")),
            str(parsed.get("experience", "")),
        ]).lower()
        assert "django" not in combined, (
            "Carol must NOT have Django — this drives her FAIL gate outcome."
        )


# ---------------------------------------------------------------------------
# 2. Gate outcomes via HardGateEvaluator (pure Python, no DB)
# ---------------------------------------------------------------------------


class TestGateOutcomes:
    """
    Run HardGateEvaluator against each candidate's resume_parsed and the
    job's must_haves. Validates that seed data is wired correctly to produce
    the outcomes expected by the BDD scenarios.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        self.evaluator = HardGateEvaluator()
        self.must_haves = JOB_SPEC["must_haves"]

    def _evaluate(self, email: str) -> GateOutcome:
        spec = CANDIDATES_BY_EMAIL[email]
        evaluation = self.evaluator.evaluate(
            must_haves=self.must_haves,
            resume_parsed=spec["resume_parsed"],
        )
        return evaluation.outcome

    def test_alice_gate_outcome_is_pass(self):
        assert self._evaluate("alice@demo.example.com") == GateOutcome.PASS

    def test_bob_gate_outcome_is_unknown(self):
        assert self._evaluate("bob@demo.example.com") == GateOutcome.UNKNOWN

    def test_carol_gate_outcome_is_fail(self):
        assert self._evaluate("carol@demo.example.com") == GateOutcome.FAIL

    def test_alice_individual_criteria_all_pass(self):
        spec = CANDIDATES_BY_EMAIL["alice@demo.example.com"]
        evaluation = self.evaluator.evaluate(
            must_haves=self.must_haves,
            resume_parsed=spec["resume_parsed"],
        )
        for result in evaluation.criterion_results:
            assert result.outcome == GateOutcome.PASS, (
                f"Expected PASS on criterion '{result.name}' for Alice; "
                f"got {result.outcome}: {result.evidence}"
            )

    def test_bob_experience_criterion_is_unknown(self):
        spec = CANDIDATES_BY_EMAIL["bob@demo.example.com"]
        evaluation = self.evaluator.evaluate(
            must_haves=self.must_haves,
            resume_parsed=spec["resume_parsed"],
        )
        exp_result = next(
            r for r in evaluation.criterion_results if r.name == "min_experience"
        )
        assert exp_result.outcome == GateOutcome.UNKNOWN

    def test_bob_python_and_django_criteria_pass(self):
        spec = CANDIDATES_BY_EMAIL["bob@demo.example.com"]
        evaluation = self.evaluator.evaluate(
            must_haves=self.must_haves,
            resume_parsed=spec["resume_parsed"],
        )
        keyword_results = {
            r.name: r.outcome
            for r in evaluation.criterion_results
            if r.name in ("python_required", "django_required")
        }
        assert keyword_results["python_required"] == GateOutcome.PASS
        assert keyword_results["django_required"] == GateOutcome.PASS

    def test_carol_experience_criterion_fails(self):
        spec = CANDIDATES_BY_EMAIL["carol@demo.example.com"]
        evaluation = self.evaluator.evaluate(
            must_haves=self.must_haves,
            resume_parsed=spec["resume_parsed"],
        )
        exp_result = next(
            r for r in evaluation.criterion_results if r.name == "min_experience"
        )
        assert exp_result.outcome == GateOutcome.FAIL

    def test_carol_django_criterion_fails(self):
        spec = CANDIDATES_BY_EMAIL["carol@demo.example.com"]
        evaluation = self.evaluator.evaluate(
            must_haves=self.must_haves,
            resume_parsed=spec["resume_parsed"],
        )
        django_result = next(
            r for r in evaluation.criterion_results if r.name == "django_required"
        )
        assert django_result.outcome == GateOutcome.FAIL


# ---------------------------------------------------------------------------
# 3. Idempotency pattern — get_or_create called with natural unique keys
# ---------------------------------------------------------------------------


class TestSeedDemoIdempotency:
    """
    Tests the seed_demo.Command._seed() method by mocking all ORM calls.
    Validates that:
      - Job.objects.get_or_create uses title as the natural unique key
      - Candidate.objects.get_or_create uses email as the natural unique key
      - Application.objects.get_or_create uses (job, candidate) as the key
      - Counts are reported correctly on first run and second run
    """

    def _make_mock_manager(self, created: bool, instance=None):
        """Returns a mock manager where get_or_create returns (instance, created)."""
        obj = instance or MagicMock()
        manager = MagicMock()
        manager.get_or_create.return_value = (obj, created)
        return manager, obj

    def _run_seed(self, job_created: bool, cand_created: bool):
        """Run _seed() with controlled get_or_create return values."""
        # Late import so Django isn't required at module collect time
        from resume_pipeline.management.commands.seed_demo import Command

        job_manager, job_obj = self._make_mock_manager(created=job_created)
        cand_manager, cand_obj = self._make_mock_manager(created=cand_created)
        app_manager, _ = self._make_mock_manager(created=False)

        with (
            patch("resume_pipeline.management.commands.seed_demo.Job") as MockJob,
            patch(
                "resume_pipeline.management.commands.seed_demo.Candidate"
            ) as MockCandidate,
            patch(
                "resume_pipeline.management.commands.seed_demo.Application"
            ) as MockApp,
        ):
            MockJob.objects = job_manager
            MockCandidate.objects = cand_manager
            MockApp.objects = app_manager

            cmd = Command()
            cmd.stdout = MagicMock()
            cmd.style = MagicMock()
            return cmd._seed()

    def test_first_run_returns_one_job_three_candidates(self):
        jobs_created, candidates_created = self._run_seed(
            job_created=True, cand_created=True
        )
        assert jobs_created == 1
        assert candidates_created == 3

    def test_second_run_returns_zeros(self):
        jobs_created, candidates_created = self._run_seed(
            job_created=False, cand_created=False
        )
        assert jobs_created == 0
        assert candidates_created == 0

    def test_job_get_or_create_uses_title_as_natural_key(self):
        from resume_pipeline.management.commands.seed_demo import Command

        job_manager, job_obj = self._make_mock_manager(created=True)
        cand_manager, _ = self._make_mock_manager(created=False)
        app_manager, _ = self._make_mock_manager(created=False)

        with (
            patch("resume_pipeline.management.commands.seed_demo.Job") as MockJob,
            patch("resume_pipeline.management.commands.seed_demo.Candidate") as MockCand,
            patch("resume_pipeline.management.commands.seed_demo.Application") as MockApp,
        ):
            MockJob.objects = job_manager
            MockCand.objects = cand_manager
            MockApp.objects = app_manager

            cmd = Command()
            cmd.stdout = MagicMock()
            cmd.style = MagicMock()
            cmd._seed()

        # title must be a positional lookup key, not inside defaults
        call_kwargs = job_manager.get_or_create.call_args
        assert "title" in call_kwargs.kwargs or (
            len(call_kwargs.args) > 0 and "title" in call_kwargs.args[0]
        ), f"Expected 'title' in get_or_create lookup; got: {call_kwargs}"

        # title value must match JOB_SPEC
        all_kwargs = {**call_kwargs.kwargs}
        assert all_kwargs.get("title") == JOB_SPEC["title"]

    def test_candidate_get_or_create_uses_email_as_natural_key(self):
        from resume_pipeline.management.commands.seed_demo import Command

        job_manager, _ = self._make_mock_manager(created=False)
        cand_manager, _ = self._make_mock_manager(created=False)
        app_manager, _ = self._make_mock_manager(created=False)

        with (
            patch("resume_pipeline.management.commands.seed_demo.Job") as MockJob,
            patch("resume_pipeline.management.commands.seed_demo.Candidate") as MockCand,
            patch("resume_pipeline.management.commands.seed_demo.Application") as MockApp,
        ):
            MockJob.objects = job_manager
            MockCand.objects = cand_manager
            MockApp.objects = app_manager

            cmd = Command()
            cmd.stdout = MagicMock()
            cmd.style = MagicMock()
            cmd._seed()

        # Should have been called once per candidate
        assert cand_manager.get_or_create.call_count == len(CANDIDATE_SPECS)

        # Each call must use 'email' as the lookup key
        for c in cand_manager.get_or_create.call_args_list:
            assert "email" in c.kwargs, (
                f"get_or_create must use 'email' as lookup; got: {c}"
            )

        # Emails must match spec
        called_emails = {c.kwargs["email"] for c in cand_manager.get_or_create.call_args_list}
        expected_emails = {s["email"] for s in CANDIDATE_SPECS}
        assert called_emails == expected_emails

    def test_idempotent_flag_true_on_second_run(self):
        from resume_pipeline.management.commands.seed_demo import Command
        import io

        job_manager, _ = self._make_mock_manager(created=False)
        cand_manager, _ = self._make_mock_manager(created=False)
        app_manager, _ = self._make_mock_manager(created=False)

        with (
            patch("resume_pipeline.management.commands.seed_demo.Job") as MockJob,
            patch("resume_pipeline.management.commands.seed_demo.Candidate") as MockCand,
            patch("resume_pipeline.management.commands.seed_demo.Application") as MockApp,
            patch("resume_pipeline.management.commands.seed_demo.logger") as mock_logger,
        ):
            MockJob.objects = job_manager
            MockCand.objects = cand_manager
            MockApp.objects = app_manager

            cmd = Command()
            cmd.stdout = MagicMock()
            cmd.style = MagicMock()
            cmd.handle(purge=False)

        # Grab the JSON string logged at INFO level
        logged = mock_logger.info.call_args[0][0]
        event = json.loads(logged)

        assert event["event"] == "demo_seed_completed"
        assert event["jobs_created"] == 0
        assert event["candidates_created"] == 0
        assert event["idempotent"] is True


# ---------------------------------------------------------------------------
# 4. Purge guard
# ---------------------------------------------------------------------------


class TestPurgeGuard:
    def test_purge_raises_in_production(self):
        from django.core.management.base import CommandError
        from resume_pipeline.management.commands.seed_demo import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.style = MagicMock()

        with patch(
            "resume_pipeline.management.commands.seed_demo.settings"
        ) as mock_settings:
            mock_settings.IS_PRODUCTION = True
            with pytest.raises(CommandError, match="not allowed in production"):
                cmd._purge()

    def test_purge_allowed_when_not_production(self):
        from resume_pipeline.management.commands.seed_demo import Command

        with (
            patch(
                "resume_pipeline.management.commands.seed_demo.settings"
            ) as mock_settings,
            patch(
                "resume_pipeline.management.commands.seed_demo.Application"
            ) as MockApp,
            patch(
                "resume_pipeline.management.commands.seed_demo.Candidate"
            ) as MockCand,
            patch(
                "resume_pipeline.management.commands.seed_demo.Job"
            ) as MockJob,
        ):
            mock_settings.IS_PRODUCTION = False
            MockApp.objects = MagicMock()
            MockCand.objects = MagicMock()
            MockJob.objects = MagicMock()

            cmd = Command()
            cmd.stdout = MagicMock()
            cmd.style = MagicMock()
            # Should not raise
            cmd._purge()

        MockApp.objects.filter.assert_called_once()
        MockCand.objects.filter.assert_called_once()
        MockJob.objects.filter.assert_called_once()
