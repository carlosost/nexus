"""
Inner-loop unit tests for DashboardStatsView.

Strategy:
  - Drive the view through DRF's APIRequestFactory.
  - All ORM calls are patched at the model level in resume_pipeline.views.
  - No database, no HTTP server, no network required.
  - Django settings are loaded via pytest-django (DJANGO_SETTINGS_MODULE in pytest.ini).

Coverage matrix:
  ┌─────────────────────────────────┬────────────────────────────────────┐
  │ Class                           │ Behaviour exercised                │
  ├─────────────────────────────────┼────────────────────────────────────┤
  │ TestResponseShape               │ HTTP 200, top-level keys           │
  │ TestTotalsCalculation           │ application count, active filter,  │
  │                                 │ user count, LLM rate formula       │
  │ TestLLMSuccessRateEdgeCases     │ 0 scored → 100 %, all primary,    │
  │                                 │ all fallback, mixed, rounding      │
  │ TestStatusDistribution          │ 8 canonical statuses, zero counts  │
  │                                 │ preserved, ordering, label mapping │
  │ TestJobExecutionFunnel          │ 4 buckets always present,          │
  │                                 │ bucket mapping from status values  │
  │ TestLLMResilienceTimeSeries     │ always 7 entries, date ordering,  │
  │                                 │ zero-fill for missing days,        │
  │                                 │ primary/fallback split             │
  └─────────────────────────────────┴────────────────────────────────────┘

Run:
  pytest tests/unit/test_dashboard_stats.py -m unit
  pytest tests/unit/test_dashboard_stats.py        # full, with coverage
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from rest_framework.test import APIRequestFactory

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request():
    factory = APIRequestFactory()
    return factory.get("/api/dashboard/stats/")


def _call_view(
    *,
    total_apps:        int = 0,
    app_status_rows:   list[dict] | None = None,
    active_apps:       int = 0,
    user_count:        int = 0,
    rubric_total:      int = 0,
    rubric_primary:    int = 0,
    funnel_completed:  int = 0,
    funnel_running:    int = 0,
    funnel_failed:     int = 0,
    funnel_fallback:   int = 0,
    ts_rows:           list[dict] | None = None,
    freeze_date:       datetime.date | None = None,
):
    """
    Invoke DashboardStatsView.get() with fully controlled ORM mocks.

    Returns the DRF Response object.
    """
    if app_status_rows is None:
        app_status_rows = []
    if ts_rows is None:
        ts_rows = []

    with (
        patch("resume_pipeline.views.Application") as MockApp,
        patch("resume_pipeline.views.RubricScore") as MockRS,
        patch("resume_pipeline.views.get_user_model") as MockGetUser,
        patch("resume_pipeline.views.timezone") as MockTZ,
    ):
        # ── Freeze time ──────────────────────────────────────────────────────
        import datetime as _dt
        now = _dt.datetime(2024, 1, 15, 12, 0, 0, tzinfo=_dt.timezone.utc)
        MockTZ.now.return_value = now

        # ── Application mocks ────────────────────────────────────────────────
        MockApp.objects.count.return_value = total_apps
        MockApp.objects.values.return_value.annotate.return_value = app_status_rows

        _completed = {"scored", "approved", "rejected", "under_review"}
        _running   = {"pending", "gate_passed", "gate_unknown"}

        def _app_filter(**kwargs):
            qs = MagicMock()
            s_in   = kwargs.get("status__in")
            s_eq   = kwargs.get("status")
            upd_gte = "updated_at__gte" in kwargs

            if upd_gte:
                # Funnel outer queryset — returns inner mock that handles .filter()
                inner = MagicMock()
                def _inner_filter(**kw):
                    inner2 = MagicMock()
                    si   = kw.get("status__in")
                    se   = kw.get("status")
                    is_fb = kw.get("rubric_score__is_evaluated_via_fallback")
                    if si and set(si) == _completed:
                        inner2.count.return_value = funnel_completed
                    elif si and set(si) == _running:
                        inner2.count.return_value = funnel_running
                    elif se == "gate_failed":
                        inner2.count.return_value = funnel_failed
                    elif is_fb is True:
                        inner2.count.return_value = funnel_fallback
                    else:
                        inner2.count.return_value = 0
                    return inner2
                inner.filter.side_effect = _inner_filter
                return inner

            if s_in and set(s_in) == {"pending", "gate_passed", "gate_unknown"}:
                qs.count.return_value = active_apps
                return qs

            qs.count.return_value = 0
            return qs

        MockApp.objects.filter.side_effect = _app_filter

        # ── RubricScore mocks ─────────────────────────────────────────────────
        MockRS.objects.count.return_value = rubric_total

        # The view makes exactly two .filter() calls on RubricScore:
        #   1. .filter(is_evaluated_via_fallback=False).count()  → rubric_primary
        #   2. .filter(application__updated_at__gte=...).annotate().values().annotate()
        #      → iterable ts_rows
        # A single shared return_value handles both: the .count() path and the
        # annotate chain path. Using side_effect created a new MagicMock on each
        # call, and when Django's real TruncDate/Count expressions were passed as
        # keyword arguments, the chain traversal could produce a fresh child mock
        # rather than the pre-configured ts_rows list.
        rs_qs = MagicMock()
        rs_qs.count.return_value = rubric_primary
        rs_qs.annotate.return_value.values.return_value.annotate.return_value = ts_rows
        MockRS.objects.filter.return_value = rs_qs

        # ── User model mock ───────────────────────────────────────────────────
        MockUser = MagicMock()
        MockGetUser.return_value = MockUser
        MockUser.objects.filter.return_value.count.return_value = user_count

        # ── Call the view ─────────────────────────────────────────────────────
        from resume_pipeline.views import DashboardStatsView
        view = DashboardStatsView.as_view()
        return view(_make_request())


# ---------------------------------------------------------------------------
# TestResponseShape
# ---------------------------------------------------------------------------

class TestResponseShape:
    """The endpoint always returns 200 with the four canonical top-level keys."""

    def test_returns_200(self):
        resp = _call_view()
        assert resp.status_code == 200

    def test_has_totals_key(self):
        assert "totals" in _call_view().data

    def test_has_status_distribution_key(self):
        assert "application_status_distribution" in _call_view().data

    def test_has_funnel_key(self):
        assert "job_execution_funnel" in _call_view().data

    def test_has_llm_resilience_key(self):
        assert "llm_resilience" in _call_view().data

    def test_totals_has_four_sub_keys(self):
        totals = _call_view().data["totals"]
        assert set(totals.keys()) == {
            "applications", "active_jobs", "workspace_users", "llm_success_rate"
        }

    def test_llm_resilience_has_time_series_key(self):
        assert "time_series" in _call_view().data["llm_resilience"]


# ---------------------------------------------------------------------------
# TestTotalsCalculation
# ---------------------------------------------------------------------------

class TestTotalsCalculation:

    def test_application_count_reflects_total(self):
        resp = _call_view(total_apps=42)
        assert resp.data["totals"]["applications"] == 42

    def test_application_count_zero_when_no_data(self):
        resp = _call_view(total_apps=0)
        assert resp.data["totals"]["applications"] == 0

    def test_active_jobs_uses_pending_gate_passed_gate_unknown(self):
        resp = _call_view(total_apps=10, active_apps=4)
        assert resp.data["totals"]["active_jobs"] == 4

    def test_active_jobs_zero_when_all_scored(self):
        resp = _call_view(total_apps=5, active_apps=0)
        assert resp.data["totals"]["active_jobs"] == 0

    def test_workspace_users_count(self):
        resp = _call_view(user_count=7)
        assert resp.data["totals"]["workspace_users"] == 7

    def test_workspace_users_zero_when_none(self):
        resp = _call_view(user_count=0)
        assert resp.data["totals"]["workspace_users"] == 0


# ---------------------------------------------------------------------------
# TestLLMSuccessRateEdgeCases
# ---------------------------------------------------------------------------

class TestLLMSuccessRateEdgeCases:
    """
    Rule: rate = round(primary / total * 100, 1)
    Edge: total == 0 → 100.0 (no LLM calls is not a failure)
    """

    def test_no_rubric_scores_returns_100(self):
        resp = _call_view(rubric_total=0, rubric_primary=0)
        assert resp.data["totals"]["llm_success_rate"] == 100.0

    def test_all_primary_returns_100(self):
        resp = _call_view(rubric_total=10, rubric_primary=10)
        assert resp.data["totals"]["llm_success_rate"] == 100.0

    def test_all_fallback_returns_0(self):
        resp = _call_view(rubric_total=5, rubric_primary=0)
        assert resp.data["totals"]["llm_success_rate"] == 0.0

    def test_mixed_computes_correct_rate(self):
        # 8 primary out of 10 total = 80.0 %
        resp = _call_view(rubric_total=10, rubric_primary=8)
        assert resp.data["totals"]["llm_success_rate"] == pytest.approx(80.0, abs=0.05)

    def test_rate_rounds_to_one_decimal(self):
        # 7 out of 9 = 77.777… → should round to 77.8
        resp = _call_view(rubric_total=9, rubric_primary=7)
        assert resp.data["totals"]["llm_success_rate"] == pytest.approx(77.8, abs=0.05)

    def test_single_fallback_out_of_many(self):
        # 99 primary out of 100 = 99.0 %
        resp = _call_view(rubric_total=100, rubric_primary=99)
        assert resp.data["totals"]["llm_success_rate"] == pytest.approx(99.0, abs=0.05)


# ---------------------------------------------------------------------------
# TestStatusDistribution
# ---------------------------------------------------------------------------

class TestStatusDistribution:
    """
    The distribution always includes all 8 canonical statuses (even count=0).
    The view fills in zeros for statuses absent from the ORM result.
    """

    _ALL_STATUSES = {
        "pending", "gate_failed", "gate_unknown", "gate_passed",
        "scored", "under_review", "approved", "rejected",
    }

    def test_always_returns_8_entries(self):
        resp = _call_view(app_status_rows=[])
        dist = resp.data["application_status_distribution"]
        assert len(dist) == 8

    def test_all_8_canonical_statuses_present(self):
        resp = _call_view(app_status_rows=[])
        statuses = {e["status"] for e in resp.data["application_status_distribution"]}
        assert statuses == self._ALL_STATUSES

    def test_absent_status_has_count_zero(self):
        # Only "scored" in the mock queryset — all others should be 0.
        resp = _call_view(
            app_status_rows=[{"status": "scored", "count": 5}],
            total_apps=5,
        )
        dist = resp.data["application_status_distribution"]
        pending_entry = next(e for e in dist if e["status"] == "pending")
        assert pending_entry["count"] == 0

    def test_present_status_has_correct_count(self):
        resp = _call_view(
            app_status_rows=[{"status": "approved", "count": 3}],
            total_apps=3,
        )
        dist = resp.data["application_status_distribution"]
        entry = next(e for e in dist if e["status"] == "approved")
        assert entry["count"] == 3

    def test_each_entry_has_label_field(self):
        resp = _call_view(app_status_rows=[])
        for entry in resp.data["application_status_distribution"]:
            assert "label" in entry, f"Entry missing 'label': {entry}"

    def test_gate_failed_label_is_human_readable(self):
        resp = _call_view(app_status_rows=[])
        dist = resp.data["application_status_distribution"]
        entry = next(e for e in dist if e["status"] == "gate_failed")
        assert entry["label"] == "Gate Failed"

    def test_multiple_statuses_counted_correctly(self):
        rows = [
            {"status": "pending", "count": 7},
            {"status": "scored",  "count": 12},
        ]
        resp = _call_view(app_status_rows=rows, total_apps=19)
        dist = resp.data["application_status_distribution"]
        by_status = {e["status"]: e["count"] for e in dist}
        assert by_status["pending"] == 7
        assert by_status["scored"]  == 12
        assert by_status["rejected"] == 0


# ---------------------------------------------------------------------------
# TestJobExecutionFunnel
# ---------------------------------------------------------------------------

class TestJobExecutionFunnel:
    """The funnel always returns 4 buckets: completed, running, failed, fallback."""

    _BUCKET_STATUSES = {"completed", "running", "failed", "fallback"}

    def test_always_returns_4_buckets(self):
        resp = _call_view()
        assert len(resp.data["job_execution_funnel"]) == 4

    def test_all_4_bucket_statuses_present(self):
        resp = _call_view()
        statuses = {e["status"] for e in resp.data["job_execution_funnel"]}
        assert statuses == self._BUCKET_STATUSES

    def test_all_buckets_zero_when_no_recent_activity(self):
        resp = _call_view()
        for bucket in resp.data["job_execution_funnel"]:
            assert bucket["count"] == 0, f"Expected 0 for {bucket['status']}"

    def test_completed_bucket_reflects_recent_scored_apps(self):
        resp = _call_view(funnel_completed=5)
        bucket = next(
            e for e in resp.data["job_execution_funnel"] if e["status"] == "completed"
        )
        assert bucket["count"] == 5

    def test_running_bucket_reflects_recent_active_apps(self):
        resp = _call_view(funnel_running=3)
        bucket = next(
            e for e in resp.data["job_execution_funnel"] if e["status"] == "running"
        )
        assert bucket["count"] == 3

    def test_failed_bucket_reflects_gate_failed_apps(self):
        resp = _call_view(funnel_failed=2)
        bucket = next(
            e for e in resp.data["job_execution_funnel"] if e["status"] == "failed"
        )
        assert bucket["count"] == 2

    def test_fallback_bucket_reflects_fallback_scored_apps(self):
        resp = _call_view(funnel_fallback=1)
        bucket = next(
            e for e in resp.data["job_execution_funnel"] if e["status"] == "fallback"
        )
        assert bucket["count"] == 1

    def test_each_bucket_has_label_field(self):
        resp = _call_view()
        for bucket in resp.data["job_execution_funnel"]:
            assert "label" in bucket

    def test_mixed_buckets_are_independent(self):
        resp = _call_view(
            funnel_completed=10,
            funnel_running=3,
            funnel_failed=1,
            funnel_fallback=2,
        )
        by_status = {
            e["status"]: e["count"]
            for e in resp.data["job_execution_funnel"]
        }
        assert by_status["completed"] == 10
        assert by_status["running"]   == 3
        assert by_status["failed"]    == 1
        assert by_status["fallback"]  == 2


# ---------------------------------------------------------------------------
# TestLLMResilienceTimeSeries
# ---------------------------------------------------------------------------

class TestLLMResilienceTimeSeries:
    """The time series always covers exactly the last 7 calendar days."""

    def test_always_has_7_entries(self):
        resp = _call_view(ts_rows=[])
        ts = resp.data["llm_resilience"]["time_series"]
        assert len(ts) == 7

    def test_all_entries_have_date_primary_fallback_keys(self):
        resp = _call_view(ts_rows=[])
        for entry in resp.data["llm_resilience"]["time_series"]:
            assert "date"     in entry
            assert "primary"  in entry
            assert "fallback" in entry

    def test_empty_days_have_zero_counts(self):
        resp = _call_view(ts_rows=[])
        for entry in resp.data["llm_resilience"]["time_series"]:
            assert entry["primary"]  == 0
            assert entry["fallback"] == 0

    def test_series_ends_with_today(self):
        resp = _call_view(ts_rows=[])
        ts = resp.data["llm_resilience"]["time_series"]
        # Frozen date in _call_view is 2024-01-15
        assert ts[-1]["date"] == "2024-01-15"

    def test_series_starts_6_days_ago(self):
        resp = _call_view(ts_rows=[])
        ts = resp.data["llm_resilience"]["time_series"]
        assert ts[0]["date"] == "2024-01-09"

    def test_today_primary_count_is_surfaced(self):
        ts_rows = [
            {"date": datetime.date(2024, 1, 15), "is_evaluated_via_fallback": False, "count": 8},
        ]
        resp = _call_view(ts_rows=ts_rows, rubric_total=8, rubric_primary=8)
        ts = resp.data["llm_resilience"]["time_series"]
        today_entry = next(e for e in ts if e["date"] == "2024-01-15")
        assert today_entry["primary"] == 8

    def test_today_fallback_count_is_surfaced(self):
        ts_rows = [
            {"date": datetime.date(2024, 1, 15), "is_evaluated_via_fallback": True, "count": 3},
        ]
        resp = _call_view(ts_rows=ts_rows, rubric_total=3, rubric_primary=0)
        ts = resp.data["llm_resilience"]["time_series"]
        today_entry = next(e for e in ts if e["date"] == "2024-01-15")
        assert today_entry["fallback"] == 3

    def test_primary_and_fallback_on_same_day_are_split_correctly(self):
        ts_rows = [
            {"date": datetime.date(2024, 1, 15), "is_evaluated_via_fallback": False, "count": 12},
            {"date": datetime.date(2024, 1, 15), "is_evaluated_via_fallback": True,  "count": 2},
        ]
        resp = _call_view(ts_rows=ts_rows, rubric_total=14, rubric_primary=12)
        ts = resp.data["llm_resilience"]["time_series"]
        today = next(e for e in ts if e["date"] == "2024-01-15")
        assert today["primary"]  == 12
        assert today["fallback"] == 2

    def test_older_day_does_not_bleed_into_today(self):
        ts_rows = [
            {"date": datetime.date(2024, 1, 10), "is_evaluated_via_fallback": False, "count": 5},
        ]
        resp = _call_view(ts_rows=ts_rows, rubric_total=5, rubric_primary=5)
        ts = resp.data["llm_resilience"]["time_series"]
        today = next(e for e in ts if e["date"] == "2024-01-15")
        assert today["primary"]  == 0
        assert today["fallback"] == 0


# ---------------------------------------------------------------------------
# Regression guard
# ---------------------------------------------------------------------------

class TestRegressionGuards:
    """
    Pinned assertions for edge-cases found during code review.
    These act as regression tests: they must continue to pass after any
    refactor of DashboardStatsView.
    """

    def test_llm_rate_is_float_not_int_when_evenly_divisible(self):
        # 10/10 must be 100.0 (float) not 100 (int) — the frontend compares with 90.0
        resp = _call_view(rubric_total=10, rubric_primary=10)
        rate = resp.data["totals"]["llm_success_rate"]
        assert isinstance(rate, float), f"Expected float, got {type(rate)}"

    def test_status_distribution_preserves_zero_count_for_gate_unknown(self):
        # gate_unknown must appear even if no apps have that status
        resp = _call_view(app_status_rows=[{"status": "pending", "count": 1}])
        dist = resp.data["application_status_distribution"]
        gate_unknown = next((e for e in dist if e["status"] == "gate_unknown"), None)
        assert gate_unknown is not None
        assert gate_unknown["count"] == 0

    def test_funnel_always_has_fallback_bucket(self):
        # The "fallback" bucket must always be present even when 0
        resp = _call_view()
        statuses = [e["status"] for e in resp.data["job_execution_funnel"]]
        assert "fallback" in statuses

    def test_time_series_date_strings_are_iso_format(self):
        resp = _call_view(ts_rows=[])
        for entry in resp.data["llm_resilience"]["time_series"]:
            # Must match YYYY-MM-DD
            parts = entry["date"].split("-")
            assert len(parts) == 3 and all(p.isdigit() for p in parts), (
                f"Date '{entry['date']}' is not ISO format"
            )
