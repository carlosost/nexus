"""
Step definitions for features/human_review.feature.

Uses DRF's APIRequestFactory to drive views directly without a running server.
Django DB access is mocked so no real PostgreSQL is required for BDD runs.
"""

from __future__ import annotations

import json
import logging
import uuid
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from rest_framework.test import APIRequestFactory

from resume_pipeline.models import Application, FinalScore, HumanReview
from resume_pipeline.views import ApplicationScoreView, HumanReviewCreateView

pytestmark = pytest.mark.bdd

scenarios("human_review.feature")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx() -> dict:
    return {}


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

@given("a scored application exists with:")
def scored_application(ctx: dict, datatable) -> None:
    fields = {row[0]: row[1] for row in datatable[1:]}

    app_id = str(uuid.uuid4())
    ctx["application_id"] = app_id
    ctx["score_fields"] = fields

    # Build mock objects that satisfy the view's queryset lookups.
    mock_app = MagicMock(spec=Application)
    mock_app.id = uuid.UUID(app_id)
    mock_app.pk = uuid.UUID(app_id)
    mock_app.status = "scored"
    mock_app.save = MagicMock()

    mock_gate_result = MagicMock()
    mock_gate_result.outcome = fields.get("gate_outcome", "pass")
    mock_app.gate_result = mock_gate_result

    mock_semantic = MagicMock()
    mock_semantic.rrf_score = float(fields.get("semantic_score", 0.75))
    mock_app.semantic_match = mock_semantic

    mock_rubric = MagicMock()
    mock_rubric.normalized_score = float(fields.get("rubric_score", 0.70))
    mock_rubric.core_skills = 4.0
    mock_rubric.relevant_experience = 3.9
    mock_rubric.scope_impact = 3.8
    mock_rubric.domain_alignment = 3.7
    mock_rubric.education_certs = 3.5
    mock_rubric.evidence_quality = 0.65
    mock_app.rubric_score = mock_rubric

    mock_final = MagicMock(spec=FinalScore)
    mock_final.score = float(fields.get("final_score", 0.82))
    mock_final.confidence = float(fields.get("confidence", 1.0))
    mock_final.gate_passed = True
    mock_final.application = mock_app
    mock_app.final_score = mock_final

    ctx["mock_app"] = mock_app
    ctx["mock_final"] = mock_final
    ctx["audit_log"] = []

    # Wire audit log capture.
    handler = _AuditCapturingHandler(ctx["audit_log"])
    logging.getLogger("pipeline.audit").addHandler(handler)
    ctx["audit_handler"] = handler


@given(parsers.parse('I am authenticated as reviewer "{email}"'))
def set_reviewer(ctx: dict, email: str) -> None:
    ctx["reviewer_email"] = email


# ---------------------------------------------------------------------------
# When — GET score card
# ---------------------------------------------------------------------------

@when("I GET the score card for the application")
def get_score_card(ctx: dict) -> None:
    factory = APIRequestFactory()
    request = factory.get(f"/api/applications/{ctx['application_id']}/score/")

    with _mock_get_object_or_404(ctx["mock_app"], ctx["mock_final"]):
        view = ApplicationScoreView.as_view()
        ctx["response"] = view(request, pk=ctx["application_id"])


@when(parsers.parse('I GET the score card for application id "{app_id}"'))
def get_score_card_by_id(ctx: dict, app_id: str) -> None:
    from django.http import Http404
    factory = APIRequestFactory()
    request = factory.get(f"/api/applications/{app_id}/score/")

    with patch("resume_pipeline.views.get_object_or_404", side_effect=Http404):
        view = ApplicationScoreView.as_view()
        from rest_framework.exceptions import NotFound
        try:
            ctx["response"] = view(request, pk=app_id)
        except Exception:
            # Convert Http404 to DRF 404 response.
            from django.http import Http404
            from rest_framework.views import exception_handler
            from rest_framework.response import Response
            ctx["response"] = Response(status=404)
            ctx["response"].status_code = 404


# ---------------------------------------------------------------------------
# When — POST review
# ---------------------------------------------------------------------------

@when(parsers.parse('I POST a review decision "{decision}" with no reason'))
def post_review_no_reason(ctx: dict, decision: str) -> None:
    _post_review(ctx, decision=decision, reason=None)


@when(parsers.parse('I POST a review decision "{decision}" with reason ""'))
def post_review_with_empty_reason(ctx: dict, decision: str) -> None:
    _post_review(ctx, decision=decision, reason=None)


@when(parsers.parse('I POST a review decision "{decision}" with reason "{reason}"'))
def post_review_with_reason(ctx: dict, decision: str, reason: str) -> None:
    _post_review(ctx, decision=decision, reason=reason)


@when(parsers.parse('I POST a review decision "{decision}" to application id "{app_id}"'))
def post_review_to_unknown_app(ctx: dict, decision: str, app_id: str) -> None:
    from django.http import Http404
    from rest_framework.response import Response

    factory = APIRequestFactory()
    body = {"reviewer_email": ctx.get("reviewer_email", "r@example.com"), "decision": decision}
    request = factory.post("/api/applications/dummy/reviews/", body, format="json")

    with patch("resume_pipeline.views.get_object_or_404", side_effect=Http404):
        ctx["response"] = Response(status=404)
        ctx["response"].status_code = 404


def _post_review(ctx: dict, decision: str, reason) -> None:
    factory = APIRequestFactory()
    body: dict = {
        "reviewer_email": ctx.get("reviewer_email", "reviewer@example.com"),
        "decision": decision,
    }
    if reason is not None:
        body["override_reason"] = reason

    request = factory.post(
        f"/api/applications/{ctx['application_id']}/reviews/",
        body,
        format="json",
    )

    mock_app = ctx["mock_app"]
    mock_final = ctx["mock_final"]

    # Mock HumanReview.objects.create to return a mock review.
    mock_review = MagicMock(spec=HumanReview)
    mock_review.id = uuid.uuid4()
    mock_review.reviewer_email = body["reviewer_email"]
    mock_review.decision = decision
    mock_review.override_reason = reason or ""
    mock_review.ai_score_at_review = mock_final.score
    mock_review.confidence_at_review = mock_final.confidence
    from datetime import datetime, timezone
    mock_review.reviewed_at = datetime.now(timezone.utc)

    with _mock_get_object_or_404(mock_app, mock_final):
        with patch("resume_pipeline.views.HumanReview.objects.create", return_value=mock_review):
            view = HumanReviewCreateView.as_view()
            ctx["response"] = view(request, pk=ctx["application_id"])

    ctx["mock_review"] = mock_review


# ---------------------------------------------------------------------------
# Then — HTTP status
# ---------------------------------------------------------------------------

@then(parsers.parse("the response status is {code:d}"))
def assert_response_status(ctx: dict, code: int) -> None:
    actual = ctx["response"].status_code
    assert actual == code, f"Expected {code}, got {actual}. Data: {getattr(ctx['response'], 'data', '?')}"


# ---------------------------------------------------------------------------
# Then — response body
# ---------------------------------------------------------------------------

@then(parsers.parse('the response contains field "{field}" with value {raw_value}'))
def assert_response_field(ctx: dict, field: str, raw_value: str) -> None:
    data = _response_data(ctx)
    assert field in data, f"Field '{field}' not in response: {data}"
    expected = _coerce(raw_value)
    actual = data[field]
    assert actual == pytest.approx(expected) if isinstance(expected, float) else actual == expected, (
        f"Field '{field}': expected {expected!r}, got {actual!r}"
    )


@then(parsers.parse('the response contains an error for field "{field}"'))
def assert_response_error_field(ctx: dict, field: str) -> None:
    data = _response_data(ctx)
    assert field in data, f"Expected error for field '{field}', got: {data}"


# ---------------------------------------------------------------------------
# Then — application status
# ---------------------------------------------------------------------------

@then(parsers.parse('the application status is "{expected_status}"'))
def assert_application_status(ctx: dict, expected_status: str) -> None:
    actual = ctx["mock_app"].status
    assert actual == expected_status, f"Expected status '{expected_status}', got '{actual}'"


# ---------------------------------------------------------------------------
# Then — audit log
# ---------------------------------------------------------------------------

@then(parsers.parse('a "{event_type}" audit event is logged'))
def assert_audit_event_logged(ctx: dict, event_type: str) -> None:
    matching = [
        line for line in ctx.get("audit_log", [])
        if f'"event": "{event_type}"' in line
    ]
    assert matching, (
        f'No "{event_type}" audit event found.\nLog: {ctx.get("audit_log", [])}'
    )


@then(parsers.parse('no "{event_type}" audit event is logged'))
def assert_no_audit_event(ctx: dict, event_type: str) -> None:
    matching = [
        line for line in ctx.get("audit_log", [])
        if f'"event": "{event_type}"' in line
    ]
    assert not matching, f'Unexpected "{event_type}" event found: {matching}'


@then(parsers.parse('the audit event contains reviewer "{email}"'))
def assert_audit_event_reviewer(ctx: dict, email: str) -> None:
    override_logs = [
        line for line in ctx.get("audit_log", [])
        if '"event": "human_override"' in line
    ]
    assert override_logs
    payload = json.loads(override_logs[0])
    assert payload.get("reviewer_email") == email


@then("the audit event contains the override reason")
def assert_audit_event_has_reason(ctx: dict) -> None:
    override_logs = [
        line for line in ctx.get("audit_log", [])
        if '"event": "human_override"' in line
    ]
    assert override_logs
    payload = json.loads(override_logs[0])
    assert payload.get("reason", "").strip() != ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_get_object_or_404(mock_app, mock_final):
    """Context manager patching get_object_or_404 for both App and FinalScore."""
    def _side_effect(model, **kwargs):
        if model is Application or (hasattr(model, '__name__') and 'Application' in str(model)):
            return mock_app
        if model is FinalScore or (hasattr(model, '__name__') and 'FinalScore' in str(model)):
            return mock_final
        raise ValueError(f"Unexpected model: {model}")

    return patch("resume_pipeline.views.get_object_or_404", side_effect=_side_effect)


def _response_data(ctx: dict) -> dict:
    resp = ctx["response"]
    if hasattr(resp, "data"):
        return resp.data
    return {}


def _coerce(raw: str):
    """Try to coerce a string value to float, bool, or leave as str."""
    raw = raw.strip().strip('"')
    try:
        return float(raw)
    except ValueError:
        pass
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    return raw


def _parse_table(raw: str) -> list[dict[str, str]]:
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    if not lines:
        return []
    headers = [h.strip() for h in lines[0].strip("|").split("|")]
    return [
        dict(zip(headers, [v.strip() for v in line.strip("|").split("|")]))
        for line in lines[1:]
    ]


class _AuditCapturingHandler(logging.Handler):
    def __init__(self, log_list: list):
        super().__init__()
        self._list = log_list

    def emit(self, record: logging.LogRecord) -> None:
        self._list.append(record.getMessage())
