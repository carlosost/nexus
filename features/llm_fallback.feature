Feature: LLM Provider Resilience — Automatic Failover
  As a platform engineer operating the resume evaluation pipeline
  I want the rubric scoring stage to automatically fail over to a secondary
  LLM provider when the primary exhausts its retry budget
  So that a recruiter's candidate upload never fails due to a single provider outage

  Background:
    Given a valid resume for Alice with 7 years of Python and Django experience
    And a job with must-haves: 5+ years experience, Python, Django
    And a mock rubric backend that returns all scores of 4

  # ─────────────────────────────────────────────────────────────────────────
  # Scenario 1: Rate limit on primary → fallback completes successfully
  # ─────────────────────────────────────────────────────────────────────────
  Scenario: Primary provider hits rate limit and fallback evaluates the resume
    Given the primary LLM backend is OpenAI configured with max_retries 3
    And the OpenAI client raises RateLimitError on every attempt
    And the fallback LLM backend is Anthropic and returns a valid rubric score
    And a FallbackLLMBackend is wired with OpenAI as primary and Anthropic as fallback
    When the rubric evaluator runs against Alice's resume
    Then the rubric evaluation completes successfully
    And the RubricResult has is_evaluated_via_fallback set to True
    And a "primary_llm_failed" audit event is emitted with provider "gpt-4o-mini"
    And a "primary_llm_failed" event has error_type "RateLimitError"
    And a "fallback_llm_engaged" audit event is emitted with target_provider "claude-haiku-4-5-20251001"
    And a "fallback_llm_succeeded" audit event is emitted with provider "claude-haiku-4-5-20251001"
    And no "fallback_llm_exhausted" event is emitted

  # ─────────────────────────────────────────────────────────────────────────
  # Scenario 2: API timeout on primary → fallback completes successfully
  # ─────────────────────────────────────────────────────────────────────────
  Scenario: Primary provider times out and fallback evaluates the resume
    Given the primary LLM backend is OpenAI configured with max_retries 3
    And the OpenAI client raises APITimeoutError on every attempt
    And the fallback LLM backend is Anthropic and returns a valid rubric score
    And a FallbackLLMBackend is wired with OpenAI as primary and Anthropic as fallback
    When the rubric evaluator runs against Alice's resume
    Then the rubric evaluation completes successfully
    And the RubricResult has is_evaluated_via_fallback set to True
    And a "primary_llm_failed" audit event is emitted with provider "gpt-4o-mini"
    And a "primary_llm_failed" event has error_type "APITimeoutError"
    And a "fallback_llm_engaged" audit event is emitted with target_provider "claude-haiku-4-5-20251001"
    And a "fallback_llm_succeeded" audit event is emitted with provider "claude-haiku-4-5-20251001"

  # ─────────────────────────────────────────────────────────────────────────
  # Scenario 3: Primary succeeds — fallback must NOT be engaged
  # ─────────────────────────────────────────────────────────────────────────
  Scenario: Primary provider succeeds — no fallback is engaged
    Given the primary LLM backend is OpenAI configured with max_retries 3
    And the OpenAI client returns a valid rubric score on the first attempt
    And a FallbackLLMBackend is wired with OpenAI as primary and Anthropic as fallback
    When the rubric evaluator runs against Alice's resume
    Then the rubric evaluation completes successfully
    And the RubricResult has is_evaluated_via_fallback set to False
    And no "primary_llm_failed" event is emitted
    And no "fallback_llm_engaged" event is emitted
    And no "fallback_llm_succeeded" event is emitted

  # ─────────────────────────────────────────────────────────────────────────
  # Scenario 4: Both providers fail — exception propagates
  # ─────────────────────────────────────────────────────────────────────────
  Scenario: Both primary and fallback providers fail — exception is raised
    Given the primary LLM backend is OpenAI configured with max_retries 3
    And the OpenAI client raises APIConnectionError on every attempt
    And the fallback LLM backend is Anthropic and also raises an exception
    And a FallbackLLMBackend is wired with OpenAI as primary and Anthropic as fallback
    When the rubric evaluator attempts to run against Alice's resume
    Then a provider exception is raised
    And a "primary_llm_failed" audit event is emitted with provider "gpt-4o-mini"
    And a "fallback_llm_engaged" audit event is emitted with target_provider "claude-haiku-4-5-20251001"
    And a "fallback_llm_exhausted" audit event is emitted
    And a "fallback_llm_exhausted" event has primary_provider "gpt-4o-mini"
    And a "fallback_llm_exhausted" event has fallback_provider "claude-haiku-4-5-20251001"

  # ─────────────────────────────────────────────────────────────────────────
  # Scenario 5: Fallback flag propagates through the full orchestrator
  # ─────────────────────────────────────────────────────────────────────────
  Scenario: Fallback flag is present in PipelineResult and score_computed audit event
    Given the primary LLM backend is OpenAI configured with max_retries 3
    And the OpenAI client raises RateLimitError on every attempt
    And the fallback LLM backend is Anthropic and returns a valid rubric score
    And a FallbackLLMBackend is wired with OpenAI as primary and Anthropic as fallback
    And the pipeline orchestrator uses this FallbackLLMBackend for rubric scoring
    When the full pipeline runs for Alice's application
    Then the PipelineResult has is_evaluated_via_fallback set to True
    And the "score_computed" audit event contains is_evaluated_via_fallback true

  # ─────────────────────────────────────────────────────────────────────────
  # Scenario 6: make_rubric_backend() wires FallbackLLMBackend from env vars
  # ─────────────────────────────────────────────────────────────────────────
  Scenario: Factory function auto-wires fallback chain from environment variables
    Given the environment variable LLM_BACKEND is set to "openai"
    And the environment variable LLM_BACKEND_FALLBACK is set to "anthropic"
    When make_rubric_backend() is called with no arguments
    Then the returned backend is a FallbackLLMBackend
    And its primary provider model_name contains "gpt"
    And its fallback provider model_name contains "claude"
