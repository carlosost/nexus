"""
Pipeline and Review services — business logic extracted from views and commands.

PipelineService  — runs the 4-stage pipeline and persists results for one Application.
ReviewService    — processes human review decisions and transitions Application status.

ReviewService status transition table:
    approve       → Application.Status.APPROVED
    reject        → Application.Status.REJECTED
    override_pass → Application.Status.APPROVED  (+audit log)
    override_fail → Application.Status.REJECTED  (+audit log)
"""

from __future__ import annotations

import math
import os

from rest_framework.exceptions import ValidationError

from resume_pipeline.embeddings import EmbeddingClient, MockEmbeddingBackend
from resume_pipeline.logging_module import audit_logger
from resume_pipeline.observability import pipeline_observability
from resume_pipeline.pipeline.rubric_score import LLMBackendNotConfiguredError
from resume_pipeline.models import (
    Application,
    FinalScore,
    HardGateResult,
    HumanReview,
    RubricScore,
    SemanticMatchResult,
)
from resume_pipeline.pipeline.orchestrator import PipelineInput, PipelineOrchestrator

_SECTIONS = ["summary", "experience", "skills", "education", "certifications", "projects"]

_GATE_OUTCOME_TO_STATUS = {
    "fail":    Application.Status.GATE_FAILED,
    "unknown": Application.Status.GATE_UNKNOWN,
    "pass":    Application.Status.SCORED,
}


class PipelineService:
    """
    Runs the 4-stage evaluation pipeline for a single Application and
    persists all results to the database.

    Usage::

        service = PipelineService()
        result = service.run(application)
    """

    def __init__(self, orchestrator=None, embedding_client=None) -> None:
        self._orchestrator = orchestrator or PipelineOrchestrator()
        self._embedding_client = embedding_client or EmbeddingClient(
            backend=MockEmbeddingBackend(dim=1536)
        )
        backend = getattr(self._embedding_client, "_backend", None)
        audit_logger.log_pipeline_service_init(
            orchestrator_type=type(self._orchestrator).__name__,
            embedding_backend_type=type(backend).__name__ if backend else "unknown",
            embedding_dim=getattr(backend, "_dim", None),
        )

    def run(self, application: Application) -> dict:
        """
        Execute the pipeline for the given application and persist the results.

        Returns a summary dict suitable for serialising directly in an API response.
        """
        application_id = str(application.id)
        candidate = application.candidate
        job = application.job

        audit_logger.log_pipeline_started(
            application_id=application_id,
            job_id=str(application.job_id),
            candidate_id=str(application.candidate_id),
        )

        # ── Log raw input shape before any computation ────────────────────────
        resume_sections_chars = {
            s: len(str(candidate.resume_parsed[s]))
            for s in candidate.resume_parsed
            if candidate.resume_parsed.get(s)
        }
        job_req_keys_chars = {
            k: len(str(v))
            for k, v in job.requirements_raw.items()
        } if job.requirements_raw else {}

        audit_logger.log_pipeline_input_prepared(
            application_id=application_id,
            job_title=job.title,
            resume_sections=resume_sections_chars,
            job_requirement_keys=job_req_keys_chars,
            must_haves_count=len(job.must_haves) if job.must_haves else 0,
        )

        # ── Embedding build ───────────────────────────────────────────────────
        try:
            with pipeline_observability.timed("pipeline_embedding_build", application_id=application_id):
                candidate_embeddings = {
                    s: self._embedding_client.embed(str(candidate.resume_parsed[s]))
                    for s in _SECTIONS
                    if candidate.resume_parsed.get(s)
                }
                job_embeddings = {
                    s: self._embedding_client.embed(str(job.requirements_raw.get(s, job.description)))
                    for s in _SECTIONS
                    if job.requirements_raw.get(s) or job.description
                }
        except Exception as exc:
            audit_logger.log_pipeline_exception(
                application_id=application_id,
                stage="embedding_build",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            raise

        first_vec = next(iter(candidate_embeddings.values()), None)
        first_vec_dim  = len(first_vec) if first_vec is not None else 0
        first_vec_norm = math.sqrt(sum(x * x for x in first_vec)) if first_vec else 0.0
        first_vec_sample = first_vec[:5] if first_vec else []

        def _norm(v: list[float]) -> float:
            return round(math.sqrt(sum(x * x for x in v)), 6)

        audit_logger.log_pipeline_embeddings_built(
            application_id=application_id,
            candidate_sections=list(candidate_embeddings.keys()),
            job_sections=list(job_embeddings.keys()),
            embedding_dim=first_vec_dim,
        )
        audit_logger.log_pipeline_embedding_stats(
            application_id=application_id,
            candidate_section_norms={s: _norm(v) for s, v in candidate_embeddings.items()},
            job_section_norms={s: _norm(v) for s, v in job_embeddings.items()},
            first_vec_dim=first_vec_dim,
            first_vec_norm=first_vec_norm,
            first_vec_sample=first_vec_sample,
        )

        pipeline_input = PipelineInput(
            application_id=application_id,
            job_must_haves=job.must_haves,
            resume_parsed=candidate.resume_parsed,
            candidate_embeddings=candidate_embeddings,
            job_embeddings=job_embeddings,
            lexical_rank=None,
            semantic_rank=None,
            job_requirements=job.requirements_raw,
        )

        # ── Orchestrator run ──────────────────────────────────────────────────
        try:
            with pipeline_observability.timed("pipeline_orchestrator_run", application_id=application_id):
                result = self._orchestrator.run(pipeline_input)
        except LLMBackendNotConfiguredError as exc:
            audit_logger.log_llm_not_configured(
                configured_backend=os.environ.get("LLM_BACKEND", "mock"),
                application_id=application_id,
                message=str(exc),
            )
            raise
        except Exception as exc:
            audit_logger.log_pipeline_exception(
                application_id=application_id,
                stage="orchestrator_run",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            raise

        audit_logger.log_pipeline_gate_result(
            application_id=application_id,
            gate_outcome=result.gate_outcome.value,
            gate_passed=result.gate_passed,
            criterion_results=[
                {"name": cr.name, "outcome": cr.outcome.value, "evidence": cr.evidence}
                for cr in result.gate_criterion_results
            ],
        )

        if result.gate_passed:
            audit_logger.log_pipeline_semantic_result(
                application_id=application_id,
                semantic_score=result.semantic_score,
                section_scores=result.semantic_section_scores or {},
            )
            audit_logger.log_pipeline_rubric_result(
                application_id=application_id,
                rubric_score=result.rubric_score,
                criterion_scores=result.rubric_criterion_scores or {},
                evidence_quality=result.evidence_quality,
            )

        if not result.gate_passed:
            audit_logger.log_pipeline_short_circuited(
                application_id=application_id,
                gate_outcome=result.gate_outcome.value,
                reason="Hard gate criteria not met",
            )

        audit_logger.log_score_computed(
            application_id=application_id,
            final_score=result.final_score,
            gate_passed=result.gate_passed,
            semantic_match=result.semantic_score,
            rubric_score_norm=result.rubric_score,
            evidence_quality=result.evidence_quality,
            confidence=result.confidence,
            model_name=os.environ.get("LLM_BACKEND", "mock"),
        )

        # ── Persist ───────────────────────────────────────────────────────────
        try:
            with pipeline_observability.timed("pipeline_persist", application_id=application_id):
                self._persist(application, result)
        except Exception as exc:
            audit_logger.log_pipeline_exception(
                application_id=application_id,
                stage="persist",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            raise

        audit_logger.log_pipeline_persisted(
            application_id=application_id,
            gate_outcome=result.gate_outcome.value,
            gate_passed=result.gate_passed,
            stages_persisted=result.stages_executed,
            new_status=str(application.status),
        )

        audit_logger.log_pipeline_completed(
            application_id=application_id,
            gate_outcome=result.gate_outcome.value,
            gate_passed=result.gate_passed,
            final_score=result.final_score,
            stages_executed=result.stages_executed,
            latency_ms=result.total_latency_ms,
        )

        return {
            "application_id": application_id,
            "gate_outcome": result.gate_outcome.value,
            "gate_passed": result.gate_passed,
            "gate_criterion_results": [
                {"name": cr.name, "outcome": cr.outcome.value, "evidence": cr.evidence}
                for cr in result.gate_criterion_results
            ],
            "semantic_score": result.semantic_score,
            "rubric_score": result.rubric_score,
            "evidence_quality": result.evidence_quality,
            "final_score": result.final_score,
            "confidence": result.confidence,
            "stages_executed": result.stages_executed,
            "latency_ms": result.total_latency_ms,
            "status": application.status,
        }

    def _persist(self, application: Application, result) -> None:
        HardGateResult.objects.filter(application=application).delete()
        HardGateResult.objects.create(
            application=application,
            outcome=result.gate_outcome.value,
            criterion_results={
                cr.name: {"outcome": cr.outcome.value, "evidence": cr.evidence}
                for cr in result.gate_criterion_results
            },
            latency_ms=result.total_latency_ms,
        )

        if result.gate_passed:
            SemanticMatchResult.objects.filter(application=application).delete()
            SemanticMatchResult.objects.create(
                application=application,
                rrf_score=result.semantic_score,
                section_scores=result.semantic_section_scores or {},
                lexical_rank=None,
                semantic_rank=None,
                latency_ms=0.0,
            )

            crit = result.rubric_criterion_scores or {}
            RubricScore.objects.filter(application=application).delete()
            RubricScore.objects.create(
                application=application,
                core_skills=crit.get("core_skills", 3.0),
                relevant_experience=crit.get("relevant_experience", 3.0),
                scope_impact=crit.get("scope_impact", 3.0),
                domain_alignment=crit.get("domain_alignment", 3.0),
                education_certs=crit.get("education_certs", 3.0),
                normalized_score=result.rubric_score,
                evidence_quality=result.evidence_quality,
                model_name=os.environ.get("LLM_BACKEND", "mock"),
                latency_ms=0.0,
            )

        FinalScore.objects.filter(application=application).delete()
        FinalScore.objects.create(
            application=application,
            score=result.final_score,
            gate_passed=result.gate_passed,
            confidence=result.confidence,
        )

        application.status = _GATE_OUTCOME_TO_STATUS[result.gate_outcome.value]
        application.save(update_fields=["status", "updated_at"])

# Decisions that require a non-empty reason (last line of defence after
# serializer validation — guards against direct service calls from tasks/admin).
_OVERRIDE_DECISIONS = {
    HumanReview.Decision.OVERRIDE_PASS,
    HumanReview.Decision.OVERRIDE_FAIL,
}

# Maps each decision to the resulting application status.
_DECISION_TO_STATUS: dict[str, str] = {
    HumanReview.Decision.APPROVE: Application.Status.APPROVED,
    HumanReview.Decision.REJECT: Application.Status.REJECTED,
    HumanReview.Decision.OVERRIDE_PASS: Application.Status.APPROVED,
    HumanReview.Decision.OVERRIDE_FAIL: Application.Status.REJECTED,
}


class ReviewService:
    """
    Processes a human review decision against an application.

    Usage::

        service = ReviewService()
        service.process_review(application, human_review)
    """

    def process_review(self, application, review) -> None:
        """
        Apply a review decision to an application.

        Args:
            application: An Application model instance (or duck-typed mock).
            review: A HumanReview model instance (or duck-typed mock).

        Raises:
            ValidationError: If an override decision is submitted without a
                             non-empty, non-whitespace reason.
        """
        decision = review.decision
        reason = (review.override_reason or "").strip()

        # Guard: override decisions must have a reason even if the serializer
        # is bypassed (e.g., admin action, management command, task).
        if decision in _OVERRIDE_DECISIONS and not reason:
            raise ValidationError(
                {
                    "override_reason": (
                        f"A non-empty reason is required for '{decision}' decisions."
                    )
                }
            )

        # Apply status transition.
        new_status = _DECISION_TO_STATUS[decision]
        application.status = new_status
        application.save(update_fields=["status", "updated_at"])

        # Emit audit event for override decisions only.
        if decision in _OVERRIDE_DECISIONS:
            audit_logger.log_human_override(
                application_id=str(application.id),
                reviewer_email=review.reviewer_email,
                ai_score=review.ai_score_at_review,
                decision=decision,
                reason=reason,
                confidence_at_review=getattr(review, "confidence_at_review", None),
            )
