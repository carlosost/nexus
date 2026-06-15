# features/job_lifecycle.feature
#
# Outer-loop BDD specification — Job domain: CRUD lifecycle,
# Markdown ingestion, and vector embedding pipeline.
#
# Business rules encoded here:
#   1.  POST /api/jobs/markdown/ accepts raw Markdown and creates a Job record.
#   2.  The parser maps Markdown structure to Job.title, .description,
#       .requirements_raw, and .must_haves using JOB_SPEC as the reference.
#   3.  A malformed or partially missing Markdown body returns HTTP 422 with
#       a field-level error map — the DB connection is NOT dropped.
#   4.  A completely blank body returns HTTP 400 before reaching the parser.
#   5.  GET /api/jobs/<uuid>/ returns full Job detail.
#   6.  DELETE /api/jobs/<uuid>/ removes the Job and all JobSectionEmbeddings.
#   7.  Embedding generation is triggered after create.
#   8.  Embedding timeout does NOT fail the HTTP response — the Job is persisted
#       and the error swallowed (graceful degradation).
#  10.  Deleting a Job leaves no orphan vector rows in JobSectionEmbedding.

Feature: Job Lifecycle — Markdown Ingestion, CRUD, and Vector Embeddings
  As a recruiting operator
  I want to manage Job records through their full lifecycle
  So that candidates can be accurately matched against well-structured positions

  Background:
    Given the Job ingestion parser is initialized
    And the embedding backend is set to "mock"
    And the database is empty of Job records


  # ───────────────────────────────────────────────────────────────────────────
  # Scenario Group 1 — Successful Markdown creation
  # ───────────────────────────────────────────────────────────────────────────

  Scenario: Full JOB_SPEC-compliant Markdown creates a valid Job record
    Given the following raw Markdown job specification:
      """
      # Senior Backend Engineer

      ## Description
      We are looking for a Senior Backend Engineer with deep Python and Django
      experience to lead backend development of our data platform.

      ## Requirements
      ### Required Skills
      - Python
      - Django
      - PostgreSQL
      - REST APIs
      ### Preferred Skills
      - Redis
      - Docker
      - Kubernetes
      ### Minimum Experience
      5 years

      ## Must Haves
      ### min_experience
      type: years_experience
      minimum_years: 5
      ### python_required
      type: keyword_presence
      keywords: Python
      sections: skills, experience
      ### django_required
      type: keyword_presence
      keywords: Django
      sections: skills, experience
      """
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 201
    And the response body contains field "id"
    And the response body contains field "title" with value "Senior Backend Engineer"
    And the response body contains field "created_at"

  Scenario: Parser extracts title correctly from the H1 heading
    Given a valid Markdown job spec with title "Principal Data Engineer"
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 201
    And the persisted Job title is "Principal Data Engineer"

  Scenario: Parser maps description from the Description section
    Given a valid Markdown job spec with a description section containing "next-generation data platform"
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the persisted Job description contains "next-generation data platform"

  Scenario: Parser maps required_skills list into requirements_raw
    Given a valid Markdown job spec with required skills: Python, Django, PostgreSQL
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the persisted Job has required_skills containing "Python"
    And the persisted Job has required_skills containing "Django"
    And the persisted Job has required_skills containing "PostgreSQL"

  Scenario: Parser extracts minimum_experience_years as an integer
    Given a valid Markdown job spec with "Minimum Experience" of 5 years
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the persisted Job minimum_experience_years equals 5

  Scenario: Parser maps must_haves years_experience criterion correctly
    Given a valid Markdown job spec with must_have criterion "min_experience" of type "years_experience" with minimum_years 5
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the persisted Job must_haves "min_experience" type equals "years_experience"
    And the persisted Job must_haves "min_experience" minimum_years equals 5

  Scenario: Parser maps keyword_presence criteria with section lists
    Given a valid Markdown job spec with must_have criterion "python_required" requiring keyword "Python" in sections "skills, experience"
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the persisted Job must_haves "python_required" type equals "keyword_presence"
    And the persisted Job must_haves "python_required" keywords contains "Python"
    And the persisted Job must_haves "python_required" sections contains "skills"


  # ───────────────────────────────────────────────────────────────────────────
  # Scenario Group 2 — Resilient graceful failure on malformed Markdown
  # ───────────────────────────────────────────────────────────────────────────

  Scenario: Completely blank body returns 400 without touching the parser
    Given an empty request body
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 400
    And the response body contains key "raw_markdown"
    And no Job records exist in the database

  Scenario: Markdown missing the H1 title heading returns 422
    Given a Markdown body with no H1 heading line
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 422
    And the response body contains key "title"
    And no Job records exist in the database

  Scenario: Markdown with only a title but no description returns 422
    Given a Markdown body containing only a lone title heading
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 422
    And the response body contains key "description"
    And no Job records exist in the database

  Scenario: Malformed must_haves block produces a 422 with field-level error
    Given a Markdown job spec where the Must Haves section has invalid syntax
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 422
    And the response body contains key "must_haves"
    And no Job records exist in the database

  Scenario: Duplicate title returns 409 — existing record is not mutated
    Given a Job named "Senior Backend Engineer" already exists in the mock store
    And a valid Markdown job spec with title "Senior Backend Engineer"
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 409


  # ───────────────────────────────────────────────────────────────────────────
  # Scenario Group 3 — Full CRUD lifecycle (view-layer, no DB)
  # ───────────────────────────────────────────────────────────────────────────

  Scenario: GET /api/jobs/ lists all Job records
    Given 3 Jobs exist in the mock store
    When I GET "/api/jobs/"
    Then the response status is 200
    And the response body is a list of 3 items

  Scenario: GET /api/jobs/ for an unknown id returns 404
    When I GET "/api/jobs/00000000-0000-0000-0000-000000000000/"
    Then the response status is 404

  Scenario: DELETE /api/jobs/ removes the Job record
    Given a Job exists in the mock store with title "To Delete" and description "Gone."
    When I DELETE the Job
    Then the response status is 204
