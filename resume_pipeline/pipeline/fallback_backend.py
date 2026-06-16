"""
LLM Provider Resilience — Automatic Failover Backend.

Architecture
────────────
                 ┌──────────────────────────┐
                 │   FallbackLLMBackend     │
                 │   primary: LLMBackend    │
                 │   fallback: LLMBackend   │
                 └───────────┬──────────────┘
                             │
                    primary.complete()
                             │
                   ┌─────────▼──────────┐
                   │  Success           │──── return result (used_fallback=False)
                   └────────────────────┘
                             │ Exception (tenacity exhausted)
                             ▼
                   emit: primary_llm_failed
                   emit: fallback_llm_engaged
                             │
                    fallback.complete()
                             │
           ┌─────────────────┼───────────────────────┐
           │ Success                                 │ Exception
           ▼                                         ▼
  used_fallback = True                    emit: fallback_llm_exhausted
  emit: fallback_llm_succeeded            re-raise
  return result

Key properties
──────────────
  used_fallback  — True when the most-recent complete() engaged the secondary.
                   Reset at the start of every call, so it reflects only the
                   last invocation's outcome.
  model_name     — Dynamically returns the active provider's model name.
                   Used by RubricEvaluator + orchestrator for audit logging.

Integration points
──────────────────
  1. RubricEvaluator.evaluate() checks getattr(self._llm, 'used_fallback', False)
     after complete() and stamps RubricResult.is_evaluated_via_fallback.
  2. PipelineOrchestrator reads is_evaluated_via_fallback from RubricResult and
     includes it in the score_computed audit event and PipelineResult.
  3. make_rubric_backend() auto-wires this wrapper when LLM_BACKEND_FALLBACK env
     var is set to a provider name different from the primary.

Configuration (via make_rubric_backend)
────────────────────────────────────────
  LLM_BACKEND=openai    LLM_BACKEND_FALLBACK=anthropic  → FallbackLLMBackend
  LLM_BACKEND=anthropic LLM_BACKEND_FALLBACK=openai     → FallbackLLMBackend
  LLM_BACKEND=openai    (no fallback var)               → OpenAIRubricBackend only
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from resume_pipeline.logging_module import StructuredAuditLogger
from resume_pipeline.logging_module import audit_logger as _process_audit_logger

if TYPE_CHECKING:
    # Avoid circular import at module load time; these types are only needed
    # for static analysis and function signatures.
    from resume_pipeline.pipeline.rubric_score import LLMBackendProtocol, RubricScoreResponse


class FallbackLLMBackend:
    """
    Composite LLM backend that automatically fails over to a secondary provider.

    Calls primary.complete() — which internally has its own tenacity retry
    logic (e.g. 3 attempts on RateLimitError). Only if the primary raises
    after exhausting all retries does this wrapper engage the fallback.

    Thread-safety: not thread-safe. Each pipeline worker should create its
    own FallbackLLMBackend instance (or the make_rubric_backend factory
    should be called per-request, not at startup). This matches the current
    orchestrator instantiation pattern.

    Args:
        primary:       The preferred backend (e.g., OpenAIRubricBackend).
        fallback:      The secondary backend (e.g., AnthropicRubricBackend).
        audit_logger:  Injected logger for tests. Defaults to the
                       process-level singleton.

    Attributes:
        used_fallback: True if the last complete() call engaged the secondary.
                       Read by RubricEvaluator to stamp RubricResult.
        model_name:    The model identifier of whichever provider was active.
    """

    def __init__(
        self,
        primary: "LLMBackendProtocol",
        fallback: "LLMBackendProtocol",
        audit_logger: Optional[StructuredAuditLogger] = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._audit = audit_logger or _process_audit_logger

        # Per-call state — reset at the start of each complete() call.
        self._used_fallback: bool = False
        self._last_primary_error: Optional[Exception] = None

    # ------------------------------------------------------------------
    # LLMBackendProtocol
    # ------------------------------------------------------------------

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> "Union[str, RubricScoreResponse]":
        """
        Execute LLM completion with automatic provider failover.

        The primary is called first. Its own tenacity retry loop runs N
        times on transient errors. If it still raises, we catch that
        exception here, log structured audit events, and delegate to the
        fallback provider.

        Sets self._used_fallback = True if the secondary was engaged.

        Raises:
            Exception: Re-raises the fallback's last exception if both
                       providers fail (after logging fallback_llm_exhausted).
        """
        # Reset per-call state so .used_fallback always reflects THIS call.
        self._used_fallback = False
        self._last_primary_error = None

        # ── Primary attempt ────────────────────────────────────────────
        try:
            return self._primary.complete(system_prompt, user_prompt)
        except Exception as exc:
            self._last_primary_error = exc
            self._audit.log_primary_llm_failed(
                provider=self._primary.model_name,
                error_type=type(exc).__name__,
                error_message=str(exc),
                retry_count=getattr(self._primary, "_max_retries", None),
            )

        # ── Engage fallback ────────────────────────────────────────────
        self._audit.log_fallback_llm_engaged(
            primary_provider=self._primary.model_name,
            target_provider=self._fallback.model_name,
        )

        try:
            result = self._fallback.complete(system_prompt, user_prompt)
        except Exception as exc:
            self._audit.log_fallback_llm_exhausted(
                primary_provider=self._primary.model_name,
                fallback_provider=self._fallback.model_name,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise

        # Fallback succeeded.
        self._used_fallback = True
        self._audit.log_fallback_llm_succeeded(provider=self._fallback.model_name)
        return result

    # ------------------------------------------------------------------
    # LLMBackendProtocol — properties
    # ------------------------------------------------------------------

    @property
    def used_fallback(self) -> bool:
        """True if the most-recent complete() call was served by the fallback."""
        return self._used_fallback

    @property
    def model_name(self) -> str:
        """
        The model identifier of the provider that was last active.

        Returns the fallback model name after a handoff, or the primary
        model name when primary was used (or before any call).
        """
        if self._used_fallback:
            return self._fallback.model_name
        return self._primary.model_name

    # ------------------------------------------------------------------
    # Introspection helpers (for tests and observability)
    # ------------------------------------------------------------------

    @property
    def primary(self) -> "LLMBackendProtocol":
        """The configured primary backend."""
        return self._primary

    @property
    def fallback_backend(self) -> "LLMBackendProtocol":
        """The configured fallback backend."""
        return self._fallback

    @property
    def last_primary_error(self) -> Optional[Exception]:
        """The exception that caused the primary to fail on the last call."""
        return self._last_primary_error
