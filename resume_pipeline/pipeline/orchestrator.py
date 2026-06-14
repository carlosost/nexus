"""
Pipeline Orchestrator — wires all four stages into a single run() call.

Execution flow:
    ┌──────────────┐
    │  Stage 1     │  HardGateEvaluator
    │  Hard Gate   │─── FAIL ──────────────────────────→ PipelineResult(score=0)
    └──────┬───────┘
           │ PASS / UNKNOWN
           ▼
    ┌──────────────┐
    │  Stage 2     │  SemanticMatchEvaluator
    │  Semantic    │
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │  Stage 3     │  RubricEvaluatorProtocol (real or stub)
    │  Rubric      │
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │  Stage 4     │  FinalScoreCalculator
    │  Final Score │
    └──────────────┘

Design constraints:
  - All evaluators are injected at construction — no module-level singletons
    instantiated inside the orchestrator, making it trivially mockable.
  - Observability is injected; the default is the process-level singleton.
  - Audit logging uses the process-level singleton (audit_logger) — audit events
    are global concerns, not scoped to a single run.
  - The orchestrator does NOT persist to the database. Persistence is the
    caller's responsibility (e.g., a Django view or a Celery task).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from resume_pipeline.logging_module import audit_logger
from resume_pipeline.observability import PipelineObservability, pipeline_observability
from resume_pipeline.pipeline.final_score import FinalScoreCalculator
from resume_pipeline.pipeline.hard_gate import GateOutcome, HardGateEvaluator
from resume_pipeline.pipeline.rubric_protocol import (
    RubricEvaluatorProtocol,
    RubricResult,
    StubRubricEvaluator,
)
from resume_pipeline.pipeline.rubric_score import RubricEvaluator, make_rubric_backend
from resume_pipeline.pipeline.semantic_match import SemanticMatchEvaluator, SemanticMatchScore


# ---------------------------------------------------------------------------
# Confidence constants
# ---------------------------------------------------------------------------

#: Confidence when the gate passed with all criteria confirmed.
CONFIDENCE_GATE_PASS: float = 1.0

#: Confidence when the gate outcome was UNKNOWN (some criteria unresolvable).
#: Surfaced to human reviewers to indicate the score warrants scrutiny.
CONFIDENCE_GATE_UNKNOWN: float = 0.70


# ---------------------------------------------------------------------------
# Input / Output data classes
# ---------------------------------------------------------------------------

@dataclass
class PipelineInput:
    """
    Everything the orchestrator needs to run all four stages.

    Produced by the caller (view, task, test) from Django model instances.
    Keeping this a plain dataclass means the orchestrator has no ORM imports.
    """
    application_id: str
    job_must_haves: dict
    resume_parsed: dict
    candidate_embeddings: dict[str, list[float]]
    job_embeddings: dict[str, list[float]]
    lexical_rank: Optional[int]
    semantic_rank: Optional[int]
    job_requirements: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    """
    Complete output from one orchestrator run.

    Callers persist this to the DB (HardGateResult, SemanticMatchResult,
    RubricScore, FinalScore models) and enqueue for human review if needed.
    """
    application_id: str
    gate_outcome: GateOutcome
    gate_criterion_results: list
    gate_passed: bool

    # Populated by Stage 2 (None if short-circuited).
    semantic_score: Optional[float]
    semantic_section_scores: Optional[dict[str, float]]

    # Populated by Stage 3 (None if short-circuited).
    rubric_score: Optional[float]
    evidence_quality: Optional[float]
    rubric_criterion_scores: Optional[dict[str, float]]

    # Stage 4 output — always present.
    final_score: float

    # Meta
    stages_executed: list[str]
    total_latency_ms: float
    confidence: Optional[float]

    # LLM resilience — True when primary provider failed and fallback was used.
    # Callers should persist this to RubricScore.is_evaluated_via_fallback
    # so the reviewer UI can surface a visual alert.
    is_evaluated_via_fallback: bool = False


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class PipelineOrchestrator:
    """
    Executes the 4-stage pipeline for a single candidate-job application.

    Args:
        gate_evaluator:    Stage 1. Defaults to HardGateEvaluator().
        semantic_evaluator: Stage 2. Defaults to SemanticMatchEvaluator().
        rubric_evaluator:  Stage 3. Any object satisfying RubricEvaluatorProtocol.
                           Defaults to StubRubricEvaluator() until M3 is complete.
        final_score_calc:  Stage 4. Defaults to FinalScoreCalculator().
        observability:     Latency tracking. Defaults to process-level singleton.
    """

    def __init__(
        self,
        gate_evaluator=None,
        semantic_evaluator=None,
        rubric_evaluator: Optional[RubricEvaluatorProtocol] = None,
        final_score_calc: Optional[FinalScoreCalculator] = None,
        observability: Optional[PipelineObservability] = None,
    ) -> None:
        self._gate = gate_evaluator or HardGateEvaluator()
        self._semantic = semantic_evaluator or SemanticMatchEvaluator()
        # Default: real LLM backend selected by LLM_BACKEND env var (falls back to mock).
        # Tests inject their own mock via the rubric_evaluator parameter.
        self._rubric = rubric_evaluator or RubricEvaluator(make_rubric_backend())
        self._final_score = final_score_calc or FinalScoreCalculator()
        self._obs = observability or pipeline_observability

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, pipeline_input: PipelineInput) -> PipelineResult:
        """
        Execute the pipeline for one application.

        Args:
            pipeline_input: Fully populated PipelineInput.

        Returns:
            PipelineResult with all stage outputs and metadata.
        """
        app_id = pipeline_input.application_id
        stages_executed: list[str] = []
        run_start = time.perf_counter()

        # ── Stage 1: Hard Gate ──────────────────────────────────────────
        gate_evaluation = self._timed(
            "hard_gate",
            lambda: self._gate.evaluate(
                must_haves=pipeline_input.job_must_haves,
                resume_parsed=pipeline_input.resume_parsed,
            ),
            metadata={"application_id": app_id},
        )
        stages_executed.append("hard_gate")

        # Log each criterion transition.
        for criterion_result in gate_evaluation.criterion_results:
            audit_logger.log_gate_transition(
                application_id=app_id,
                criterion=criterion_result.name,
                new_outcome=criterion_result.outcome.value,
                evidence=criterion_result.evidence,
            )

        # ── Short-circuit on FAIL ───────────────────────────────────────
        if gate_evaluation.outcome == GateOutcome.FAIL:
            audit_logger.log_pipeline_short_circuited(
                application_id=app_id,
                gate_outcome=gate_evaluation.outcome.value,
                reason="Hard gate failed; remaining stages skipped",
            )
            total_ms = (time.perf_counter() - run_start) * 1000
            return PipelineResult(
                application_id=app_id,
                gate_outcome=GateOutcome.FAIL,
                gate_criterion_results=gate_evaluation.criterion_results,
                gate_passed=False,
                semantic_score=None,
                semantic_section_scores=None,
                rubric_score=None,
                evidence_quality=None,
                rubric_criterion_scores=None,
                final_score=0.0,
                stages_executed=stages_executed,
                total_latency_ms=round(total_ms, 3),
                confidence=0.0,
            )

        # ── Stage 2: Semantic Match ─────────────────────────────────────
        semantic_result: SemanticMatchScore = self._timed(
            "semantic_match",
            lambda: self._semantic.evaluate(
                candidate_embeddings=pipeline_input.candidate_embeddings,
                job_embeddings=pipeline_input.job_embeddings,
                lexical_rank=pipeline_input.lexical_rank,
                semantic_rank=pipeline_input.semantic_rank,
            ),
            metadata={"application_id": app_id},
        )
        stages_executed.append("semantic_match")

        # ── Stage 3: Rubric Scoring ─────────────────────────────────────
        rubric_result: RubricResult = self._timed(
            "rubric",
            lambda: self._rubric.evaluate(
                resume_parsed=pipeline_input.resume_parsed,
                job_requirements=pipeline_input.job_requirements,
            ),
            metadata={"application_id": app_id},
        )
        stages_executed.append("rubric")

        # ── Stage 4: Final Score ────────────────────────────────────────
        final_score = self._final_score.calculate(
            gate_outcome=gate_evaluation.outcome,
            semantic_match=semantic_result.final_score,
            rubric_score_norm=rubric_result.normalized_score,
            evidence_quality=rubric_result.evidence_quality,
        )

        # Confidence: reduced when gate was UNKNOWN.
        confidence = (
            CONFIDENCE_GATE_PASS
            if gate_evaluation.outcome == GateOutcome.PASS
            else CONFIDENCE_GATE_UNKNOWN
        )

        # Capture the backend model name if the rubric evaluator exposes it.
        rubric_llm = getattr(self._rubric, "_llm", None)
        rubric_model_name = (
            rubric_llm.model_name
            if rubric_llm is not None
            else getattr(self._rubric, "model_name", "unknown")
        )

        # LLM resilience — did a fallback provider complete this evaluation?
        is_evaluated_via_fallback = rubric_result.is_evaluated_via_fallback

        audit_logger.log_score_computed(
            application_id=app_id,
            final_score=final_score,
            gate_passed=(gate_evaluation.outcome == GateOutcome.PASS),
            semantic_match=semantic_result.final_score,
            rubric_score_norm=rubric_result.normalized_score,
            evidence_quality=rubric_result.evidence_quality,
            confidence=confidence,
            model_name=rubric_model_name,
            is_evaluated_via_fallback=is_evaluated_via_fallback,
        )

        total_ms = (time.perf_counter() - run_start) * 1000
        return PipelineResult(
            application_id=app_id,
            gate_outcome=gate_evaluation.outcome,
            gate_criterion_results=gate_evaluation.criterion_results,
            gate_passed=(gate_evaluation.outcome == GateOutcome.PASS),
            semantic_score=semantic_result.final_score,
            semantic_section_scores=semantic_result.section_scores,
            rubric_score=rubric_result.normalized_score,
            evidence_quality=rubric_result.evidence_quality,
            rubric_criterion_scores=rubric_result.criterion_scores,
            final_score=final_score,
            stages_executed=stages_executed,
            total_latency_ms=round(total_ms, 3),
            confidence=confidence,
            is_evaluated_via_fallback=is_evaluated_via_fallback,
        )

    # ------------------------------------------------------------------
    # Internal timing helper
    # ------------------------------------------------------------------

    def _timed(self, stage_name: str, fn, metadata: Optional[dict] = None):
        """
        Execute fn(), record a LatencyRecord, and return the result.

        We use this instead of @instrument because the evaluators are
        injected mocks in tests — decorating the mock's method would
        shadow the mock and break call assertions.
        """
        start = time.perf_counter()
        result = fn()
        elapsed_ms = (time.perf_counter() - start) * 1000

        from resume_pipeline.observability import LatencyRecord
        record = LatencyRecord(
            stage=stage_name,
            latency_ms=round(elapsed_ms, 3),
            metadata=metadata or {},
        )
        self._obs._records.append(record)
        self._obs._sink(record)

        return result
