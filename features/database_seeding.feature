Feature: Database Seeding — Milestone 0.6
  As a pipeline operator
  I want the database pre-populated with demo data on first boot
  So that the pipeline is demonstrable with zero manual data entry
  and no manual setup steps

  Background:
    Given the seed data specification is loaded

  # ---------------------------------------------------------------------------
  # Seed spec validation — no database required
  # These scenarios verify the data constants, not the DB layer.
  # ---------------------------------------------------------------------------

  Scenario: Seed spec defines exactly one job
    Then the seed spec contains exactly 1 job definition

  Scenario: Seed spec defines exactly three candidates
    Then the seed spec contains exactly 3 candidate definitions

  Scenario: The demo job has a title and required must-haves
    Then the job spec has a non-empty title
    And the job spec must_haves include a years_experience criterion
    And the job spec must_haves include at least one keyword_presence criterion

  # ---------------------------------------------------------------------------
  # Gate outcome validation — verifies each candidate triggers the intended
  # pipeline path when HardGateEvaluator runs on their resume_parsed data
  # ---------------------------------------------------------------------------

  Scenario: Strong-match candidate passes all hard-gate criteria
    When the hard gate evaluates candidate "alice@demo.example.com"
    Then the gate outcome is "pass"

  Scenario: Borderline candidate produces gate unknown due to missing experience data
    When the hard gate evaluates candidate "bob@demo.example.com"
    Then the gate outcome is "unknown"

  Scenario: Hard-fail candidate fails the hard gate
    When the hard gate evaluates candidate "carol@demo.example.com"
    Then the gate outcome is "fail"

  Scenario: Hard-fail candidate has experience below the minimum
    When the hard gate evaluates candidate "carol@demo.example.com"
    Then the years_experience criterion outcome is "fail"

  # ---------------------------------------------------------------------------
  # Idempotency contract — mocked ORM, no real database
  # ---------------------------------------------------------------------------

  Scenario: seed_demo uses get_or_create for the job record
    When seed_demo runs against a mock database
    Then Job.objects.get_or_create was called with title "Senior Backend Engineer"
    And no duplicate Job records were created

  Scenario: seed_demo uses get_or_create for each candidate record
    When seed_demo runs against a mock database
    Then Candidate.objects.get_or_create was called 3 times
    And each call used the candidate email as the natural key

  Scenario: seed_demo is idempotent — second run reports zero new records
    Given all demo records already exist in the mock database
    When seed_demo runs against a mock database
    Then the log reports jobs_created=0
    And the log reports candidates_created=0
    And the log reports idempotent=true

  Scenario: seed_demo reports created counts on first run
    Given the mock database is empty
    When seed_demo runs against a mock database
    Then the log reports jobs_created=1
    And the log reports candidates_created=3
    And the log reports idempotent=false

  # ---------------------------------------------------------------------------
  # Audit / telemetry
  # ---------------------------------------------------------------------------

  Scenario: seed_demo emits a structured completion log event
    When seed_demo runs against a mock database
    Then a "demo_seed_completed" log event is emitted
