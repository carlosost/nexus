Feature: Human-in-the-Loop Review UI — M6
  As a recruiter reviewer
  I want a clear, interactive score card with an override panel
  So that I can make informed decisions and submit them with an audit trail

  Background:
    Given the application "app-001" has been scored with:
      | field          | value |
      | final_score    | 0.82  |
      | confidence     | 1.0   |
      | gate_outcome   | pass  |
      | gate_passed    | true  |
      | semantic_score | 0.79  |
      | rubric_score   | 0.84  |
    And the rubric breakdown contains:
      | criterion           | score |
      | core_skills         | 4.5   |
      | relevant_experience | 4.2   |
      | scope_impact        | 4.0   |
      | domain_alignment    | 3.8   |
      | education_certs     | 3.5   |

  # ---------------------------------------------------------------------------
  # Score Card display
  # ---------------------------------------------------------------------------

  Scenario: Score card displays the final score as a percentage
    When I open the review page for application "app-001"
    Then I see a score card
    And the score card shows "82%" as the final score
    And the score card shows a "PASS" gate badge

  Scenario: Score card shows confidence and sub-scores
    When I open the review page for application "app-001"
    Then the score card shows confidence "100%"
    And the score card shows semantic score "79%"
    And the score card shows rubric score "84%"

  Scenario: Score card shows FAIL badge when gate failed
    Given the application has gate_outcome "fail" and final_score 0.0
    When I open the review page for application "app-001"
    Then the score card shows a "FAIL" gate badge
    And the score card shows "0%" as the final score

  # ---------------------------------------------------------------------------
  # Rubric Breakdown
  # ---------------------------------------------------------------------------

  Scenario: Rubric breakdown renders all five criteria
    When I open the review page for application "app-001"
    Then I see the rubric breakdown panel
    And the rubric breakdown shows "core_skills" with score 4.5
    And the rubric breakdown shows "relevant_experience" with score 4.2
    And the rubric breakdown shows "scope_impact" with score 4.0
    And the rubric breakdown shows "domain_alignment" with score 3.8
    And the rubric breakdown shows "education_certs" with score 3.5

  Scenario: Rubric breakdown shows score bars proportional to max
    When I open the review page for application "app-001"
    Then each criterion bar width reflects its score out of 5

  # ---------------------------------------------------------------------------
  # Override Panel — submit guard
  # ---------------------------------------------------------------------------

  Scenario: Approve decision submits without a reason
    When I open the review page for application "app-001"
    And I select decision "approve"
    Then the reason textarea is not visible
    And the submit button is enabled

  Scenario: Reject decision submits without a reason
    When I open the review page for application "app-001"
    And I select decision "reject"
    Then the reason textarea is not visible
    And the submit button is enabled

  Scenario: Override-pass decision requires a reason before submit
    When I open the review page for application "app-001"
    And I select decision "override_pass"
    Then the reason textarea is visible
    And the submit button is disabled

  Scenario: Override-fail decision requires a reason before submit
    When I open the review page for application "app-001"
    And I select decision "override_fail"
    Then the reason textarea is visible
    And the submit button is disabled

  Scenario: Submit becomes enabled once override reason is filled
    When I open the review page for application "app-001"
    And I select decision "override_pass"
    And I enter reason "Strong portfolio despite missing cert"
    Then the submit button is enabled

  Scenario: Clearing the reason disables the submit button again
    When I open the review page for application "app-001"
    And I select decision "override_pass"
    And I enter reason "Strong portfolio"
    And I clear the reason field
    Then the submit button is disabled

  # ---------------------------------------------------------------------------
  # Successful submission
  # ---------------------------------------------------------------------------

  Scenario: Submitting approve posts to the API and shows confirmation
    When I open the review page for application "app-001"
    And I enter reviewer email "alice@company.com"
    And I select decision "approve"
    And I click submit
    Then the API receives a POST to "/api/applications/app-001/reviews/"
    And the request body contains decision "approve"
    And a success confirmation is displayed

  Scenario: Submitting override_pass posts reason to the API
    When I open the review page for application "app-001"
    And I enter reviewer email "alice@company.com"
    And I select decision "override_pass"
    And I enter reason "Strong portfolio despite missing cert"
    And I click submit
    Then the API receives a POST to "/api/applications/app-001/reviews/"
    And the request body contains decision "override_pass"
    And the request body contains reason "Strong portfolio despite missing cert"

  # ---------------------------------------------------------------------------
  # Error states
  # ---------------------------------------------------------------------------

  Scenario: API returns 404 — error message displayed
    Given the application "app-999" does not exist
    When I open the review page for application "app-999"
    Then an error message "Application not found" is displayed

  Scenario: API submission fails — error message displayed
    When I open the review page for application "app-001"
    And I select decision "approve"
    And the API returns a 500 error on submit
    And I click submit
    Then an error message "Submission failed" is displayed
    And the form remains visible

  # ---------------------------------------------------------------------------
  # Audit Trail
  # ---------------------------------------------------------------------------

  Scenario: Audit trail shows past reviews
    Given the application has an existing review:
      | reviewer_email   | decision | reviewed_at              |
      | bob@company.com  | approve  | 2026-06-10T14:00:00Z     |
    When I open the review page for application "app-001"
    Then the audit trail shows reviewer "bob@company.com"
    And the audit trail shows decision "approve"
