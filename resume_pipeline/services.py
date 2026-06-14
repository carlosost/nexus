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

import os

from rest_framework.exceptions import ValidationError

from resume_pipeline.embeddings import EmbeddingClient, MockEmbeddingBackend
from resume_pipeline.logging_module import audit_logger
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

    def run(self, application: Application) -> dict:
        """
        Execute the pipeline for the given application and persist the results.

        Returns a summary dict suitable for serialising directly in an API response.
        """
        candidate = application.candidate
        job = application.job

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

        pipeline_input = PipelineInput(
            application_id=str(application.id),
            job_must_haves=job.must_haves,
            resume_parsed=candidate.resume_parsed,
            candidate_embeddings=candidate_embeddings,
            job_embeddings=job_embeddings,
            lexical_rank=None,
            semantic_rank=None,
            job_requirements=job.requirements_raw,
        )

        result = self._orchestrator.run(pipeline_input)
        self._persist(application, result)

        return {
            "application_id": str(application.id),
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
