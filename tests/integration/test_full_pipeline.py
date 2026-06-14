"""
M7 — Full end-to-end pipeline integration test.

Covers the complete path:
    Ingestion (mock PDF text) → Hard Gate → Semantic Match → Rubric (mock LLM)
    → Final Score → Audit event verification → Observability records

All tests run with LLM_BACKEND=mock (no API key needed). They are marked
@pytest.mark.integration because they wire every module together and are
slower than unit tests, but they do NOT require a running database or
real LLM.

Run:
    pytest tests/integration/test_full_pipeline.py -v

Telemetry completeness audit (per execution_plan_v2.md M7 checklist):
    Every stage must emit both:
      (a) a LatencyRecord in pipeline_observability._records
      (b) the correct structured audit event in pipeline.audit logger
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from resume_pipeline.ingestion.parser import ParseStatus, ResumeParser
from resume_pipeline.ingestion.section_detector import SectionDetector
from resume_pipeline.logging_module import StructuredAuditLogger
from resume_pipeline.observability import PipelineObservability
from resume_pipeline.pipeline.hard_gate import GateOutcome, HardGateEvaluator
from resume_pipeline.pipeline.orchestrator import PipelineInput, PipelineOrchestrator
from resume_pipeline.pipeline.rubric_score import (
    CRITERIA,
    MockLLMBackend,
    RubricEvaluator,
    build_llm_response,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

ALICE_RESUME_TEXT = """\
Experience
Senior Python Engineer at Acme Corp 2017-2024. Led Django monolith-to-microservices
migration. Reduced p99 latency by 40ms. Managed team of 6 engineers.

Technical Skills
Python Django PostgreSQL Redis Docker Kubernetes REST APIs

Education
BSc Computer Science, University of California, Berkeley, 2016

Certifications
AWS Solutions Architect Professional 2022
"""

ALICE_JOB_MUST_HAVES = {
    "min_experience": {"type": "years_experience", "minimum_years": 5},
    "python_required": {
        "type": "keyword_presence",
        "keywords": ["Python"],
        "sections": ["skills", "experience"],
    },
    "django_required": {
        "type": "keyword_presence",
        "keywords": ["Django"],
        "sections": ["skills", "experience"],
    },
}

ALICE_JOB_REQUIREMENTS = {
    "required_skills": ["Python", "Django", "PostgreSQL", "REST APIs"],
    "minimum_experience_years": 5,
}


@contextmanager
def capture_audit_events():
    """Context manager that captures structured JSON events from pipeline.audit."""
    events: list[dict] = []

    class _H(logging.Handler):
        def emit(self, record):
            msg = record.getMessage()
            if msg.strip().startswith("{"):
                try:
                    events.append(json.loads(msg))
                except json.JSONDecodeError:
                    pass

    handler = _H()
    log = logging.getLogger("pipeline.audit")
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    try:
        yield events
    finally:
        log.removeHandler(handler)


def _mock_semantic(score: float = 0.78) -> MagicMock:
    mock = MagicMock()
    result = MagicMock()
    result.final_score = score
    result.section_scores = {"skills": score, "experience": score}
    mock.evaluate.return_value = result
    return mock


def _mock_llm_backend(score: int = 4) -> MockLLMBackend:
    return MockLLMBackend(
        build_llm_response(
            scores={c: score for c in CRITERIA},
            justifications={
                c: f"Strong evidence for {c}: candidate demonstrated this clearly in their resume."
                for c in CRITERIA
            },
        )
    )


# ---------------------------------------------------------------------------
# 1. Ingestion module — parse realistic resume text
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestIngestionStage:
    """Verify the ingestion module parses resume text and detects sections."""

    def test_section_detector_detects_alice_sections(self):
        detector = SectionDetector()
        # Patch _run_nlp to use regex fallback (no spaCy model download)
        with patch.object(detector, "_run_nlp", wraps=detector._regex_fallback):
            sections = detector.detect(ALICE_RESUME_TEXT)
        assert "experience" in sections
        assert "skills" in sections
        assert "education" in sections

    def test_resume_parser_returns_parsed_document(self):
        """ResumeParser with mocked backends parses text into ParsedDocument."""
        mock_primary = MagicMock()
        mock_primary.extract_text.return_value = (ALICE_RESUME_TEXT, 1)
        mock_primary.is_viable.return_value = True

        detector = SectionDetector()
        obs = PipelineObservability()
        audit = StructuredAuditLogger()

        with patch.object(detector, "_run_nlp", wraps=detector._regex_fallback):
            parser = ResumeParser(
                primary=mock_primary,
                detector=detector,
                observability=obs,
                audit_logger=audit,
            )
            doc = parser.parse("/fake/alice_resume.pdf")

        assert doc.status == ParseStatus.OK
        assert doc.char_count == len(ALICE_RESUME_TEXT)
        assert "experience" in doc.sections
        assert "skills" in doc.sections
        assert doc.parser_used == "pymupdf"

    def test_ingestion_emits_document_parsed_audit_event(self):
        mock_primary = MagicMock()
        mock_primary.extract_text.return_value = (ALICE_RESUME_TEXT, 1)
        mock_primary.is_viable.return_value = True

        detector = SectionDetector()
        obs = PipelineObservability()
        audit = StructuredAuditLogger()

        with capture_audit_events() as events, \
             patch.object(detector, "_run_nlp", wraps=detector._regex_fallback):
            parser = ResumeParser(
                primary=mock_primary,
                detector=detector,
                observability=obs,
                audit_logger=audit,
            )
            parser.parse("/fake/alice_resume.pdf")

        event_types = [e.get("event") for e in events]
        assert "document_parsed" in event_types, (
            f"Expected 'document_parsed' audit event; got: {event_types}"
        )

    def test_ingestion_records_latency(self):
        mock_primary = MagicMock()
        mock_primary.extract_text.return_value = (ALICE_RESUME_TEXT, 1)
        mock_primary.is_viable.return_value = True

        detector = SectionDetector()
        obs = PipelineObservability()
        audit = StructuredAuditLogger()

        with patch.object(detector, "_run_nlp", wraps=detector._regex_fallback):
            parser = ResumeParser(
                primary=mock_primary,
                detector=detector,
                observability=obs,
                audit_logger=audit,
            )
            parser.parse("/fake/alice_resume.pdf")

        stage_names = [r.stage for r in obs._records]
        assert "document_ingestion" in stage_names, (
            f"No 'document_ingestion' latency record. Records: {stage_names}"
        )


# ---------------------------------------------------------------------------
# 2. Full pipeline — ingestion output feeds orchestrator
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFullPipelinePassPath:
    """
    End-to-end: ingestion → hard gate → semantic → rubric → final score.
    All external dependencies (PDF libs, spaCy, LLM) are mocked.
    """

    @pytest.fixture
    def parsed_resume(self):
        """Simulate what ingestion produces for Alice's resume."""
        return {
            "total_experience_years": 7,
            "experience": "Senior Python Engineer at Acme Corp 2017-2024. Led Django migration.",
            "skills": "Python Django PostgreSQL Redis Docker Kubernetes REST APIs",
            "education": "BSc Computer Science, UC Berkeley, 2016",
            "certifications": ["AWS Solutions Architect Professional"],
        }

    @pytest.fixture
    def orchestrator(self):
        return PipelineOrchestrator(
            semantic_evaluator=_mock_semantic(score=0.78),
            rubric_evaluator=RubricEvaluator(_mock_llm_backend(score=4)),
        )

    @pytest.fixture
    def pipeline_input(self, parsed_resume):
        return PipelineInput(
            application_id="integration-alice-001",
            job_must_haves=ALICE_JOB_MUST_HAVES,
            resume_parsed=parsed_resume,
            candidate_embeddings={"skills": [0.1] * 10, "experience": [0.2] * 10},
            job_embeddings={"skills": [0.11] * 10, "experience": [0.19] * 10},
            lexical_rank=1,
            semantic_rank=1,
            job_requirements=ALICE_JOB_REQUIREMENTS,
        )

    def test_full_pass_path_executes_three_stages(self, orchestrator, pipeline_input):
        result = orchestrator.run(pipeline_input)
        assert result.stages_executed == ["hard_gate", "semantic_match", "rubric"]

    def test_full_pass_path_gate_passes(self, orchestrator, pipeline_input):
        result = orchestrator.run(pipeline_input)
        assert result.gate_outcome == GateOutcome.PASS
        assert result.gate_passed is True

    def test_full_pass_path_rubric_score_populated(self, orchestrator, pipeline_input):
        result = orchestrator.run(pipeline_input)
        assert result.rubric_score is not None
        assert 0.0 < result.rubric_score <= 1.0

    def test_full_pass_path_final_score_nonzero(self, orchestrator, pipeline_input):
        result = orchestrator.run(pipeline_input)
        assert result.final_score > 0.0

    def test_full_pass_path_criterion_scores_all_present(self, orchestrator, pipeline_input):
        result = orchestrator.run(pipeline_input)
        assert set(result.rubric_criterion_scores.keys()) == set(CRITERIA)

    def test_full_pass_path_application_id_preserved(self, orchestrator, pipeline_input):
        result = orchestrator.run(pipeline_input)
        assert result.application_id == "integration-alice-001"

    def test_full_pass_path_total_latency_recorded(self, orchestrator, pipeline_input):
        result = orchestrator.run(pipeline_input)
        assert result.total_latency_ms > 0.0


@pytest.mark.integration
class TestFullPipelineFailPath:
    """Carol Smith: gate=FAIL → short-circuit, LLM never called."""

    @pytest.fixture
    def backend(self):
        return _mock_llm_backend(score=3)

    @pytest.fixture
    def orchestrator(self, backend):
        return PipelineOrchestrator(
            semantic_evaluator=_mock_semantic(),
            rubric_evaluator=RubricEvaluator(backend),
        )

    @pytest.fixture
    def pipeline_input(self):
        return PipelineInput(
            application_id="integration-carol-001",
            job_must_haves=ALICE_JOB_MUST_HAVES,
            resume_parsed={
                "total_experience_years": 2,
                "experience": "Junior Python developer at WebAgency 2022-2024. Built Flask apps.",
                "skills": "Python Flask SQLite HTML CSS",
            },
            candidate_embeddings={},
            job_embeddings={},
            lexical_rank=None,
            semantic_rank=None,
            job_requirements={},
        )

    def test_fail_path_gate_fails(self, orchestrator, pipeline_input):
        result = orchestrator.run(pipeline_input)
        assert result.gate_outcome == GateOutcome.FAIL
        assert result.gate_passed is False

    def test_fail_path_only_gate_stage_executed(self, orchestrator, pipeline_input):
        result = orchestrator.run(pipeline_input)
        assert result.stages_executed == ["hard_gate"]

    def test_fail_path_final_score_is_zero(self, orchestrator, pipeline_input):
        result = orchestrator.run(pipeline_input)
        assert result.final_score == 0.0

    def test_fail_path_llm_never_called(self, backend, orchestrator, pipeline_input):
        orchestrator.run(pipeline_input)
        assert backend.call_count == 0


# ---------------------------------------------------------------------------
# 3. Telemetry completeness audit
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestTelemetryCompleteness:
    """
    Verifies every pipeline stage emits both:
      (a) A LatencyRecord in PipelineObservability._records
      (b) The correct structured event in the pipeline.audit logger

    Per execution_plan_v2.md M7 telemetry table.
    """

    @pytest.fixture
    def obs(self):
        return PipelineObservability()

    @pytest.fixture
    def orchestrator(self, obs):
        orch = PipelineOrchestrator(
            semantic_evaluator=_mock_semantic(score=0.75),
            rubric_evaluator=RubricEvaluator(_mock_llm_backend(score=4)),
            observability=obs,
        )
        return orch

    @pytest.fixture
    def pass_input(self):
        return PipelineInput(
            application_id="telemetry-pass-001",
            job_must_haves=ALICE_JOB_MUST_HAVES,
            resume_parsed={
                "total_experience_years": 7,
                "experience": "Senior Python Engineer 2017-2024, Django expert.",
                "skills": "Python Django PostgreSQL REST APIs",
            },
            candidate_embeddings={"skills": [0.1] * 10},
            job_embeddings={"skills": [0.1] * 10},
            lexical_rank=1,
            semantic_rank=1,
            job_requirements=ALICE_JOB_REQUIREMENTS,
        )

    @pytest.fixture
    def fail_input(self):
        return PipelineInput(
            application_id="telemetry-fail-001",
            job_must_haves=ALICE_JOB_MUST_HAVES,
            resume_parsed={
                "total_experience_years": 2,
                "skills": "Python Flask",
            },
            candidate_embeddings={},
            job_embeddings={},
            lexical_rank=None,
            semantic_rank=None,
            job_requirements={},
        )

    # ── Latency records ────────────────────────────────────────────────────

    def test_pass_path_has_latency_record_for_hard_gate(self, orchestrator, obs, pass_input):
        orchestrator.run(pass_input)
        assert any(r.stage == "hard_gate" for r in obs._records)

    def test_pass_path_has_latency_record_for_semantic_match(self, orchestrator, obs, pass_input):
        orchestrator.run(pass_input)
        assert any(r.stage == "semantic_match" for r in obs._records)

    def test_pass_path_has_latency_record_for_rubric(self, orchestrator, obs, pass_input):
        orchestrator.run(pass_input)
        assert any(r.stage == "rubric" for r in obs._records)

    def test_fail_path_has_latency_record_for_hard_gate(self, orchestrator, obs, fail_input):
        orchestrator.run(fail_input)
        assert any(r.stage == "hard_gate" for r in obs._records)

    def test_fail_path_has_no_latency_record_for_rubric(self, orchestrator, obs, fail_input):
        orchestrator.run(fail_input)
        rubric_records = [r for r in obs._records if r.stage == "rubric"]
        assert len(rubric_records) == 0, (
            "Rubric stage should not execute (and therefore not emit a latency record) "
            "when the pipeline short-circuits on gate FAIL."
        )

    # ── Audit events ────────────────────────────────────────────────────────

    def test_pass_path_emits_gate_transition_events(self, orchestrator, pass_input):
        with capture_audit_events() as events:
            orchestrator.run(pass_input)
        gate_events = [e for e in events if e.get("event") == "gate_transition"]
        assert len(gate_events) >= 1, (
            f"Expected gate_transition events; got: {[e.get('event') for e in events]}"
        )

    def test_pass_path_emits_score_computed_event(self, orchestrator, pass_input):
        with capture_audit_events() as events:
            orchestrator.run(pass_input)
        score_events = [e for e in events if e.get("event") == "score_computed"]
        assert len(score_events) == 1, (
            f"Expected exactly 1 score_computed event; got {len(score_events)}"
        )

    def test_pass_path_score_computed_has_model_name(self, orchestrator, pass_input):
        with capture_audit_events() as events:
            orchestrator.run(pass_input)
        score_event = next(e for e in events if e.get("event") == "score_computed")
        assert "model_name" in score_event, (
            f"score_computed missing model_name field: {score_event}"
        )
        assert score_event["model_name"] is not None

    def test_pass_path_score_computed_has_all_component_scores(self, orchestrator, pass_input):
        with capture_audit_events() as events:
            orchestrator.run(pass_input)
        score_event = next(e for e in events if e.get("event") == "score_computed")
        components = score_event.get("component_scores", {})
        assert "semantic_match" in components
        assert "rubric_score_norm" in components
        assert "evidence_quality" in components

    def test_fail_path_emits_pipeline_short_circuited_event(self, orchestrator, fail_input):
        with capture_audit_events() as events:
            orchestrator.run(fail_input)
        sc_events = [e for e in events if e.get("event") == "pipeline_short_circuited"]
        assert len(sc_events) == 1, (
            f"Expected 1 pipeline_short_circuited event; got: "
            f"{[e.get('event') for e in events]}"
        )

    def test_fail_path_no_score_computed_event(self, orchestrator, fail_input):
        with capture_audit_events() as events:
            orchestrator.run(fail_input)
        score_events = [e for e in events if e.get("event") == "score_computed"]
        assert len(score_events) == 0, (
            "score_computed should not be emitted when pipeline short-circuits on FAIL"
        )

    def test_ingestion_telemetry_document_parsed_event(self):
        """Document ingestion emits a document_parsed audit event."""
        mock_primary = MagicMock()
        mock_primary.extract_text.return_value = (ALICE_RESUME_TEXT, 1)
        mock_primary.is_viable.return_value = True

        detector = SectionDetector()
        obs = PipelineObservability()
        audit = StructuredAuditLogger()

        with capture_audit_events() as events, \
             patch.object(detector, "_run_nlp", wraps=detector._regex_fallback):
            parser = ResumeParser(
                primary=mock_primary,
                detector=detector,
                observability=obs,
                audit_logger=audit,
            )
            parser.parse("/fake/resume.pdf")

        event_types = {e.get("event") for e in events}
        # Must have: started + parsed
        assert "document_parsed" in event_types
        ingestion_latency = [r for r in obs._records if r.stage == "document_ingestion"]
        assert len(ingestion_latency) == 1

    def test_ingestion_fallback_emits_parser_fallback_event(self):
        """When primary returns < 50 chars, fallback emits parser_fallback audit event."""
        mock_primary = MagicMock()
        mock_primary.extract_text.return_value = ("short", 1)  # < 50 chars
        mock_primary.is_viable.return_value = False

        mock_fallback = MagicMock()
        mock_fallback.extract_text.return_value = (ALICE_RESUME_TEXT, 1)

        detector = SectionDetector()
        obs = PipelineObservability()
        audit = StructuredAuditLogger()

        with capture_audit_events() as events, \
             patch.object(detector, "_run_nlp", wraps=detector._regex_fallback):
            parser = ResumeParser(
                primary=mock_primary,
                fallback=mock_fallback,
                detector=detector,
                observability=obs,
                audit_logger=audit,
            )
            doc = parser.parse("/fake/resume.pdf")

        assert doc.parser_used == "pdfplumber"
        event_types = {e.get("event") for e in events}
        assert "parser_fallback" in event_types, (
            f"Expected parser_fallback event; got: {event_types}"
        )
