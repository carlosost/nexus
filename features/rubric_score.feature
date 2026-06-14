Feature: LLM Rubric Scoring — Stage 3
  As a pipeline operator
  I want the rubric evaluator to produce consistent, bounded scores
  So that the final score accurately reflects candidate competency

  Background:
    Given a rubric evaluator backed by a mock LLM
    And the rubric weight invariant holds (weights sum to 1.0)

  # ---------------------------------------------------------------------------
  # Score normalization
  # ---------------------------------------------------------------------------

  Scenario: Perfect raw scores produce normalized_score of 1.0
    Given the LLM returns all rubric scores as 5
    When I evaluate a resume against job requirements
    Then the normalized_score is 1.0
    And the criterion_scores contains "core_skills" with value 5.0
    And the criterion_scores contains "relevant_experience" with value 5.0
    And the criterion_scores contains "scope_impact" with value 5.0
    And the criterion_scores contains "domain_alignment" with value 5.0
    And the criterion_scores contains "education_certs" with value 5.0

  Scenario: Minimum raw scores produce normalized_score of 0.2
    Given the LLM returns all rubric scores as 1
    When I evaluate a resume against job requirements
    Then the normalized_score is 0.2

  Scenario: Mixed raw scores normalize to correct weighted average
    Given the LLM returns rubric scores:
      | criterion           | score |
      | core_skills         | 5     |
      | relevant_experience | 4     |
      | scope_impact        | 3     |
      | domain_alignment    | 2     |
      | education_certs     | 1     |
    When I evaluate a resume against job requirements
    Then the normalized_score is approximately 0.74

  Scenario: Stub-equivalent scores (all 3.5) normalize to 0.70
    Given the LLM returns all rubric scores as 3.5
    When I evaluate a resume against job requirements
    Then the normalized_score is approximately 0.70

  # ---------------------------------------------------------------------------
  # Score clamping
  # ---------------------------------------------------------------------------

  Scenario: Raw scores above 5 are clamped to 5
    Given the LLM returns a score of 7 for "core_skills" and 3 for all others
    When I evaluate a resume against job requirements
    Then the criterion_scores contains "core_skills" with value 5.0

  Scenario: Raw scores below 1 are clamped to 1
    Given the LLM returns a score of 0 for "relevant_experience" and 3 for all others
    When I evaluate a resume against job requirements
    Then the criterion_scores contains "relevant_experience" with value 1.0

  # ---------------------------------------------------------------------------
  # Evidence quality
  # ---------------------------------------------------------------------------

  Scenario: All justifications substantive — evidence_quality is 1.0
    Given the LLM returns all rubric scores as 4
    And all justifications have at least 10 words
    When I evaluate a resume against job requirements
    Then the evidence_quality is 1.0

  Scenario: No justifications present — evidence_quality is 0.0
    Given the LLM returns all rubric scores as 4
    And all justifications are empty strings
    When I evaluate a resume against job requirements
    Then the evidence_quality is 0.0

  Scenario: Partial justifications — evidence_quality is proportional
    Given the LLM returns all rubric scores as 4
    And 2 of 5 justifications have at least 10 words
    When I evaluate a resume against job requirements
    Then the evidence_quality is approximately 0.40

  # ---------------------------------------------------------------------------
  # LLM parse failure — graceful fallback
  # ---------------------------------------------------------------------------

  Scenario: LLM returns malformed JSON — fallback scores used
    Given the LLM returns invalid JSON "this is not json"
    When I evaluate a resume against job requirements
    Then the normalized_score is approximately 0.60
    And the evidence_quality is 0.0

  Scenario: LLM returns JSON in a markdown code block — parsed correctly
    Given the LLM returns valid JSON wrapped in a markdown code block
    When I evaluate a resume against job requirements
    Then the normalized_score is greater than 0.0

  Scenario: LLM returns empty string — fallback scores used
    Given the LLM returns an empty string
    When I evaluate a resume against job requirements
    Then the normalized_score is approximately 0.60
    And the evidence_quality is 0.0

  # ---------------------------------------------------------------------------
  # Protocol conformance
  # ---------------------------------------------------------------------------

  Scenario: RubricEvaluator satisfies RubricEvaluatorProtocol at runtime
    Given a rubric evaluator backed by a mock LLM
    Then the evaluator is an instance of RubricEvaluatorProtocol

  Scenario: RubricResult fields are bounded
    Given the LLM returns all rubric scores as 5
    And all justifications have at least 10 words
    When I evaluate a resume against job requirements
    Then the normalized_score is between 0.0 and 1.0
    And the evidence_quality is between 0.0 and 1.0

  # ---------------------------------------------------------------------------
  # M3 Upgrade — Pydantic schema, real backends, factory
  # ---------------------------------------------------------------------------

  Scenario: RubricScoreResponse rejects a score below the valid range
    When I construct a RubricScoreResponse with score 0 for "core_skills"
    Then a ValidationError is raised

  Scenario: RubricScoreResponse rejects a score above the valid range
    When I construct a RubricScoreResponse with score 6 for "core_skills"
    Then a ValidationError is raised

  Scenario: RubricScoreResponse rejects a response missing a required criterion
    When I construct a RubricScoreResponse with "scope_impact" omitted from scores
    Then a ValidationError is raised

  Scenario: RubricScoreResponse accepts a fully valid response
    When I construct a valid RubricScoreResponse with all scores set to 4
    Then no ValidationError is raised
    And the RubricScoreResponse has scores for all five criteria

  Scenario: make_rubric_backend returns MockLLMBackend for backend "mock"
    When I call make_rubric_backend with backend "mock"
    Then the result satisfies LLMBackendProtocol

  Scenario: make_rubric_backend returns OpenAIRubricBackend for backend "openai"
    When I call make_rubric_backend with backend "openai"
    Then the result satisfies LLMBackendProtocol
    And the result is an OpenAIRubricBackend

  Scenario: make_rubric_backend returns AnthropicRubricBackend for backend "anthropic"
    When I call make_rubric_backend with backend "anthropic"
    Then the result satisfies LLMBackendProtocol
    And the result is an AnthropicRubricBackend

  Scenario: OpenAIRubricBackend retries on RateLimitError and eventually succeeds
    Given an OpenAIRubricBackend whose client raises RateLimitError twice then succeeds
    When I call complete on the backend
    Then the backend returns a valid RubricScoreResponse
    And the underlying client was called 3 times

  Scenario: OpenAIRubricBackend raises after exhausting all retries
    Given an OpenAIRubricBackend whose client always raises RateLimitError
    When I call complete on the backend
    Then a RateLimitError is raised after 3 attempts

  Scenario: RubricEvaluator accepts a RubricScoreResponse object directly from a real backend
    Given a rubric evaluator backed by a mock backend returning a RubricScoreResponse object
    When I evaluate a resume against job requirements
    Then the normalized_score is greater than 0.0
    And the evidence_quality is between 0.0 and 1.0
