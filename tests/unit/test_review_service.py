"""
Inner-loop unit tests for ReviewService.

Tests the business logic layer in isolation — ORM calls are mocked.
No DB, no HTTP, no Django test runner needed.

ReviewService responsibilities:
  1. Apply the status transition corresponding to the decision.
  2. Call audit_logger.log_human_override() for override decisions.
  3. NOT call audit_logger for approve/reject decisions.
  4. Raise ValidationError when an override is submitted without a reason.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_application(status: str = "scored") -> MagicMock:
    app = MagicMock()
    app.id = "app-uuid-001"
    app.status = status
    app.save = MagicMock()
    return app


def _make_review(
    decision: str,
    reason: str = "",
    reviewer_email: str = "r@example.com",
    ai_score: float = 0.82,
    confidence: float = 1.0,
) -> MagicMock:
    review = MagicMock()
    review.decision = decision
    review.override_reason = reason
    review.reviewer_email = reviewer_email
    review.ai_score_at_review = ai_score
    review.confidence_at_review = confidence
    return review


# ---------------------------------------------------------------------------
# 1. Status transitions
# ---------------------------------------------------------------------------

class TestReviewServiceStatusTransitions:

    @pytest.fixture(autouse=True)
    def import_service(self):
        from resume_pipeline.services import ReviewService
        self.service = ReviewService()

    def test_approve_sets_status_to_approved(self):
        app = _make_application()
        review = _make_review("approve")
        self.service.process_review(app, review)
        assert app.status == "approved"

    def test_reject_sets_status_to_rejected(self):
        app = _make_application()
        review = _make_review("reject")
        self.service.process_review(app, review)
        assert app.status == "rejected"

    def test_override_pass_sets_status_to_approved(self):
        app = _make_application()
        review = _make_review("override_pass", reason="Good fit despite missing cert")
        self.service.process_review(app, review)
        assert app.status == "approved"

    def test_override_fail_sets_status_to_rejected(self):
        app = _make_application()
        review = _make_review("override_fail", reason="Misrepresented experience")
        self.service.process_review(app, review)
        assert app.status == "rejected"

    def test_application_save_called_after_status_update(self):
        app = _make_application()
        review = _make_review("approve")
        self.service.process_review(app, review)
        app.save.assert_called_once()

    def test_save_called_with_update_fields(self):
        """Save must use update_fields to avoid overwriting concurrent changes."""
        app = _make_application()
        review = _make_review("approve")
        self.service.process_review(app, review)
        call_kwargs = app.save.call_args
        assert "update_fields" in call_kwargs.kwargs

    def test_status_updated_before_save(self):
        """Ensure status is set before save() is called (not after)."""
        recorded = []

        app = _make_application()
        original_save = app.save

        def _capturing_save(**kwargs):
            recorded.append(app.status)

        app.save = _capturing_save
        review = _make_review("approve")
        self.service.process_review(app, review)

        assert recorded == ["approved"]


# ---------------------------------------------------------------------------
# 2. Override guard — reason required
# ---------------------------------------------------------------------------

class TestReviewServiceOverrideGuard:

    @pytest.fixture(autouse=True)
    def import_service(self):
        from resume_pipeline.services import ReviewService
        self.service = ReviewService()

    def test_override_pass_without_reason_raises(self):
        from rest_framework.exceptions import ValidationError
        app = _make_application()
        review = _make_review("override_pass", reason="")
        with pytest.raises(ValidationError) as exc_info:
            self.service.process_review(app, review)
        assert "override_reason" in str(exc_info.value.detail)

    def test_override_fail_without_reason_raises(self):
        from rest_framework.exceptions import ValidationError
        app = _make_application()
        review = _make_review("override_fail", reason="")
        with pytest.raises(ValidationError):
            self.service.process_review(app, review)

    def test_override_with_whitespace_reason_raises(self):
        from rest_framework.exceptions import ValidationError
        app = _make_application()
        review = _make_review("override_pass", reason="   ")
        with pytest.raises(ValidationError):
            self.service.process_review(app, review)

    def test_approve_without_reason_does_not_raise(self):
        app = _make_application()
        review = _make_review("approve", reason="")
        self.service.process_review(app, review)  # Must not raise

    def test_reject_without_reason_does_not_raise(self):
        app = _make_application()
        review = _make_review("reject", reason="")
        self.service.process_review(app, review)  # Must not raise

    def test_app_not_saved_when_override_guard_raises(self):
        """If validation fails, the application must NOT be mutated."""
        from rest_framework.exceptions import ValidationError
        app = _make_application()
        review = _make_review("override_pass", reason="")
        with pytest.raises(ValidationError):
            self.service.process_review(app, review)
        app.save.assert_not_called()
        assert app.status == "scored"  # unchanged


# ---------------------------------------------------------------------------
# 3. Audit logging
# ---------------------------------------------------------------------------

class TestReviewServiceAuditLogging:

    @pytest.fixture(autouse=True)
    def import_service(self):
        from resume_pipeline.services import ReviewService
        self.service = ReviewService()

    def test_override_pass_logs_human_override(self, caplog):
        app = _make_application()
        review = _make_review(
            "override_pass",
            reason="Strong portfolio",
            reviewer_email="senior@example.com",
            ai_score=0.82,
            confidence=1.0,
        )
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            self.service.process_review(app, review)

        logged = [r.getMessage() for r in caplog.records]
        override_logs = [m for m in logged if '"event": "human_override"' in m]
        assert len(override_logs) == 1

    def test_override_fail_logs_human_override(self, caplog):
        app = _make_application()
        review = _make_review("override_fail", reason="Did not meet bar")
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            self.service.process_review(app, review)

        logged = [r.getMessage() for r in caplog.records]
        assert any('"event": "human_override"' in m for m in logged)

    def test_approve_does_not_log_human_override(self, caplog):
        app = _make_application()
        review = _make_review("approve")
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            self.service.process_review(app, review)

        logged = [r.getMessage() for r in caplog.records]
        assert not any('"event": "human_override"' in m for m in logged)

    def test_reject_does_not_log_human_override(self, caplog):
        app = _make_application()
        review = _make_review("reject")
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            self.service.process_review(app, review)

        logged = [r.getMessage() for r in caplog.records]
        assert not any('"event": "human_override"' in m for m in logged)

    def test_override_audit_log_contains_reviewer_email(self, caplog):
        import json
        app = _make_application()
        review = _make_review(
            "override_pass",
            reason="Good candidate",
            reviewer_email="alice@company.com",
        )
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            self.service.process_review(app, review)

        logged = [r.getMessage() for r in caplog.records]
        override_logs = [m for m in logged if '"event": "human_override"' in m]
        assert override_logs
        payload = json.loads(override_logs[0])
        assert payload["reviewer_email"] == "alice@company.com"

    def test_override_audit_log_contains_decision(self, caplog):
        import json
        app = _make_application()
        review = _make_review("override_pass", reason="Good candidate")
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            self.service.process_review(app, review)

        logged = [r.getMessage() for r in caplog.records]
        override_logs = [m for m in logged if '"event": "human_override"' in m]
        payload = json.loads(override_logs[0])
        assert payload["decision"] == "override_pass"

    def test_override_audit_log_contains_reason(self, caplog):
        import json
        app = _make_application()
        reason = "Portfolio demonstrates senior-level impact"
        review = _make_review("override_pass", reason=reason)
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            self.service.process_review(app, review)

        logged = [r.getMessage() for r in caplog.records]
        override_logs = [m for m in logged if '"event": "human_override"' in m]
        payload = json.loads(override_logs[0])
        assert payload["reason"] == reason

    def test_override_audit_log_contains_ai_score(self, caplog):
        import json
        app = _make_application()
        review = _make_review("override_pass", reason="Good", ai_score=0.91)
        with caplog.at_level(logging.INFO, logger="pipeline.audit"):
            self.service.process_review(app, review)

        logged = [r.getMessage() for r in caplog.records]
        override_logs = [m for m in logged if '"event": "human_override"' in m]
        payload = json.loads(override_logs[0])
        assert payload["ai_score_at_review"] == pytest.approx(0.91)
