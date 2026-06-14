# features/pipeline_orchestration.feature
#
# Outer-loop BDD specification for the Pipeline Orchestrator.
#
# The orchestrator is the seam where all four stages connect.
# These scenarios define the CONTRACT, not the wiring details.
#
# Business rules encoded here:
#   1. Hard Gate FAIL → pipeline stops immediately; final score = 0.0.
#   2. Hard Gate UNKNOWN → pipeline continues; score carries reduced confidence.
#   3. Hard Gate PASS → all stages execute; final score = weighted formula.
#   4. Stages 2 (Semantic) and 3 (Rubric) must NOT execute when gate fails.
#   5. One observability latency record is emitted per stage that executes.
#   6. Every gate criterion transition is captured in the audit log.
#   7. A short-circuit event is logged when the gate hard-fails.
#   8. A score_computed event is logged when the full pipeline completes.

Feature: Pipeline Orchestration
  As a pipeline consumer
  I want to submit a candidate-job pair to the orchestrator
  So that I receive a structured PipelineResult reflecting every stage's output
  And so that short-circuits, scores, and overrides are fully auditable

  Background:
    Given the pipeline orchestrator is initialized with all stage evaluators

  # ---------------------------------------------------------------------------
  # Gate FAIL — short-circuit path
  # ---------------------------------------------------------------------------

  Scenario: Gate FAIL stops the pipeline and returns score zero
    Given a candidate resumes with total experience years of 2
    And a job requires minimum 5 years experience
    When the pipeline runs
    Then the final score is 0.0
    And the gate outcome is "fail"
    And the semantic match stage was not executed
    And the rubric scoring stage was not executed

  Scenario: Gate FAIL with multiple criteria still short-circuits at gate
    Given a candidate resumes with total experience years of 2
    And a job requires minimum 5 years experience
    And a job requires keyword "Python" in skills
    And a candidate has skills "Java Spring Boot"
    When the pipeline runs
    Then the final score is 0.0
    And the gate outcome is "fail"
    And the semantic match stage was not executed

  Scenario: Short-circuit event is written to the audit log on gate FAIL
    Given a candidate resumes with total experience years of 2
    And a job requires minimum 5 years experience
    When the pipeline runs
    Then the audit log contains a "pipeline_short_circuited" event

  Scenario: Gate criterion transitions are all written to the audit log
    Given a candidate resumes with total experience years of 7
    And a job requires minimum 5 years experience
    When the pipeline runs
    Then the audit log contains at least 1 "gate_transition" event

  # ---------------------------------------------------------------------------
  # Gate PASS — full pipeline path
  # ---------------------------------------------------------------------------

  Scenario: Gate PASS executes all stages
    Given a candidate resumes with total experience years of 7
    And a job requires minimum 5 years experience
    And the candidate has matching section embeddings for the job
    When the pipeline runs
    Then the gate outcome is "pass"
    And the semantic match stage was executed
    And the rubric scoring stage was executed
    And the final score is greater than 0.0

  Scenario: Gate PASS produces a final score using the weighted formula
    Given a candidate resumes with total experience years of 7
    And a job requires minimum 5 years experience
    And the semantic match score will be 1.0
    And the rubric normalized score will be 1.0
    And the evidence quality will be 1.0
    And the candidate has matching section embeddings for the job
    When the pipeline runs
    Then the final score is approximately 1.0

  Scenario: Score computed event is written to the audit log on successful run
    Given a candidate resumes with total experience years of 7
    And a job requires minimum 5 years experience
    And the candidate has matching section embeddings for the job
    When the pipeline runs
    Then the audit log contains a "score_computed" event

  # ---------------------------------------------------------------------------
  # Gate UNKNOWN — continuation with reduced confidence
  # ---------------------------------------------------------------------------

  Scenario: Gate UNKNOWN continues the pipeline
    Given a candidate resume has no parseable experience field
    And a job requires minimum 5 years experience
    And the candidate has matching section embeddings for the job
    When the pipeline runs
    Then the gate outcome is "unknown"
    And the semantic match stage was executed
    And the rubric scoring stage was executed

  Scenario: Gate UNKNOWN result carries a confidence flag below 1.0
    Given a candidate resume has no parseable experience field
    And a job requires minimum 5 years experience
    And the candidate has matching section embeddings for the job
    When the pipeline runs
    Then the pipeline result confidence is less than 1.0

  # ---------------------------------------------------------------------------
  # Observability
  # ---------------------------------------------------------------------------

  Scenario: One latency record is emitted per executed stage
    Given a candidate resumes with total experience years of 7
    And a job requires minimum 5 years experience
    And the candidate has matching section embeddings for the job
    When the pipeline runs
    Then there are exactly 3 observability latency records

  Scenario: Only one latency record is emitted when gate fails
    Given a candidate resumes with total experience years of 2
    And a job requires minimum 5 years experience
    When the pipeline runs
    Then there is exactly 1 observability latency record

  # ---------------------------------------------------------------------------
  # PipelineResult structure
  # ---------------------------------------------------------------------------

  Scenario: PipelineResult exposes the correct stages_executed list on full run
    Given a candidate resumes with total experience years of 7
    And a job requires minimum 5 years experience
    And the candidate has matching section embeddings for the job
    When the pipeline runs
    Then the stages executed are "hard_gate, semantic_match, rubric"

  Scenario: PipelineResult stages_executed is only hard_gate on short-circuit
    Given a candidate resumes with total experience years of 2
    And a job requires minimum 5 years experience
    When the pipeline runs
    Then the stages executed are "hard_gate"
