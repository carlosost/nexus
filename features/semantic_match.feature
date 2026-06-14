# features/semantic_match.feature
#
# Outer-loop BDD specification for Stage 2: Semantic Match.
#
# Business rules encoded here:
#   1. Section-weighted cosine similarity captures relevance at section granularity.
#   2. RRF fuses lexical (FTS) and semantic (pgvector) rank signals.
#   3. Score is always in [0, 1] — never exceeds 1.0 regardless of inputs.
#   4. When only one retrieval channel provides a rank, the score degrades gracefully.
#   5. The final semantic score fed into Stage 4 is the RRF-blended result.

Feature: Semantic Match Evaluation
  As a pipeline orchestrator
  I want to compute a semantic relevance score between a candidate and a job
  So that I can rank candidates using both lexical and vector-space signals
  And combine them via Reciprocal Rank Fusion into a single normalized score

  Background:
    Given the semantic match evaluator is initialized
    And the standard section weights are:
      | section          | weight |
      | experience       | 0.40   |
      | skills           | 0.30   |
      | summary          | 0.15   |
      | education        | 0.05   |
      | certifications   | 0.05   |
      | projects         | 0.05   |

  # ---------------------------------------------------------------------------
  # Cosine similarity — per-section
  # ---------------------------------------------------------------------------

  Scenario: Identical embeddings yield perfect per-section similarity
    Given a candidate section "experience" has embedding vector [1.0, 0.0, 0.0]
    And the job section "experience" has embedding vector [1.0, 0.0, 0.0]
    When the cosine similarity is computed for section "experience"
    Then the section similarity score is 1.0

  Scenario: Orthogonal embeddings yield zero per-section similarity
    Given a candidate section "skills" has embedding vector [1.0, 0.0, 0.0]
    And the job section "skills" has embedding vector [0.0, 1.0, 0.0]
    When the cosine similarity is computed for section "skills"
    Then the section similarity score is 0.0

  Scenario: Partially aligned embeddings yield intermediate similarity
    Given a candidate section "experience" has embedding vector [1.0, 1.0, 0.0]
    And the job section "experience" has embedding vector [1.0, 0.0, 0.0]
    When the cosine similarity is computed for section "experience"
    Then the section similarity score is approximately 0.707

  # ---------------------------------------------------------------------------
  # Section-weighted similarity
  # ---------------------------------------------------------------------------

  Scenario: Experience section is weighted most heavily
    Given candidate section embeddings:
      | section    | vector        |
      | experience | [1.0, 0.0]    |
      | skills     | [0.0, 1.0]    |
    And job section embeddings:
      | section    | vector        |
      | experience | [1.0, 0.0]    |
      | skills     | [1.0, 0.0]    |
    When the section-weighted similarity is computed
    Then the weighted similarity is greater than 0.5
    And the weighted similarity is less than 1.0

  Scenario: Candidate with only matching experience outscores one with only matching skills
    Given a candidate A has perfect match on "experience" and zero match on "skills"
    And a candidate B has zero match on "experience" and perfect match on "skills"
    When both candidates' section-weighted similarities are computed
    Then candidate A weighted similarity is greater than candidate B weighted similarity

  Scenario: Sections absent from candidate embeddings are excluded from weighted average
    Given candidate section embeddings:
      | section | vector     |
      | skills  | [1.0, 0.0] |
    And job section embeddings:
      | section    | vector     |
      | experience | [1.0, 0.0] |
      | skills     | [1.0, 0.0] |
    When the section-weighted similarity is computed
    Then the weighted similarity is 1.0

  # ---------------------------------------------------------------------------
  # RRF math
  # ---------------------------------------------------------------------------

  Scenario: Candidate ranked first in both channels achieves maximum RRF score
    Given a candidate has lexical rank 1 and semantic rank 1
    When the RRF score is computed with k=60
    Then the normalized RRF score is 1.0

  Scenario: Higher ranks produce lower RRF score
    Given a candidate has lexical rank 10 and semantic rank 10
    When the RRF score is computed with k=60
    Then the normalized RRF score is less than the score for ranks 1 and 1

  Scenario: Only lexical rank available produces valid partial score
    Given a candidate has lexical rank 1 and no semantic rank
    When the RRF score is computed with k=60
    Then the normalized RRF score is greater than 0.0
    And the normalized RRF score is less than 1.0

  Scenario: Only semantic rank available produces valid partial score
    Given a candidate has no lexical rank and semantic rank 1
    When the RRF score is computed with k=60
    Then the normalized RRF score is greater than 0.0
    And the normalized RRF score is less than 1.0

  Scenario: No ranks available produces zero score
    Given a candidate has no lexical rank and no semantic rank
    When the RRF score is computed with k=60
    Then the normalized RRF score is 0.0

  Scenario: RRF score is always in range 0 to 1
    Given a candidate has lexical rank 1000 and semantic rank 1000
    When the RRF score is computed with k=60
    Then the normalized RRF score is greater than or equal to 0.0
    And the normalized RRF score is less than or equal to 1.0

  # ---------------------------------------------------------------------------
  # Full SemanticMatchEvaluator — end-to-end
  # ---------------------------------------------------------------------------

  Scenario: Full evaluation with top ranks and strong embeddings scores near 1.0
    Given candidate section embeddings:
      | section    | vector        |
      | experience | [1.0, 0.0]    |
      | skills     | [1.0, 0.0]    |
    And job section embeddings:
      | section    | vector        |
      | experience | [1.0, 0.0]    |
      | skills     | [1.0, 0.0]    |
    And the candidate has lexical rank 1 and semantic rank 1
    When the full semantic match evaluation runs
    Then the final semantic match score is 1.0

  Scenario: Full evaluation with poor embeddings and low ranks scores near 0.0
    Given candidate section embeddings:
      | section    | vector        |
      | experience | [0.0, 1.0]    |
      | skills     | [0.0, 1.0]    |
    And job section embeddings:
      | section    | vector        |
      | experience | [1.0, 0.0]    |
      | skills     | [1.0, 0.0]    |
    And the candidate has no lexical rank and no semantic rank
    When the full semantic match evaluation runs
    Then the final semantic match score is 0.0

  Scenario: Observability records latency after evaluation
    Given candidate section embeddings:
      | section    | vector     |
      | experience | [1.0, 0.0] |
    And job section embeddings:
      | section    | vector     |
      | experience | [1.0, 0.0] |
    And the candidate has lexical rank 1 and semantic rank 1
    When the full semantic match evaluation runs
    Then a latency record exists for stage "semantic_match"
    And the latency record has latency_ms greater than or equal to 0.0
