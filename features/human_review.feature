# features/human_review.feature
#
# Outer-loop BDD specification for the Human-in-the-Loop API (Milestone 5).
#
# Business rules encoded here:
#   1. GET /api/applications/{id}/score/ returns the full AI score card.
#   2. POST /api/applications/{id}/reviews/ creates a human review decision.
#   3. Decisions "override_pass" and "override_fail" REQUIRE a non-empty reason.
#   4. Posting an override without a reason returns HTTP 400.
#   5. Posting an override with a blank or whitespace-only reason returns HTTP 400.
#   6. Decisions "approve" and "reject" do NOT require a reason.
#   7. After any decision, the Application.status transitions correctly.
#   8. Every override decision is written to the audit log.
#   9. Non-override decisions (approve/reject) are NOT logged as overrides.
#  10. Posting to a non-existent application returns HTTP 404.

Feature: Human-in-the-Loop Review API
  As a human reviewer
  I want to view an application's AI score and submit a decision
  So that override decisions are enforced, logged, and traceable

  Background:
    Given a scored application exists with:
      | field         | value                    |
      | final_score   | 0.82                     |
      | confidence    | 1.0                      |
      | gate_outcome  | pass                     |
      | semantic_score| 0.85                     |
      | rubric_score  | 0.78                     |
    And I am authenticated as reviewer "reviewer@example.com"

  # ---------------------------------------------------------------------------
  # Score card — GET
  # ---------------------------------------------------------------------------

  Scenario: Reviewer can retrieve the AI score card
    When I GET the score card for the application
    Then the response status is 200
    And the response contains field "final_score" with value 0.82
    And the response contains field "confidence" with value 1.0
    And the response contains field "gate_outcome" with value "pass"
    And the response contains field "semantic_score" with value 0.85
    And the response contains field "rubric_score" with value 0.78

  Scenario: Score card for unknown application returns 404
    When I GET the score card for application id "00000000-0000-0000-0000-000000000000"
    Then the response status is 404

  # ---------------------------------------------------------------------------
  # Approve / Reject — no reason required
  # ---------------------------------------------------------------------------

  Scenario: Reviewer approves without providing a reason
    When I POST a review decision "approve" with no reason
    Then the response status is 201
    And the application status is "approved"

  Scenario: Reviewer rejects without providing a reason
    When I POST a review decision "reject" with no reason
    Then the response status is 201
    And the application status is "rejected"

  Scenario: Approve decision does not emit an override audit event
    When I POST a review decision "approve" with no reason
    Then the response status is 201
    And no "human_override" audit event is logged

  # ---------------------------------------------------------------------------
  # Override — reason is mandatory
  # ---------------------------------------------------------------------------

  Scenario: Reviewer overrides to pass with a valid reason
    When I POST a review decision "override_pass" with reason "Strong portfolio compensates for missing cert"
    Then the response status is 201
    And the application status is "approved"

  Scenario: Reviewer overrides to fail with a valid reason
    When I POST a review decision "override_fail" with reason "Candidate misrepresented seniority level"
    Then the response status is 201
    And the application status is "rejected"

  Scenario: Override to pass without a reason is rejected
    When I POST a review decision "override_pass" with no reason
    Then the response status is 400
    And the response contains an error for field "override_reason"

  Scenario: Override to fail without a reason is rejected
    When I POST a review decision "override_fail" with no reason
    Then the response status is 400
    And the response contains an error for field "override_reason"

  Scenario: Override with a blank reason is rejected
    When I POST a review decision "override_pass" with reason "   "
    Then the response status is 400
    And the response contains an error for field "override_reason"

  Scenario: Override with an empty string reason is rejected
    When I POST a review decision "override_pass" with reason ""
    Then the response status is 400
    And the response contains an error for field "override_reason"

  # ---------------------------------------------------------------------------
  # Audit logging for overrides
  # ---------------------------------------------------------------------------

  Scenario: Override to pass emits a human_override audit event
    When I POST a review decision "override_pass" with reason "Exceptional references"
    Then the response status is 201
    And a "human_override" audit event is logged
    And the audit event contains reviewer "reviewer@example.com"
    And the audit event contains the override reason

  Scenario: Override to fail emits a human_override audit event
    When I POST a review decision "override_fail" with reason "Reference check failed"
    Then the response status is 201
    And a "human_override" audit event is logged

  # ---------------------------------------------------------------------------
  # Status transitions
  # ---------------------------------------------------------------------------

  Scenario Outline: Application status transitions correctly after decision
    When I POST a review decision "<decision>" with reason "<reason>"
    Then the response status is 201
    And the application status is "<expected_status>"

    Examples:
      | decision      | reason                          | expected_status |
      | approve       |                                 | approved        |
      | reject        |                                 | rejected        |
      | override_pass | Strong technical assessment     | approved        |
      | override_fail | Role requirements not met       | rejected        |

  # ---------------------------------------------------------------------------
  # Review for unknown application
  # ---------------------------------------------------------------------------

  Scenario: POST review to unknown application returns 404
    When I POST a review decision "approve" to application id "00000000-0000-0000-0000-000000000000"
    Then the response status is 404
