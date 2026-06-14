# features/hard_gate.feature
#
# Outer-loop BDD specification for the Hard Gate (Stage 1).
#
# These scenarios define the CONTRACT for the hard gate, not the implementation.
# Run these first — they must ALL fail before any implementation is written.
#
# Business rules encoded here:
#   1. All criteria pass  → gate outcome is "pass"
#   2. Any criterion fails → gate outcome is "fail" (regardless of others)
#   3. Required data absent → gate outcome is "unknown"
#   4. FAIL takes precedence over UNKNOWN
#   5. Gate outcome of "fail" forces final score to exactly 0.0

Feature: Hard Gate Evaluation
  As a pipeline orchestrator
  I want to evaluate mandatory must-haves against a candidate's parsed resume
  So that disqualified candidates are identified immediately
  And scoring resources are not consumed on candidates who cannot proceed

  Background:
    Given the hard gate evaluator is initialized

  # ---------------------------------------------------------------------------
  # Pass scenarios
  # ---------------------------------------------------------------------------

  Scenario: Candidate satisfies a single years-of-experience criterion
    Given a job has must-have criteria:
      | criterion          | type             | minimum_years |
      | minimum_experience | years_experience | 5             |
    And a candidate resume has these fields:
      | field                  | value |
      | total_experience_years | 7     |
    When the hard gate evaluation runs
    Then the overall gate outcome is "pass"
    And the criterion "minimum_experience" outcome is "pass"

  Scenario: Candidate satisfies all mixed criteria
    Given a job has must-have criteria:
      | criterion    | type             | minimum_years | keywords | sections         | required |
      | experience   | years_experience | 5             |          |                  |          |
      | python_skill | keyword_presence |               | Python   | skills,experience|          |
    And a candidate resume has these fields:
      | field                  | value              |
      | total_experience_years | 6                  |
      | skills                 | Python Django REST |
    When the hard gate evaluation runs
    Then the overall gate outcome is "pass"

  # ---------------------------------------------------------------------------
  # Fail scenarios
  # ---------------------------------------------------------------------------

  Scenario: Candidate fails the years-of-experience criterion
    Given a job has must-have criteria:
      | criterion          | type             | minimum_years |
      | minimum_experience | years_experience | 5             |
    And a candidate resume has these fields:
      | field                  | value |
      | total_experience_years | 3     |
    When the hard gate evaluation runs
    Then the overall gate outcome is "fail"
    And the criterion "minimum_experience" outcome is "fail"

  Scenario: Candidate is missing a required keyword
    Given a job has must-have criteria:
      | criterion    | type             | keywords | sections |
      | python_skill | keyword_presence | Python   | skills   |
    And a candidate resume has these fields:
      | field  | value          |
      | skills | Java Spring Go |
    When the hard gate evaluation runs
    Then the overall gate outcome is "fail"
    And the criterion "python_skill" outcome is "fail"

  Scenario: Candidate is missing a required certification
    Given a job has must-have criteria:
      | criterion  | type          | required                  |
      | aws_cert   | certification | AWS Solutions Architect   |
    And a candidate resume has these fields:
      | field          | value        |
      | certifications | GCP Associate |
    When the hard gate evaluation runs
    Then the overall gate outcome is "fail"
    And the criterion "aws_cert" outcome is "fail"

  Scenario: A single fail among multiple criteria still produces fail
    Given a job has must-have criteria:
      | criterion          | type             | minimum_years | keywords | sections |
      | minimum_experience | years_experience | 5             |          |          |
      | python_skill       | keyword_presence |               | Python   | skills   |
    And a candidate resume has these fields:
      | field                  | value  |
      | total_experience_years | 3      |
      | skills                 | Python |
    When the hard gate evaluation runs
    Then the overall gate outcome is "fail"
    And the criterion "minimum_experience" outcome is "fail"
    And the criterion "python_skill" outcome is "pass"

  # ---------------------------------------------------------------------------
  # Unknown scenarios
  # ---------------------------------------------------------------------------

  Scenario: Required experience data is absent from the resume
    Given a job has must-have criteria:
      | criterion          | type             | minimum_years |
      | minimum_experience | years_experience | 5             |
    And a candidate resume has these fields:
      | field | value |
    When the hard gate evaluation runs
    Then the overall gate outcome is "unknown"
    And the criterion "minimum_experience" outcome is "unknown"

  Scenario: Certifications section is absent from the resume
    Given a job has must-have criteria:
      | criterion | type          | required                |
      | aws_cert  | certification | AWS Solutions Architect |
    And a candidate resume has these fields:
      | field | value |
    When the hard gate evaluation runs
    Then the overall gate outcome is "unknown"

  Scenario: An unrecognised criterion type produces unknown
    Given a job has must-have criteria:
      | criterion  | type            |
      | mystery    | unsupported_xyz |
    And a candidate resume has these fields:
      | field | value |
    When the hard gate evaluation runs
    Then the overall gate outcome is "unknown"
    And the criterion "mystery" outcome is "unknown"

  # ---------------------------------------------------------------------------
  # Precedence scenarios
  # ---------------------------------------------------------------------------

  Scenario: Fail takes precedence over unknown
    Given a job has must-have criteria:
      | criterion          | type             | minimum_years | required                |
      | minimum_experience | years_experience | 5             |                         |
      | aws_cert           | certification    |               | AWS Solutions Architect |
    And a candidate resume has these fields:
      | field                  | value |
      | total_experience_years | 3     |
    When the hard gate evaluation runs
    Then the overall gate outcome is "fail"
    And the criterion "minimum_experience" outcome is "fail"
    And the criterion "aws_cert" outcome is "unknown"

  Scenario: Unknown takes precedence over pass
    Given a job has must-have criteria:
      | criterion          | type             | minimum_years | keywords | sections |
      | minimum_experience | years_experience | 5             |          |          |
      | python_skill       | keyword_presence |               | Python   | skills   |
    And a candidate resume has these fields:
      | field  | value  |
      | skills | Python |
    When the hard gate evaluation runs
    Then the overall gate outcome is "unknown"
    And the criterion "minimum_experience" outcome is "unknown"
    And the criterion "python_skill" outcome is "pass"

  # ---------------------------------------------------------------------------
  # Final score integration
  # ---------------------------------------------------------------------------

  Scenario: Final score is zero when hard gate fails
    Given a candidate application has a gate outcome of "fail"
    And the semantic match score is 0.85
    And the rubric normalized score is 0.78
    And the evidence quality score is 0.70
    When the final score is calculated
    Then the final score is exactly 0.0

  Scenario: Final score uses weighted formula when hard gate passes
    Given a candidate application has a gate outcome of "pass"
    And the semantic match score is 1.0
    And the rubric normalized score is 1.0
    And the evidence quality score is 1.0
    When the final score is calculated
    Then the final score is exactly 1.0

  Scenario: Final score uses weighted formula when hard gate is unknown
    Given a candidate application has a gate outcome of "unknown"
    And the semantic match score is 0.5
    And the rubric normalized score is 0.5
    And the evidence quality score is 0.5
    When the final score is calculated
    Then the final score is exactly 0.5
