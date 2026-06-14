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
