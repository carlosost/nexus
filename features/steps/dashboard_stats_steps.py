"""
Step definitions for features/dashboard_stats.feature.

Strategy: all ORM calls are mocked via unittest.mock so no real PostgreSQL
is required. The view is exercised through DRF's APIRequestFactory, exactly
as human_review_steps.py does for HumanReviewCreateView.

Context keys:
  ctx["response"]            — DRF Response from the view
  ctx["now"]                 — frozen datetime used for cutoff calculations
  ctx["app_counts"]          — dict[status, count] of mocked Application records
  ctx["rubric_primary"]      — count of primary-backend RubricScore records
  ctx["rubric_fallback"]     — count of fallback-backend RubricScore records
  ctx["app_updated_recent"]  — list of Application mock objects updated < 24 h ago
  ctx["app_updated_old"]     — list of Application mock objects updated > 24 h ago
  ctx["today_primary"]       — today's primary RubricScore count
  ctx["today_fallback"]      — today's fallback RubricScore count
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from rest_framework.test import APIRequestFactory

pytestmark = pytest.mark.bdd

scenarios("dashboard_stats.feature")


# ---------------------------------------------------------------------------
# Shared state fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx() -> dict:
    return {
        "app_counts":         {},   # {status: count}
        "rubric_primary":     0,
        "rubric_fallback":    0,
        "app_updated_recent": [],   # mocks with updated_at < 24h ago
        "app_updated_old":    [],   # mocks with updated_at > 24h ago
        "today_primary":      0,
        "today_fallback":     0,
        "user_count":         0,
    }


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

@given("the DashboardStatsView is initialized")
def init_view(ctx: dict) -> None:
    """No-op — the view is stateless; initialization is implicit."""


# ---------------------------------------------------------------------------
# Given — data setup
# ---------------------------------------------------------------------------

@given("there are no Application records")
def no_applications(ctx: dict) -> None:
    ctx["app_counts"] = {}


@given("there are no RubricScore records")
def no_rubric_scores(ctx: dict) -> None:
    ctx["rubric_primary"] = 0
    ctx["rubric_fallback"] = 0
    ctx["today_primary"] = 0
    ctx["today_fallback"] = 0


@given("there are no User records")
def no_users(ctx: dict) -> None:
    ctx["user_count"] = 0


@given(parsers.parse("{count:d} Application records exist with status \"{status}\""))
def app_records_with_status(ctx: dict, count: int, status: str) -> None:
    ctx["app_counts"][status] = ctx["app_counts"].get(status, 0) + count


@given(parsers.parse("{count:d} Application record exists with status \"{status}\""))
def one_app_record_with_status(ctx: dict, count: int, status: str) -> None:
    ctx["app_counts"][status] = ctx["app_counts"].get(status, 0) + count


@given(parsers.parse(
    "{count:d} Application records were updated more than 24 hours ago with status \"{status}\""
))
def old_apps_with_status(ctx: dict, count: int, status: str) -> None:
    ctx["app_counts"][status] = ctx["app_counts"].get(status, 0) + count
    for _ in range(count):
        ctx["app_updated_old"].append(status)


@given(parsers.parse(
    "{count:d} Application records were updated less than 24 hours ago with status \"{status}\""
))
def recent_apps_with_status(ctx: dict, count: int, status: str) -> None:
    ctx["app_counts"][status] = ctx["app_counts"].get(status, 0) + count
    for _ in range(count):
        ctx["app_updated_recent"].append(status)


@given(parsers.parse(
    "{count:d} RubricScore records exist with is_evaluated_via_fallback=False"
))
def rubric_primary_records(ctx: dict, count: int) -> None:
    ctx["rubric_primary"] = count


@given(parsers.parse(
    "{count:d} RubricScore records exist with is_evaluated_via_fallback=True"
))
def rubric_fallback_records(ctx: dict, count: int) -> None:
    ctx["rubric_fallback"] = count


@given(parsers.parse(
    "{count:d} RubricScore records were created today with is_evaluated_via_fallback=False"
))
def today_primary_records(ctx: dict, count: int) -> None:
    ctx["rubric_primary"] = ctx.get("rubric_primary", 0) + count
    ctx["today_primary"] = count


@given(parsers.parse(
    "{count:d} RubricScore records were created today with is_evaluated_via_fallback=True"
))
def today_fallback_records(ctx: dict, count: int) -> None:
    ctx["rubric_fallback"] = ctx.get("rubric_fallback", 0) + count
    ctx["today_fallback"] = count


# ---------------------------------------------------------------------------
# When — call the view
# ---------------------------------------------------------------------------

@when("I GET /api/dashboard/stats/")
def get_dashboard_stats(ctx: dict) -> None:
    """
    Drive DashboardStatsView.get() through the DRF test factory,
    with all ORM calls mocked using context data set up in Given steps.
    """
    from django.utils import timezone
    now = timezone.now()
    ctx["now"] = now

    # Build the aggregated Application querysets from ctx["app_counts"]
    app_counts = ctx["app_counts"]
    total_apps = sum(app_counts.values())

    active_statuses = {"pending", "gate_passed", "gate_unknown"}
    active_apps = sum(v for k, v in app_counts.items() if k in active_statuses)

    # Status distribution — one dict per status
    status_distribution_rows = [
        {"status": s, "count": c}
        for s, c in app_counts.items()
        if c > 0
    ]

    # Recent application querysets (for funnel)
    recent_statuses = ctx["app_updated_recent"]

    completed_statuses = {"scored", "approved", "rejected", "under_review"}
    running_statuses   = {"pending", "gate_passed", "gate_unknown"}

    recent_completed = sum(1 for s in recent_statuses if s in completed_statuses)
    recent_running   = sum(1 for s in recent_statuses if s in running_statuses)
    recent_failed    = sum(1 for s in recent_statuses if s == "gate_failed")

    # RubricScore data
    primary_count  = ctx.get("rubric_primary", 0)
    fallback_count = ctx.get("rubric_fallback", 0)
    total_scored   = primary_count + fallback_count

    # Today's time-series point
    today_str = str(now.date())
    today_primary  = ctx.get("today_primary", 0)
    today_fallback = ctx.get("today_fallback", 0)

    # ── Patch ORM calls inside the view ────────────────────────────────────
    # We patch at the model level to intercept every queryset the view builds.
    with (
        patch("resume_pipeline.views.Application") as MockApp,
        patch("resume_pipeline.views.RubricScore") as MockRS,
        patch("resume_pipeline.views.get_user_model") as MockGetUser,
    ):
        # --- Application.objects.count() ---
        MockApp.objects.count.return_value = total_apps

        # --- Application.objects.filter(...).count() for active_jobs ---
        def _app_filter_count(**kwargs):
            status_list = kwargs.get("status__in", [])
            if set(status_list) == active_statuses:
                return active_apps
            return 0

        def _app_filter(**kwargs):
            m = MagicMock()
            status_in = kwargs.get("status__in")
            status_eq = kwargs.get("status")
            updated_gte = "updated_at__gte" in kwargs

            if updated_gte:
                # Funnel queryset — calls .filter(status=...).count() or
                # .filter(rubric_score__is_evaluated_via_fallback=True).count()
                inner = MagicMock()
                def _inner_filter(**inner_kwargs):
                    inner2 = MagicMock()
                    s_in   = inner_kwargs.get("status__in")
                    s_eq   = inner_kwargs.get("status")
                    is_fb  = inner_kwargs.get("rubric_score__is_evaluated_via_fallback")
                    if s_in and set(s_in) == completed_statuses:
                        inner2.count.return_value = recent_completed
                    elif s_in and set(s_in) == running_statuses:
                        inner2.count.return_value = recent_running
                    elif s_eq == "gate_failed":
                        inner2.count.return_value = recent_failed
                    elif is_fb is True:
                        # fallback funnel bucket
                        inner2.count.return_value = 0
                    else:
                        inner2.count.return_value = 0
                    return inner2
                inner.filter.side_effect = _inner_filter
                return inner

            if status_in:
                qs = MagicMock()
                qs.count.return_value = sum(
                    v for k, v in app_counts.items() if k in set(status_in)
                )
                return qs

            qs = MagicMock()
            qs.count.return_value = app_counts.get(status_eq, 0)
            return qs

        MockApp.objects.filter.side_effect = _app_filter

        # --- Application.objects.values("status").annotate(count=...) ---
        MockApp.objects.values.return_value.annotate.return_value = status_distribution_rows

        # --- RubricScore.objects.count() ---
        MockRS.objects.count.return_value = total_scored

        # --- RubricScore filter mocks ---
        # The view makes two .filter() calls on RubricScore:
        #   1. .filter(is_evaluated_via_fallback=False).count()  → primary_count
        #   2. .filter(application__updated_at__gte=...).annotate().values().annotate()
        #      → iterable ts_rows
        # Using side_effect + filter.return_value together is broken: when side_effect
        # is active, MagicMock ignores return_value entirely and calls the side_effect
        # function instead. The time-series chain set on filter.return_value was dead
        # code. Fix: use a single shared return_value mock that handles both uses.
        ts_rows = []
        if today_primary > 0:
            ts_rows.append({
                "date":                      now.date(),
                "is_evaluated_via_fallback": False,
                "count":                     today_primary,
            })
        if today_fallback > 0:
            ts_rows.append({
                "date":                      now.date(),
                "is_evaluated_via_fallback": True,
                "count":                     today_fallback,
            })

        rs_qs = MagicMock()
        rs_qs.count.return_value = primary_count
        rs_qs.annotate.return_value.values.return_value.annotate.return_value = ts_rows
        MockRS.objects.filter.return_value = rs_qs

        # --- User model ---
        MockUser = MagicMock()
        MockGetUser.return_value = MockUser
        MockUser.objects.filter.return_value.count.return_value = ctx.get("user_count", 0)

        # --- Execute the view ---
        factory = APIRequestFactory()
        request = factory.get("/api/dashboard/stats/")

        from resume_pipeline.views import DashboardStatsView
        view = DashboardStatsView.as_view()
        ctx["response"] = view(request)


# ---------------------------------------------------------------------------
# Then — response status
# ---------------------------------------------------------------------------

@then(parsers.parse("the response status is {code:d}"))
def assert_status(ctx: dict, code: int) -> None:
    assert ctx["response"].status_code == code, (
        f"Expected {code}, got {ctx['response'].status_code}"
    )


# ---------------------------------------------------------------------------
# Then — response shape
# ---------------------------------------------------------------------------

@then(parsers.parse("the response body has key \"{key}\""))
def assert_response_has_key(ctx: dict, key: str) -> None:
    data = ctx["response"].data
    assert key in data, f"Key '{key}' not in response: {list(data.keys())}"


# ---------------------------------------------------------------------------
# Then — totals
# ---------------------------------------------------------------------------

@then(parsers.parse("totals.applications is {expected:d}"))
def assert_totals_applications(ctx: dict, expected: int) -> None:
    actual = ctx["response"].data["totals"]["applications"]
    assert actual == expected, f"totals.applications: expected {expected}, got {actual}"


@then(parsers.parse("totals.active_jobs is {expected:d}"))
def assert_totals_active_jobs(ctx: dict, expected: int) -> None:
    actual = ctx["response"].data["totals"]["active_jobs"]
    assert actual == expected, f"totals.active_jobs: expected {expected}, got {actual}"


@then(parsers.parse("totals.workspace_users is {expected:d}"))
def assert_totals_users(ctx: dict, expected: int) -> None:
    actual = ctx["response"].data["totals"]["workspace_users"]
    assert actual == expected, f"totals.workspace_users: expected {expected}, got {actual}"


@then(parsers.parse("totals.llm_success_rate is {expected:f}"))
def assert_totals_llm_rate(ctx: dict, expected: float) -> None:
    actual = ctx["response"].data["totals"]["llm_success_rate"]
    assert abs(actual - expected) < 0.05, (
        f"totals.llm_success_rate: expected {expected}, got {actual}"
    )


# ---------------------------------------------------------------------------
# Then — status distribution
# ---------------------------------------------------------------------------

@then(parsers.parse("application_status_distribution contains exactly {expected:d} entries"))
def assert_status_dist_count(ctx: dict, expected: int) -> None:
    dist = ctx["response"].data["application_status_distribution"]
    assert len(dist) == expected, (
        f"application_status_distribution: expected {expected} entries, got {len(dist)}"
    )


@then(parsers.parse(
    "application_status_distribution includes status \"{status}\" with count {count:d}"
))
def assert_status_dist_entry(ctx: dict, status: str, count: int) -> None:
    dist = ctx["response"].data["application_status_distribution"]
    matching = [e for e in dist if e["status"] == status]
    assert matching, (
        f"Status '{status}' not found in distribution: {[e['status'] for e in dist]}"
    )
    assert matching[0]["count"] == count, (
        f"Status '{status}' count: expected {count}, got {matching[0]['count']}"
    )


# ---------------------------------------------------------------------------
# Then — job execution funnel
# ---------------------------------------------------------------------------

@then(parsers.parse("job_execution_funnel contains exactly {expected:d} entries"))
def assert_funnel_count(ctx: dict, expected: int) -> None:
    funnel = ctx["response"].data["job_execution_funnel"]
    assert len(funnel) == expected, (
        f"job_execution_funnel: expected {expected} entries, got {len(funnel)}"
    )


@then(parsers.parse("job_execution_funnel \"{bucket}\" bucket has count {count:d}"))
def assert_funnel_bucket(ctx: dict, bucket: str, count: int) -> None:
    funnel = ctx["response"].data["job_execution_funnel"]
    matching = [e for e in funnel if e["status"] == bucket]
    assert matching, (
        f"Funnel bucket '{bucket}' not found: {[e['status'] for e in funnel]}"
    )
    assert matching[0]["count"] == count, (
        f"Funnel bucket '{bucket}': expected {count}, got {matching[0]['count']}"
    )


# ---------------------------------------------------------------------------
# Then — LLM resilience
# ---------------------------------------------------------------------------

@then(parsers.parse("llm_resilience.time_series has exactly {expected:d} entries"))
def assert_ts_length(ctx: dict, expected: int) -> None:
    ts = ctx["response"].data["llm_resilience"]["time_series"]
    assert len(ts) == expected, (
        f"llm_resilience.time_series: expected {expected} entries, got {len(ts)}"
    )


@then("every entry in llm_resilience.time_series has primary=0 and fallback=0")
def assert_ts_all_zero(ctx: dict) -> None:
    ts = ctx["response"].data["llm_resilience"]["time_series"]
    for entry in ts:
        assert entry["primary"] == 0 and entry["fallback"] == 0, (
            f"Non-zero entry found: {entry}"
        )


@then(parsers.parse("today's llm_resilience entry has primary={p:d} and fallback={f:d}"))
def assert_ts_today(ctx: dict, p: int, f: int) -> None:
    ts   = ctx["response"].data["llm_resilience"]["time_series"]
    today = str(ctx["now"].date())
    matching = [e for e in ts if e["date"] == today]
    assert matching, f"No entry for today ({today}) in time series: {[e['date'] for e in ts]}"
    entry = matching[0]
    assert entry["primary"] == p, f"Today primary: expected {p}, got {entry['primary']}"
    assert entry["fallback"] == f, f"Today fallback: expected {f}, got {entry['fallback']}"
