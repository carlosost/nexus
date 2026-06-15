# features/dashboard_stats.feature
#
# Outer-loop BDD specification for GET /api/dashboard/stats/.
#
# Business rules encoded here:
#   1. The endpoint returns HTTP 200 with the canonical payload shape.
#   2. totals.applications is the count of all Application records.
#   3. totals.active_jobs counts applications with status pending/gate_passed/gate_unknown.
#   4. totals.llm_success_rate is 100.0 when no RubricScore records exist.
#   5. totals.llm_success_rate is computed as (primary / total) * 100, rounded to 1 dp.
#   6. application_status_distribution includes all 8 canonical statuses, even with count 0.
#   7. job_execution_funnel buckets reflect only applications updated in the last 24 hours.
#   8. llm_resilience.time_series covers exactly 7 calendar days ending today.
#   9. Days with no LLM activity appear in the series with primary=0 and fallback=0.
#  10. is_evaluated_via_fallback=True records feed the "fallback" funnel bucket and resilience series.

Feature: Dashboard Statistics API
  As an operator
  I want a single aggregation endpoint for the Dashboard
  So that the frontend can display telemetry without issuing multiple requests

  Background:
    Given the DashboardStatsView is initialized

  # ---------------------------------------------------------------------------
  # Response shape
  # ---------------------------------------------------------------------------

  Scenario: Stats endpoint returns 200 with the correct top-level keys
    When I GET /api/dashboard/stats/
    Then the response status is 200
    And the response body has key "totals"
    And the response body has key "application_status_distribution"
    And the response body has key "job_execution_funnel"
    And the response body has key "llm_resilience"

  # ---------------------------------------------------------------------------
  # Totals — empty database
  # ---------------------------------------------------------------------------

  Scenario: All totals are zero when no data exists
    Given there are no Application records
    And there are no RubricScore records
    And there are no User records
    When I GET /api/dashboard/stats/
    Then totals.applications is 0
    And totals.active_jobs is 0
    And totals.workspace_users is 0
    And totals.llm_success_rate is 100.0

  # ---------------------------------------------------------------------------
  # Totals — with data
  # ---------------------------------------------------------------------------

  Scenario: Application count reflects all status values
    Given 3 Application records exist with status "scored"
    And 2 Application records exist with status "rejected"
    When I GET /api/dashboard/stats/
    Then totals.applications is 5

  Scenario: Active-in-pipeline count covers pending, gate_passed, and gate_unknown only
    Given 2 Application records exist with status "pending"
    And 1 Application record exists with status "gate_passed"
    And 1 Application record exists with status "gate_unknown"
    And 3 Application records exist with status "scored"
    When I GET /api/dashboard/stats/
    Then totals.active_jobs is 4

  Scenario: LLM success rate is computed from RubricScore.is_evaluated_via_fallback
    Given 8 RubricScore records exist with is_evaluated_via_fallback=False
    And 2 RubricScore records exist with is_evaluated_via_fallback=True
    When I GET /api/dashboard/stats/
    Then totals.llm_success_rate is 80.0

  Scenario: LLM success rate is 100.0 when no scores exist yet
    Given there are no RubricScore records
    When I GET /api/dashboard/stats/
    Then totals.llm_success_rate is 100.0

  # ---------------------------------------------------------------------------
  # Status distribution
  # ---------------------------------------------------------------------------

  Scenario: Status distribution includes all 8 canonical statuses
    Given there are no Application records
    When I GET /api/dashboard/stats/
    Then application_status_distribution contains exactly 8 entries
    And application_status_distribution includes status "pending" with count 0
    And application_status_distribution includes status "gate_failed" with count 0
    And application_status_distribution includes status "approved" with count 0

  Scenario: Status distribution counts match application records
    Given 4 Application records exist with status "pending"
    And 1 Application record exists with status "approved"
    When I GET /api/dashboard/stats/
    Then application_status_distribution includes status "pending" with count 4
    And application_status_distribution includes status "approved" with count 1

  # ---------------------------------------------------------------------------
  # Job execution funnel — last 24 hours
  # ---------------------------------------------------------------------------

  Scenario: Funnel only counts applications updated in the last 24 hours
    Given 3 Application records were updated more than 24 hours ago with status "scored"
    And 2 Application records were updated less than 24 hours ago with status "scored"
    When I GET /api/dashboard/stats/
    Then job_execution_funnel "completed" bucket has count 2

  Scenario: Funnel "failed" bucket counts gate_failed applications from last 24 hours
    Given 2 Application records were updated less than 24 hours ago with status "gate_failed"
    When I GET /api/dashboard/stats/
    Then job_execution_funnel "failed" bucket has count 2

  Scenario: Funnel returns 4 buckets always
    Given there are no Application records
    When I GET /api/dashboard/stats/
    Then job_execution_funnel contains exactly 4 entries
    And job_execution_funnel "completed" bucket has count 0
    And job_execution_funnel "running" bucket has count 0
    And job_execution_funnel "failed" bucket has count 0
    And job_execution_funnel "fallback" bucket has count 0

  # ---------------------------------------------------------------------------
  # LLM resilience — 7-day time series
  # ---------------------------------------------------------------------------

  Scenario: Resilience time series always covers exactly 7 days
    Given there are no RubricScore records
    When I GET /api/dashboard/stats/
    Then llm_resilience.time_series has exactly 7 entries

  Scenario: Days with no LLM activity have primary=0 and fallback=0
    Given there are no RubricScore records
    When I GET /api/dashboard/stats/
    Then every entry in llm_resilience.time_series has primary=0 and fallback=0

  Scenario: Primary and fallback counts are split by is_evaluated_via_fallback
    Given 5 RubricScore records were created today with is_evaluated_via_fallback=False
    And 2 RubricScore records were created today with is_evaluated_via_fallback=True
    When I GET /api/dashboard/stats/
    Then today's llm_resilience entry has primary=5 and fallback=2
