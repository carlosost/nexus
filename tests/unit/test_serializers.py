"""
Inner-loop unit tests for DRF serializers.

Focus: HumanReviewSerializer's override_reason enforcement.
These tests are pure validation logic — no DB, no HTTP.

Run: pytest tests/unit/test_serializers.py -m unit

Django must be configured before DRF serializers can be imported.
The pytest-django plugin handles this via DJANGO_SETTINGS_MODULE in pytest.ini.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# HumanReviewSerializer — override_reason validation
# ---------------------------------------------------------------------------

class TestHumanReviewSerializerValidation:
    """
    Rule: override_pass and override_fail REQUIRE a non-empty, non-blank reason.
         approve and reject do NOT require a reason.
    """

    @pytest.fixture(autouse=True)
    def import_serializer(self):
        from resume_pipeline.serializers import HumanReviewSerializer
        self.Serializer = HumanReviewSerializer

    def _valid(self, data: dict) -> bool:
        s = self.Serializer(data=data)
        return s.is_valid()

    def _errors(self, data: dict) -> dict:
        s = self.Serializer(data=data)
        s.is_valid()
        return s.errors

    # ── approve / reject — reason optional ──────────────────────────────────

    def test_approve_without_reason_is_valid(self):
        assert self._valid({
            "reviewer_email": "r@example.com",
            "decision": "approve",
        })

    def test_reject_without_reason_is_valid(self):
        assert self._valid({
            "reviewer_email": "r@example.com",
            "decision": "reject",
        })

    def test_approve_with_reason_is_valid(self):
        assert self._valid({
            "reviewer_email": "r@example.com",
            "decision": "approve",
            "override_reason": "Good fit",
        })

    # ── override_pass — reason required ─────────────────────────────────────

    def test_override_pass_without_reason_is_invalid(self):
        assert not self._valid({
            "reviewer_email": "r@example.com",
            "decision": "override_pass",
        })

    def test_override_pass_without_reason_error_is_on_override_reason_field(self):
        errors = self._errors({
            "reviewer_email": "r@example.com",
            "decision": "override_pass",
        })
        assert "override_reason" in errors

    def test_override_pass_with_empty_string_reason_is_invalid(self):
        assert not self._valid({
            "reviewer_email": "r@example.com",
            "decision": "override_pass",
            "override_reason": "",
        })

    def test_override_pass_with_whitespace_only_reason_is_invalid(self):
        assert not self._valid({
            "reviewer_email": "r@example.com",
            "decision": "override_pass",
            "override_reason": "   ",
        })

    def test_override_pass_with_valid_reason_is_valid(self):
        assert self._valid({
            "reviewer_email": "r@example.com",
            "decision": "override_pass",
            "override_reason": "Strong portfolio compensates for missing cert",
        })

    # ── override_fail — reason required ─────────────────────────────────────

    def test_override_fail_without_reason_is_invalid(self):
        assert not self._valid({
            "reviewer_email": "r@example.com",
            "decision": "override_fail",
        })

    def test_override_fail_with_empty_reason_is_invalid(self):
        assert not self._valid({
            "reviewer_email": "r@example.com",
            "decision": "override_fail",
            "override_reason": "",
        })

    def test_override_fail_with_whitespace_reason_is_invalid(self):
        assert not self._valid({
            "reviewer_email": "r@example.com",
            "decision": "override_fail",
            "override_reason": "\t\n  ",
        })

    def test_override_fail_with_valid_reason_is_valid(self):
        assert self._valid({
            "reviewer_email": "r@example.com",
            "decision": "override_fail",
            "override_reason": "Candidate misrepresented seniority level",
        })

    # ── email field validation ───────────────────────────────────────────────

    def test_invalid_email_produces_error(self):
        errors = self._errors({
            "reviewer_email": "not-an-email",
            "decision": "approve",
        })
        assert "reviewer_email" in errors

    def test_missing_email_produces_error(self):
        errors = self._errors({"decision": "approve"})
        assert "reviewer_email" in errors

    # ── invalid decision value ───────────────────────────────────────────────

    def test_unknown_decision_produces_error(self):
        errors = self._errors({
            "reviewer_email": "r@example.com",
            "decision": "do_nothing",
        })
        assert "decision" in errors

    def test_missing_decision_produces_error(self):
        errors = self._errors({"reviewer_email": "r@example.com"})
        assert "decision" in errors

    # ── validated_data contains ai_score_at_review default ──────────────────

    def test_approved_validated_data_has_override_reason_as_empty_string(self):
        s = self.Serializer(data={
            "reviewer_email": "r@example.com",
            "decision": "approve",
        })
        assert s.is_valid()
        assert s.validated_data.get("override_reason", "") == ""


# ---------------------------------------------------------------------------
# ApplicationScoreSerializer — read-only output structure
# ---------------------------------------------------------------------------

class TestApplicationScoreSerializer:

    @pytest.fixture(autouse=True)
    def import_serializer(self):
        from resume_pipeline.serializers import ApplicationScoreSerializer
        self.Serializer = ApplicationScoreSerializer

    def test_serializer_includes_final_score(self):
        fields = self.Serializer().fields
        assert "final_score" in fields

    def test_serializer_includes_confidence(self):
        fields = self.Serializer().fields
        assert "confidence" in fields

    def test_serializer_includes_gate_outcome(self):
        fields = self.Serializer().fields
        assert "gate_outcome" in fields

    def test_serializer_includes_semantic_score(self):
        fields = self.Serializer().fields
        assert "semantic_score" in fields

    def test_serializer_includes_rubric_score(self):
        fields = self.Serializer().fields
        assert "rubric_score" in fields

    def test_serializer_includes_rubric_breakdown(self):
        fields = self.Serializer().fields
        assert "rubric_breakdown" in fields

    def test_all_score_fields_are_read_only(self):
        """Score card must never be writable via the API."""
        s = self.Serializer()
        for field_name in ("final_score", "confidence", "semantic_score", "rubric_score"):
            field = s.fields[field_name]
            assert field.read_only, f"Field '{field_name}' should be read_only"
