"""
Pipeline Observability Module.

Design principle: zero business logic pollution.
Stages are instrumented via a decorator — the stage function itself is unaware.

Usage::

    obs = PipelineObservability()

    @obs.instrument("hard_gate")
    def run_hard_gate(must_haves, resume_parsed):
        ...

    # Or wrap an existing callable at composition time:
    timed_evaluate = obs.instrument("semantic_match")(evaluator.evaluate)

The module ships a process-level singleton `pipeline_observability` for convenience,
but it is replaceable (e.g., swap the sink to emit to Prometheus / Datadog in prod).
"""

from __future__ import annotations

import functools
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class LatencyRecord:
    """Immutable record emitted after each instrumented stage."""

    stage: str
    latency_ms: float
    # Optional key-value metadata (application_id, model_name, etc.)
    metadata: dict[str, Any] = field(default_factory=dict)


SinkCallable = Callable[[LatencyRecord], None]


# ---------------------------------------------------------------------------
# Core module
# ---------------------------------------------------------------------------

class PipelineObservability:
    """
    Wraps pipeline stage callables to measure and emit wall-clock latency.

    Args:
        sink: Callable that receives each LatencyRecord. Defaults to a
              structured log line. Replace with a metrics client in production.
    """

    def __init__(self, sink: Optional[SinkCallable] = None) -> None:
        self._sink: SinkCallable = sink or self._log_sink
        self._records: list[LatencyRecord] = []

    # ------------------------------------------------------------------
    # Decorator factory
    # ------------------------------------------------------------------

    def instrument(self, stage_name: str, **extra_metadata: Any):
        """
        Decorator factory. Wraps a callable and records its execution latency.

        Args:
            stage_name: Human-readable label for the pipeline stage.
            **extra_metadata: Static key-value pairs merged into every record.

        Example::

            @obs.instrument("hard_gate", application_id=app.id)
            def evaluate(...):
                ...
        """

        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                try:
                    result = fn(*args, **kwargs)
                    return result
                finally:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    record = LatencyRecord(
                        stage=stage_name,
                        latency_ms=round(elapsed_ms, 3),
                        metadata=dict(extra_metadata),
                    )
                    self._records.append(record)
                    self._sink(record)

            return wrapper

        return decorator

    # ------------------------------------------------------------------
    # Context manager for one-off timing blocks
    # ------------------------------------------------------------------

    def timed(self, stage_name: str, **extra_metadata: Any):
        """
        Context manager variant for timing an arbitrary block.

        Usage::

            with obs.timed("embedding_generation", model="ada-002"):
                vectors = embed(texts)
        """
        return _TimedBlock(
            stage_name=stage_name,
            observability=self,
            metadata=extra_metadata,
        )

    # ------------------------------------------------------------------
    # Record access
    # ------------------------------------------------------------------

    def get_records(self) -> list[LatencyRecord]:
        """Returns a snapshot of all records collected in this instance."""
        return list(self._records)

    def get_stage_records(self, stage_name: str) -> list[LatencyRecord]:
        return [r for r in self._records if r.stage == stage_name]

    def clear(self) -> None:
        """Reset records — useful between test runs."""
        self._records.clear()

    def total_latency_ms(self) -> float:
        return sum(r.latency_ms for r in self._records)

    # ------------------------------------------------------------------
    # Default sink
    # ------------------------------------------------------------------

    @staticmethod
    def _log_sink(record: LatencyRecord) -> None:
        logger.info(
            "pipeline.latency stage=%s latency_ms=%.3f %s",
            record.stage,
            record.latency_ms,
            " ".join(f"{k}={v}" for k, v in record.metadata.items()),
        )


# ---------------------------------------------------------------------------
# Context manager helper
# ---------------------------------------------------------------------------

class _TimedBlock:
    def __init__(
        self,
        stage_name: str,
        observability: PipelineObservability,
        metadata: dict[str, Any],
    ) -> None:
        self._stage_name = stage_name
        self._obs = observability
        self._metadata = metadata
        self._start: float = 0.0

    def __enter__(self) -> "_TimedBlock":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        record = LatencyRecord(
            stage=self._stage_name,
            latency_ms=round(elapsed_ms, 3),
            metadata=self._metadata,
        )
        self._obs._records.append(record)
        self._obs._sink(record)


# ---------------------------------------------------------------------------
# Process-level singleton
# ---------------------------------------------------------------------------

#: Convenience singleton. Import and use directly in stage modules.
#: Swap the sink at application startup to route to your metrics backend.
pipeline_observability = PipelineObservability()
