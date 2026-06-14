"""
M3: LLM Rubric Scoring — Stage 3.

Architecture
────────────
┌──────────────────────────┐
│  LLMBackendProtocol      │  Structural subtyping — any object with
│  .complete(sys, user)    │  .complete() and .model_name satisfies it.
│  .model_name             │
└──────────────────────────┘
          │
          ▼
┌──────────────────────────┐
│  RubricEvaluator         │  Implements RubricEvaluatorProtocol.
│  .evaluate(resume, reqs) │  Builds prompts → LLM → parses JSON → scores.
└──────────────────────────┘
          │
          ▼
┌──────────────────────────┐
│  RubricResult            │  normalized_score, evidence_quality,
│                          │  criterion_scores (from rubric_protocol.py)
└──────────────────────────┘

Scoring formulas
────────────────
  normalized_score = sum(RUBRIC_WEIGHTS[c] * raw_scores[c] for c in CRITERIA) / 5.0

  evidence_quality = (number of criteria where len(justification.split()) >= 10) / 5

  Raw scores clamped to [1.0, 5.0] before normalization.

Fallback on parse failure
─────────────────────────
  FALLBACK_SCORE = 3.0 for all criteria.
  normalized_score = 3.0 / 5.0 = 0.60.
  evidence_quality = 0.0 (no justifications available).

Note: normalized_score = 0.70 when all criteria = 3.5 — matches StubRubricEvaluator.DEFAULT_NORMALIZED_SCORE.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol, Union, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from resume_pipeline.pipeline.rubric_protocol import RubricEvaluatorProtocol, RubricResult


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RUBRIC_WEIGHTS: dict[str, float] = {
    "core_skills": 0.30,
    "relevant_experience": 0.30,
    "scope_impact": 0.20,
    "domain_alignment": 0.10,
    "education_certs": 0.10,
}

CRITERIA: list[str] = list(RUBRIC_WEIGHTS.keys())

# Score assigned to all criteria when LLM response cannot be parsed.
FALLBACK_SCORE: float = 3.0

# Minimum word count for a justification to count toward evidence_quality.
_MIN_JUSTIFICATION_WORDS: int = 10


# ---------------------------------------------------------------------------
# LLM Backend Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMBackendProtocol(Protocol):
    """
    Interface for any LLM inference backend.

    The rubric evaluator depends on this protocol, not on a concrete
    provider. Swap MockLLMBackend → OpenAIBackend → AnthropicBackend
    without changing the evaluator.
    """

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return the model's text completion for the given prompts."""
        ...

    @property
    def model_name(self) -> str:
        """Identifier of the model being used."""
        ...


# ---------------------------------------------------------------------------
# Mock LLM Backend — for tests
# ---------------------------------------------------------------------------

class MockLLMBackend:
    """
    Deterministic LLM backend for unit tests.

    Returns a pre-configured response and records the last prompts
    passed to it so tests can assert on prompt content.
    """

    _MODEL_NAME: str = "mock-llm-v1"

    def __init__(self, response: str = "") -> None:
        self._response = response
        self.last_system_prompt: str | None = None
        self.last_user_prompt: str | None = None
        self.call_count: int = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        self.call_count += 1
        return self._response

    @property
    def model_name(self) -> str:
        return self._MODEL_NAME


# ---------------------------------------------------------------------------
# Pydantic schema — enforced by instructor on real backends
# ---------------------------------------------------------------------------

class RubricScoreResponse(BaseModel):
    """
    Strict schema for LLM rubric output. Enforced by instructor on real
    backends; used by the evaluator's _parse_response() to detect structured
    output vs raw JSON strings.

    Validation rules:
      - All five criteria must appear in `scores`.
      - Each score must be an integer in [1, 5].
    """

    scores: dict[str, int] = Field(
        description="Raw scores 1-5 for each criterion"
    )
    justifications: dict[str, str] = Field(
        default_factory=dict,
        description="Per-criterion evidence citation from the resume",
    )

    @model_validator(mode="after")
    def validate_criteria(self) -> "RubricScoreResponse":
        required = set(CRITERIA)
        missing = required - set(self.scores.keys())
        if missing:
            raise ValueError(f"Missing criteria in scores: {missing}")
        for k, v in self.scores.items():
            if not (1 <= v <= 5):
                raise ValueError(f"Score for '{k}' must be 1-5, got {v}")
        return self


# ---------------------------------------------------------------------------
# Real LLM Backends (lazy-imported — openai/anthropic not required at import)
# ---------------------------------------------------------------------------

class OpenAIRubricBackend:
    """
    Production backend using instructor + openai with tenacity retry.

    All third-party imports (instructor, openai, tenacity) are deferred to
    complete() so this class is instantiable without those packages installed.
    Tests bypass __init__ via __new__ and inject a mock _client directly.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_retries: int = 3,
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        self._client = None  # lazily created on first complete() call

    def _get_client(self):
        if self._client is None:
            import instructor
            import openai
            self._client = instructor.from_openai(openai.OpenAI())
        return self._client

    def complete(self, system_prompt: str, user_prompt: str) -> RubricScoreResponse:
        import openai
        import tenacity

        client = self._get_client()

        @tenacity.retry(
            stop=tenacity.stop_after_attempt(self._max_retries),
            wait=tenacity.wait_exponential(multiplier=1, min=2, max=20),
            retry=tenacity.retry_if_exception_type((
                openai.RateLimitError,
                openai.APITimeoutError,
                openai.APIConnectionError,
            )),
            reraise=True,
        )
        def _call() -> RubricScoreResponse:
            return client.chat.completions.create(
                model=self._model,
                response_model=RubricScoreResponse,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

        return _call()

    @property
    def model_name(self) -> str:
        return self._model


class AnthropicRubricBackend:
    """
    Production backend using instructor + anthropic with tenacity retry.

    Drop-in alternative to OpenAIRubricBackend. Same lazy-import pattern.
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        max_retries: int = 3,
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        self._client = None  # lazily created on first complete() call

    def _get_client(self):
        if self._client is None:
            import anthropic
            import instructor
            self._client = instructor.from_anthropic(anthropic.Anthropic())
        return self._client

    def complete(self, system_prompt: str, user_prompt: str) -> RubricScoreResponse:
        import tenacity

        client = self._get_client()

        @tenacity.retry(
            stop=tenacity.stop_after_attempt(self._max_retries),
            wait=tenacity.wait_exponential(multiplier=1, min=2, max=20),
            retry=tenacity.retry_if_exception_type(Exception),
            reraise=True,
        )
        def _call() -> RubricScoreResponse:
            return client.messages.create(
                model=self._model,
                response_model=RubricScoreResponse,
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

        return _call()

    @property
    def model_name(self) -> str:
        return self._model


# ---------------------------------------------------------------------------
# Backend factory — env-var driven
# ---------------------------------------------------------------------------

def make_rubric_backend(
    backend: str | None = None,
) -> "LLMBackendProtocol":
    """
    Instantiate the correct LLM backend.

    Priority: explicit `backend` argument → LLM_BACKEND env var → "mock".

    Args:
        backend: "openai" | "anthropic" | "mock" (or None to read env var)

    Returns:
        An object satisfying LLMBackendProtocol.
    """
    choice = backend or os.environ.get("LLM_BACKEND", "mock")
    if choice == "openai":
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return OpenAIRubricBackend(model=model)
    if choice == "anthropic":
        model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        return AnthropicRubricBackend(model=model)
    return MockLLMBackend("")


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

_RUBRIC_SYSTEM_PROMPT: str = """\
You are an expert technical recruiter evaluating a candidate's resume against a job description.

Score the candidate on each of the following competency criteria using a scale of 1 to 5:
  1 = Does not meet expectations
  2 = Partially meets expectations
  3 = Meets expectations
  4 = Exceeds expectations
  5 = Strongly exceeds expectations

Criteria:
  - core_skills: Proficiency in the core technical skills listed in the job requirements.
  - relevant_experience: Depth and relevance of professional experience to the role.
  - scope_impact: Evidence of owning projects, leading initiatives, or delivering measurable impact.
  - domain_alignment: Familiarity with the domain, industry, or problem space of the role.
  - education_certs: Relevant educational background and professional certifications.

Return ONLY a JSON object in the following format (no prose, no markdown fences):
{
  "scores": {
    "core_skills": <integer 1-5>,
    "relevant_experience": <integer 1-5>,
    "scope_impact": <integer 1-5>,
    "domain_alignment": <integer 1-5>,
    "education_certs": <integer 1-5>
  },
  "justifications": {
    "core_skills": "<one or two sentences citing specific evidence from the resume>",
    "relevant_experience": "<one or two sentences citing specific evidence from the resume>",
    "scope_impact": "<one or two sentences citing specific evidence from the resume>",
    "domain_alignment": "<one or two sentences citing specific evidence from the resume>",
    "education_certs": "<one or two sentences citing specific evidence from the resume>"
  }
}
"""


def _build_user_prompt(resume_parsed: dict, job_requirements: dict) -> str:
    """Format resume and job requirements into the LLM user prompt."""
    resume_text = json.dumps(resume_parsed, indent=2)
    req_text = json.dumps(job_requirements, indent=2)
    return (
        f"Resume:\n{resume_text}\n\n"
        f"Job Requirements:\n{req_text}\n\n"
        "Evaluate the candidate against the rubric. Return JSON only."
    )


# ---------------------------------------------------------------------------
# Test helper — build a valid LLM response JSON string
# ---------------------------------------------------------------------------

def build_llm_response(scores: dict[str, float], justifications: dict[str, str]) -> str:
    """
    Build a JSON response string in the format the evaluator expects.

    Used by tests to construct deterministic LLM outputs.
    """
    return json.dumps({"scores": scores, "justifications": justifications})


# ---------------------------------------------------------------------------
# RubricEvaluator
# ---------------------------------------------------------------------------

class RubricEvaluator:
    """
    Stage 3: Evaluates a resume against a role's rubric using an LLM.

    Implements RubricEvaluatorProtocol — satisfies structural subtyping;
    no explicit inheritance needed.

    Args:
        llm_backend: Any object implementing LLMBackendProtocol.
    """

    def __init__(self, llm_backend: LLMBackendProtocol) -> None:
        self._llm = llm_backend

    # -- RubricEvaluatorProtocol -----------------------------------------------

    def evaluate(self, resume_parsed: dict, job_requirements: dict) -> RubricResult:
        """
        Evaluate a candidate resume against job requirements via LLM.

        Steps:
          1. Build system + user prompts.
          2. Call LLM backend.
          3. Parse JSON response (fallback to FALLBACK_SCORE on failure).
          4. Score: normalize, clamp, compute evidence quality.

        Returns:
            RubricResult with normalized_score ∈ [0, 1], evidence_quality ∈ [0, 1],
            and criterion_scores (raw, clamped to [1, 5]) for all criteria.
        """
        system_prompt = _RUBRIC_SYSTEM_PROMPT
        user_prompt = _build_user_prompt(resume_parsed, job_requirements)
        raw_response = self._llm.complete(system_prompt, user_prompt)
        parsed = self._parse_response(raw_response)
        return self._score(parsed)

    # -- Internal helpers -------------------------------------------------------

    def _parse_response(self, raw: "str | RubricScoreResponse") -> dict:
        """
        Parse the LLM's response into a dict with 'scores' and 'justifications'.

        Handles three cases:
          - RubricScoreResponse object (from real instructor-backed backends) → unwrap directly
          - Plain JSON string (from MockLLMBackend in tests) → parse
          - JSON wrapped in ``` or ```json markdown fences → strip then parse
          - Malformed / empty string → fallback dict (FALLBACK_SCORE for all)
        """
        # Real backends (instructor) return a validated Pydantic object directly.
        if isinstance(raw, RubricScoreResponse):
            return {
                "scores": dict(raw.scores),
                "justifications": dict(raw.justifications),
            }

        text = raw.strip()
        if not text:
            return self._fallback_parsed()

        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        text = re.sub(r"^```[a-z]*\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

        try:
            data = json.loads(text)
            # Ensure both keys exist at the top level.
            if "scores" not in data:
                data["scores"] = {}
            if "justifications" not in data:
                data["justifications"] = {}
            return data
        except (json.JSONDecodeError, ValueError):
            return self._fallback_parsed()

    def _score(self, parsed: dict) -> RubricResult:
        """
        Compute RubricResult from a parsed LLM response dict.

        Normalization: weighted_sum / 5.0  (maps [1,5] → [0.2, 1.0])
        Evidence quality: fraction of criteria with >= 10 words in justification.
        """
        raw_scores_input: dict = parsed.get("scores", {})
        justifications: dict = parsed.get("justifications", {})

        # Clamp each criterion's raw score to [1.0, 5.0].
        criterion_scores: dict[str, float] = {}
        for criterion in CRITERIA:
            raw = raw_scores_input.get(criterion, FALLBACK_SCORE)
            try:
                clamped = max(1.0, min(5.0, float(raw)))
            except (TypeError, ValueError):
                clamped = FALLBACK_SCORE
            criterion_scores[criterion] = clamped

        # Weighted average, normalized to [0, 1].
        weighted_sum = sum(RUBRIC_WEIGHTS[c] * criterion_scores[c] for c in CRITERIA)
        normalized_score = weighted_sum / 5.0

        # Evidence quality: proportion of criteria with substantive justification.
        substantive_count = sum(
            1
            for c in CRITERIA
            if len(justifications.get(c, "").split()) >= _MIN_JUSTIFICATION_WORDS
        )
        evidence_quality = substantive_count / len(CRITERIA)

        return RubricResult(
            normalized_score=normalized_score,
            evidence_quality=evidence_quality,
            criterion_scores=criterion_scores,
        )

    @staticmethod
    def _fallback_parsed() -> dict:
        """Return a fallback response dict used when LLM output cannot be parsed."""
        return {
            "scores": {c: FALLBACK_SCORE for c in CRITERIA},
            "justifications": {c: "" for c in CRITERIA},
        }
