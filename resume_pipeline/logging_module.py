"""
Centralized Audit Logging Module.

Captures hard-gate state transitions, LLM override events, human override
decisions, and final score computations as structured JSON log lines.

Every entry is machine-parseable by log aggregators (Loki, Splunk, CloudWatch).

Usage::

    from resume_pipeline.logging_module import audit_logger

    audit_logger.log_gate_transition(
        application_id=str(application.id),
        criterion="minimum_experience",
        previous_outcome=None,
        new_outcome="fail",
        evidence="Candidate has 3 years; required 5",
    )
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Event taxonomy
# ---------------------------------------------------------------------------

class AuditEventType(str, Enum):
    GATE_TRANSITION = "gate_transition"
    LLM_RUBRIC_SCORE = "llm_rubric_score"
    LLM_OVERRIDE = "llm_override"
    HUMAN_OVERRIDE = "human_override"
    SCORE_COMPUTED = "score_computed"
    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_SHORT_CIRCUITED = "pipeline_short_circuited"
    # M0.5 — Document ingestion events
    DOCUMENT_INGESTION_STARTED = "document_ingestion_started"
    DOCUMENT_PARSED = "document_parsed"
    PARSER_FALLBACK = "parser_fallback"
    DOCUMENT_PARSE_FAILED = "document_parse_failed"
    # LLM Resilience — provider failover events
    PRIMARY_LLM_FAILED = "primary_llm_failed"
    FALLBACK_LLM_ENGAGED = "fallback_llm_engaged"
    FALLBACK_LLM_SUCCEEDED = "fallback_llm_succeeded"
    FALLBACK_LLM_EXHAUSTED = "fallback_llm_exhausted"
    # Job ingestion events
    JOB_CREATE_STARTED = "job_create_started"
    JOB_CREATED = "job_created"
    JOB_CREATE_FAILED = "job_create_failed"
    # Candidate ingestion events
    CANDIDATE_CREATE_STARTED = "candidate_create_started"
    CANDIDATE_CREATED = "candidate_created"
    CANDIDATE_CREATE_FAILED = "candidate_create_failed"
    # Application lifecycle events
    APPLICATION_CREATE_STARTED = "application_create_started"
    APPLICATION_CREATED = "application_created"
    APPLICATION_ALREADY_EXISTS = "application_already_exists"
    APPLICATION_CREATE_FAILED = "application_create_failed"
    # Dashboard stats events
    DASHBOARD_STATS_FETCHED = "dashboard_stats_fetched"
    # Pipeline internals — step-level trace events
    PIPELINE_SERVICE_INIT     = "pipeline_service_init"
    PIPELINE_EMBEDDINGS_BUILT = "pipeline_embeddings_built"
    PIPELINE_GATE_RESULT      = "pipeline_gate_result"
    PIPELINE_SEMANTIC_RESULT  = "pipeline_semantic_result"
    PIPELINE_RUBRIC_RESULT    = "pipeline_rubric_result"
    PIPELINE_PERSISTED        = "pipeline_persisted"
    # RubricEvaluator internals
    RUBRIC_LLM_CALL_STARTED  = "rubric_llm_call_started"
    RUBRIC_LLM_CALL_FINISHED = "rubric_llm_call_finished"
    RUBRIC_RESPONSE_PARSED   = "rubric_response_parsed"
    RUBRIC_SCORED            = "rubric_scored"


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

class StructuredAuditLogger:
    """
    Emits structured JSON audit records to a named Python logger.

    In production, configure the underlying logger to write to a dedicated
    audit log file or stream separate from the application log, to simplify
    compliance queries.

    Args:
        name: Python logger name. Default: "pipeline.audit".
        level: Log level for emitted records. Default: logging.INFO.
    """

    def __init__(
        self,
        name: str = "pipeline.audit",
        level: int = logging.INFO,
    ) -> None:
        self._logger = logging.getLogger(name)
        # Explicitly set the logger level so INFO messages are not silently
        # dropped by a root logger configured at WARNING (common in test envs).
        self._logger.setLevel(level)
        self._level = level

    # ------------------------------------------------------------------
    # Pipeline lifecycle events
    # ------------------------------------------------------------------

    def log_pipeline_started(
        self,
        application_id: str,
        job_id: str,
        candidate_id: str,
    ) -> None:
        """Emitted at the start of a pipeline run before any stage executes."""
        self._emit(
            event_type=AuditEventType.PIPELINE_STARTED,
            payload={
                "application_id": application_id,
                "job_id": job_id,
                "candidate_id": candidate_id,
            },
        )

    def log_pipeline_completed(
        self,
        application_id: str,
        gate_outcome: str,
        gate_passed: bool,
        final_score: float,
        stages_executed: int,
        latency_ms: float,
    ) -> None:
        """Emitted after all stages finish and results are persisted."""
        self._emit(
            event_type=AuditEventType.PIPELINE_COMPLETED,
            payload={
                "application_id": application_id,
                "gate_outcome": gate_outcome,
                "gate_passed": gate_passed,
                "final_score": final_score,
                "stages_executed": stages_executed,
                "latency_ms": latency_ms,
            },
        )

    # ------------------------------------------------------------------
    # Hard Gate events
    # ------------------------------------------------------------------

    def log_gate_transition(
        self,
        application_id: str,
        criterion: str,
        new_outcome: str,
        *,
        previous_outcome: Optional[str] = None,
        evidence: Optional[str] = None,
    ) -> None:
        """
        Log a single criterion's gate evaluation result.

        Call once per criterion after evaluation, regardless of outcome.
        Captures state transitions for audit and downstream analytics.
        """
        self._emit(
            event_type=AuditEventType.GATE_TRANSITION,
            payload={
                "application_id": application_id,
                "criterion": criterion,
                "previous_outcome": previous_outcome,
                "new_outcome": new_outcome,
                "evidence": evidence,
            },
        )

    def log_pipeline_short_circuited(
        self,
        application_id: str,
        gate_outcome: str,
        reason: str,
    ) -> None:
        """Log when the pipeline stops early due to a gate FAIL."""
        self._emit(
            event_type=AuditEventType.PIPELINE_SHORT_CIRCUITED,
            payload={
                "application_id": application_id,
                "gate_outcome": gate_outcome,
                "reason": reason,
            },
        )

    # ------------------------------------------------------------------
    # LLM events
    # ------------------------------------------------------------------

    def log_llm_rubric_score(
        self,
        application_id: str,
        model_name: str,
        raw_scores: dict[str, float],
        normalized_score: float,
        evidence_quality: float,
        latency_ms: float,
    ) -> None:
        """Log an LLM rubric evaluation result."""
        self._emit(
            event_type=AuditEventType.LLM_RUBRIC_SCORE,
            payload={
                "application_id": application_id,
                "model_name": model_name,
                "raw_scores": raw_scores,
                "normalized_score": normalized_score,
                "evidence_quality": evidence_quality,
                "latency_ms": latency_ms,
            },
        )

    def log_llm_override(
        self,
        application_id: str,
        model_name: str,
        original_outcome: str,
        overridden_outcome: str,
        confidence: float,
        reason: str,
    ) -> None:
        """
        Log when LLM output diverges from heuristic baseline beyond threshold.

        This creates an auditable record that the pipeline's rubric scorer
        produced a result that differed meaningfully from the heuristic signal,
        and that the LLM output was used despite that discrepancy.
        """
        self._emit(
            event_type=AuditEventType.LLM_OVERRIDE,
            payload={
                "application_id": application_id,
                "model_name": model_name,
                "original_outcome": original_outcome,
                "overridden_outcome": overridden_outcome,
                "confidence": confidence,
                "reason": reason,
            },
        )

    # ------------------------------------------------------------------
    # Human review events
    # ------------------------------------------------------------------

    def log_human_override(
        self,
        application_id: str,
        reviewer_email: str,
        ai_score: float,
        decision: str,
        reason: str,
        *,
        confidence_at_review: Optional[float] = None,
    ) -> None:
        """
        Log a human reviewer's override decision.

        This is the primary audit trail for compliance: it records who,
        when, what the AI said, what the human decided, and why.
        """
        self._emit(
            event_type=AuditEventType.HUMAN_OVERRIDE,
            payload={
                "application_id": application_id,
                "reviewer_email": reviewer_email,
                "ai_score_at_review": ai_score,
                "confidence_at_review": confidence_at_review,
                "decision": decision,
                "reason": reason,
            },
        )

    # ------------------------------------------------------------------
    # Score events
    # ------------------------------------------------------------------

    def log_score_computed(
        self,
        application_id: str,
        final_score: float,
        gate_passed: bool,
        semantic_match: float,
        rubric_score_norm: float,
        evidence_quality: float,
        confidence: Optional[float] = None,
        model_name: Optional[str] = None,
        retry_count: Optional[int] = None,
        is_evaluated_via_fallback: bool = False,
    ) -> None:
        self._emit(
            event_type=AuditEventType.SCORE_COMPUTED,
            payload={
                "application_id": application_id,
                "final_score": final_score,
                "gate_passed": gate_passed,
                "component_scores": {
                    "semantic_match": semantic_match,
                    "rubric_score_norm": rubric_score_norm,
                    "evidence_quality": evidence_quality,
                },
                "confidence": confidence,
                "model_name": model_name,
                "retry_count": retry_count,
                "is_evaluated_via_fallback": is_evaluated_via_fallback,
            },
        )

    # ------------------------------------------------------------------
    # LLM Resilience — provider failover events
    # ------------------------------------------------------------------

    def log_primary_llm_failed(
        self,
        provider: str,
        error_type: str,
        error_message: str,
        retry_count: Optional[int] = None,
    ) -> None:
        """
        Emitted when the primary LLM provider raises after exhausting all
        tenacity retries. Signals imminent handoff to the fallback provider.

        Example JSON::

            {"event": "primary_llm_failed", "provider": "openai",
             "error_type": "RateLimitError", "retry_count": 3,
             "error_message": "rate limit exceeded"}
        """
        self._emit(
            event_type=AuditEventType.PRIMARY_LLM_FAILED,
            payload={
                "provider": provider,
                "error_type": error_type,
                "error_message": error_message,
                "retry_count": retry_count,
            },
        )

    def log_fallback_llm_engaged(
        self,
        primary_provider: str,
        target_provider: str,
    ) -> None:
        """
        Emitted the moment the fallback provider is about to be called.

        Example JSON::

            {"event": "fallback_llm_engaged", "primary_provider": "openai",
             "target_provider": "anthropic"}
        """
        self._emit(
            event_type=AuditEventType.FALLBACK_LLM_ENGAGED,
            payload={
                "primary_provider": primary_provider,
                "target_provider": target_provider,
            },
        )

    def log_fallback_llm_succeeded(
        self,
        provider: str,
    ) -> None:
        """
        Emitted when the fallback provider returns a valid completion.

        Example JSON::

            {"event": "fallback_llm_succeeded", "provider": "anthropic"}
        """
        self._emit(
            event_type=AuditEventType.FALLBACK_LLM_SUCCEEDED,
            payload={"provider": provider},
        )

    def log_fallback_llm_exhausted(
        self,
        primary_provider: str,
        fallback_provider: str,
        error_type: str,
        error_message: str,
    ) -> None:
        """
        Emitted when both primary and fallback providers fail. The pipeline
        will surface an exception to the caller.

        Example JSON::

            {"event": "fallback_llm_exhausted", "primary_provider": "openai",
             "fallback_provider": "anthropic", "error_type": "APIConnectionError",
             "error_message": "network unreachable"}
        """
        self._emit(
            event_type=AuditEventType.FALLBACK_LLM_EXHAUSTED,
            payload={
                "primary_provider": primary_provider,
                "fallback_provider": fallback_provider,
                "error_type": error_type,
                "error_message": error_message,
            },
        )

    # ------------------------------------------------------------------
    # Job ingestion events
    # ------------------------------------------------------------------

    def log_job_create_started(self, markdown_length: int) -> None:
        """Emitted when POST /api/jobs/ receives a valid request."""
        self._emit(
            event_type=AuditEventType.JOB_CREATE_STARTED,
            payload={"markdown_length": markdown_length},
        )

    def log_job_created(self, job_id: str, title: str) -> None:
        """Emitted after a Job row is successfully persisted."""
        self._emit(
            event_type=AuditEventType.JOB_CREATED,
            payload={"job_id": job_id, "title": title},
        )

    def log_job_create_failed(
        self,
        reason: str,
        *,
        field_key: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        """
        Emitted when POST /api/jobs/ cannot create the job.

        Args:
            reason: One of ``"validation_error"``, ``"parse_error"``,
                    ``"duplicate_title"``.
            field_key: The offending field from ``JobParseError``, if any.
            detail: Human-readable description of the failure.
        """
        self._emit(
            event_type=AuditEventType.JOB_CREATE_FAILED,
            payload={
                "reason":    reason,
                "field_key": field_key,
                "detail":    detail,
            },
        )

    # ------------------------------------------------------------------
    # Candidate ingestion events
    # ------------------------------------------------------------------

    def log_candidate_create_started(self, name: str) -> None:
        """Emitted when POST /api/candidates/ receives a valid request."""
        self._emit(
            event_type=AuditEventType.CANDIDATE_CREATE_STARTED,
            payload={"name": name},
        )

    def log_candidate_created(self, candidate_id: str, name: str) -> None:
        """Emitted after a Candidate row is successfully persisted."""
        self._emit(
            event_type=AuditEventType.CANDIDATE_CREATED,
            payload={"candidate_id": candidate_id, "name": name},
        )

    def log_candidate_create_failed(
        self,
        reason: str,
        *,
        field_key: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        """
        Emitted when POST /api/candidates/ cannot create the candidate.

        Args:
            reason: One of ``"validation_error"``, ``"pdf_parse_error"``,
                    ``"duplicate_email"``.
            field_key: The offending field, if any.
            detail: Human-readable description of the failure.
        """
        self._emit(
            event_type=AuditEventType.CANDIDATE_CREATE_FAILED,
            payload={"reason": reason, "field_key": field_key, "detail": detail},
        )

    # ------------------------------------------------------------------
    # Application lifecycle events
    # ------------------------------------------------------------------

    def log_application_create_started(self, job_id: str, candidate_id: str) -> None:
        """Emitted when POST /api/applications/ receives a valid request."""
        self._emit(
            event_type=AuditEventType.APPLICATION_CREATE_STARTED,
            payload={"job_id": job_id, "candidate_id": candidate_id},
        )

    def log_application_created(
        self, application_id: str, job_id: str, candidate_id: str
    ) -> None:
        """Emitted after a new Application row is successfully persisted (HTTP 201)."""
        self._emit(
            event_type=AuditEventType.APPLICATION_CREATED,
            payload={
                "application_id": application_id,
                "job_id": job_id,
                "candidate_id": candidate_id,
            },
        )

    def log_application_already_exists(
        self, application_id: str, job_id: str, candidate_id: str
    ) -> None:
        """Emitted when the job–candidate pair already exists (HTTP 200 idempotent)."""
        self._emit(
            event_type=AuditEventType.APPLICATION_ALREADY_EXISTS,
            payload={
                "application_id": application_id,
                "job_id": job_id,
                "candidate_id": candidate_id,
            },
        )

    def log_application_create_failed(
        self,
        reason: str,
        *,
        field_key: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        """
        Emitted when POST /api/applications/ cannot create the application.

        Args:
            reason: One of ``"validation_error"``.
            field_key: The offending field, if any.
            detail: Human-readable description of the failure.
        """
        self._emit(
            event_type=AuditEventType.APPLICATION_CREATE_FAILED,
            payload={"reason": reason, "field_key": field_key, "detail": detail},
        )

    # ------------------------------------------------------------------
    # Pipeline internals — step-level trace events
    # ------------------------------------------------------------------

    def log_pipeline_service_init(
        self,
        orchestrator_type: str,
        embedding_backend_type: str,
        embedding_dim: Optional[int],
    ) -> None:
        """Emitted once when PipelineService.__init__ completes."""
        self._emit(
            event_type=AuditEventType.PIPELINE_SERVICE_INIT,
            payload={
                "orchestrator_type":      orchestrator_type,
                "embedding_backend_type": embedding_backend_type,
                "embedding_dim":          embedding_dim,
            },
        )

    def log_pipeline_embeddings_built(
        self,
        application_id: str,
        candidate_sections: list[str],
        job_sections: list[str],
        embedding_dim: int,
    ) -> None:
        """Emitted after candidate and job embeddings are constructed."""
        self._emit(
            event_type=AuditEventType.PIPELINE_EMBEDDINGS_BUILT,
            payload={
                "application_id":    application_id,
                "candidate_sections": candidate_sections,
                "job_sections":       job_sections,
                "candidate_section_count": len(candidate_sections),
                "job_section_count":       len(job_sections),
                "embedding_dim":           embedding_dim,
            },
        )

    def log_pipeline_gate_result(
        self,
        application_id: str,
        gate_outcome: str,
        gate_passed: bool,
        criterion_results: list[dict],
    ) -> None:
        """Emitted after the hard-gate stage completes with per-criterion detail."""
        self._emit(
            event_type=AuditEventType.PIPELINE_GATE_RESULT,
            payload={
                "application_id": application_id,
                "gate_outcome":   gate_outcome,
                "gate_passed":    gate_passed,
                "criteria":       criterion_results,
            },
        )

    def log_pipeline_semantic_result(
        self,
        application_id: str,
        semantic_score: float,
        section_scores: dict[str, float],
    ) -> None:
        """Emitted after the semantic-match stage completes."""
        self._emit(
            event_type=AuditEventType.PIPELINE_SEMANTIC_RESULT,
            payload={
                "application_id": application_id,
                "semantic_score": semantic_score,
                "section_scores": section_scores,
                "sections_scored": len(section_scores),
            },
        )

    def log_pipeline_rubric_result(
        self,
        application_id: str,
        rubric_score: float,
        criterion_scores: dict[str, float],
        evidence_quality: float,
    ) -> None:
        """Emitted after the LLM rubric stage completes."""
        self._emit(
            event_type=AuditEventType.PIPELINE_RUBRIC_RESULT,
            payload={
                "application_id":  application_id,
                "rubric_score":    rubric_score,
                "criterion_scores": criterion_scores,
                "evidence_quality": evidence_quality,
            },
        )

    def log_pipeline_persisted(
        self,
        application_id: str,
        gate_outcome: str,
        gate_passed: bool,
        stages_persisted: list[str],
        new_status: str,
    ) -> None:
        """Emitted after all pipeline results are written to the database."""
        self._emit(
            event_type=AuditEventType.PIPELINE_PERSISTED,
            payload={
                "application_id":  application_id,
                "gate_outcome":    gate_outcome,
                "gate_passed":     gate_passed,
                "stages_persisted": stages_persisted,
                "new_status":       new_status,
            },
        )

    # ------------------------------------------------------------------
    # RubricEvaluator internals
    # ------------------------------------------------------------------

    def log_rubric_llm_call_started(
        self,
        model_name: str,
        system_prompt_len: int,
        user_prompt_len: int,
        resume_sections: list[str],
        job_requirement_keys: list[str],
    ) -> None:
        """Emitted immediately before the LLM backend is called."""
        self._emit(
            event_type=AuditEventType.RUBRIC_LLM_CALL_STARTED,
            payload={
                "model_name":          model_name,
                "system_prompt_len":   system_prompt_len,
                "user_prompt_len":     user_prompt_len,
                "resume_sections":     resume_sections,
                "job_requirement_keys": job_requirement_keys,
            },
        )

    def log_rubric_llm_call_finished(
        self,
        model_name: str,
        response_type: str,
        response_len: Optional[int],
        latency_ms: float,
        used_fallback: bool,
    ) -> None:
        """Emitted after the LLM returns (before parsing). response_type: 'structured' | 'string'."""
        self._emit(
            event_type=AuditEventType.RUBRIC_LLM_CALL_FINISHED,
            payload={
                "model_name":    model_name,
                "response_type": response_type,
                "response_len":  response_len,
                "latency_ms":    latency_ms,
                "used_fallback": used_fallback,
            },
        )

    def log_rubric_response_parsed(
        self,
        parse_path: str,
        had_markdown_fence: bool,
        criteria_found: list[str],
        is_fallback: bool,
    ) -> None:
        """
        Emitted after _parse_response() resolves.

        parse_path values:
          'structured_object' — instructor returned a validated Pydantic object
          'json_string'       — raw JSON string parsed successfully
          'fallback_empty'    — LLM returned an empty string
          'fallback_parse_error' — JSON parsing failed
        """
        self._emit(
            event_type=AuditEventType.RUBRIC_RESPONSE_PARSED,
            payload={
                "parse_path":        parse_path,
                "had_markdown_fence": had_markdown_fence,
                "criteria_found":    criteria_found,
                "criteria_count":    len(criteria_found),
                "is_fallback":       is_fallback,
            },
        )

    def log_rubric_scored(
        self,
        raw_scores: dict[str, float],
        clamped_scores: dict[str, float],
        weighted_sum: float,
        normalized_score: float,
        evidence_per_criterion: dict[str, int],
        evidence_quality: float,
    ) -> None:
        """Emitted after _score() computes the final RubricResult."""
        self._emit(
            event_type=AuditEventType.RUBRIC_SCORED,
            payload={
                "raw_scores":             raw_scores,
                "clamped_scores":         clamped_scores,
                "weighted_sum":           round(weighted_sum, 4),
                "normalized_score":       round(normalized_score, 4),
                "evidence_per_criterion": evidence_per_criterion,
                "evidence_quality":       round(evidence_quality, 4),
            },
        )

    # ------------------------------------------------------------------
    # Dashboard stats events
    # ------------------------------------------------------------------

    def log_dashboard_stats_fetched(
        self,
        *,
        applications: int,
        candidates: int,
        jobs: int,
        active_jobs: int,
        llm_success_rate: float,
        latency_ms: float,
    ) -> None:
        """Emitted after GET /api/dashboard/stats/ successfully aggregates all queries."""
        self._emit(
            event_type=AuditEventType.DASHBOARD_STATS_FETCHED,
            payload={
                "totals": {
                    "applications": applications,
                    "candidates":   candidates,
                    "jobs":         jobs,
                    "active_jobs":  active_jobs,
                },
                "llm_success_rate": llm_success_rate,
                "latency_ms": latency_ms,
            },
        )

    # ------------------------------------------------------------------
    # M0.5 — Document ingestion events
    # ------------------------------------------------------------------

    def log_pipeline_stage_started(self, stage: str, **kwargs) -> None:
        """Emit a stage-started event. Event name: ``{stage}_started``."""
        self._emit_raw(
            event_type=f"{stage}_started",
            payload=dict(kwargs),
        )

    def log_document_parsed(
        self,
        filepath: str,
        parser_used: str,
        char_count: int,
        page_count: int,
        status: str,
    ) -> None:
        """Emitted after successful PDF extraction and section detection."""
        self._emit(
            event_type=AuditEventType.DOCUMENT_PARSED,
            payload={
                "filepath": filepath,
                "parser_used": parser_used,
                "char_count": char_count,
                "page_count": page_count,
                "status": status,
            },
        )

    def log_parser_fallback(
        self,
        primary: str,
        fallback: str,
        reason: str,
    ) -> None:
        """Emitted when pdfplumber is invoked as fallback for the primary backend."""
        self._emit(
            event_type=AuditEventType.PARSER_FALLBACK,
            payload={
                "primary": primary,
                "fallback": fallback,
                "reason": reason,
            },
        )

    def log_document_parse_failed(self, filepath: str, error: str) -> None:
        """Emitted when both backends fail and status=FAILED is returned."""
        self._emit(
            event_type=AuditEventType.DOCUMENT_PARSE_FAILED,
            payload={
                "filepath": filepath,
                "error": error,
            },
        )

    # ------------------------------------------------------------------
    # Internal emit
    # ------------------------------------------------------------------

    def _emit_raw(self, event_type: str, payload: dict) -> None:
        """Emit with a plain string event_type (for dynamic names like '{stage}_started')."""
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            **payload,
        }
        self._logger.log(self._level, json.dumps(record, default=str))

    def _emit(self, event_type: AuditEventType, payload: dict) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_type.value,
            **payload,
        }
        self._logger.log(self._level, json.dumps(record, default=str))


# ---------------------------------------------------------------------------
# Process-level singleton
# ---------------------------------------------------------------------------

#: Import this directly in pipeline modules.
audit_logger = StructuredAuditLogger()
