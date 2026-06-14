"""
Django models for the resume evaluation pipeline.

Entity hierarchy:
  Job → Application ← Candidate
  Application → HardGateResult
  Application → SemanticMatchResult
  Application → RubricScore
  Application → FinalScore
  Application → HumanReview (many)

  Candidate → SectionEmbedding (many, one per section)
  Job       → JobSectionEmbedding (many, one per section)
"""

import uuid
from django.db import models

# pgvector field — requires `pgvector` package and the extension installed in Postgres.
# Install: pip install pgvector
# Migration: CREATE EXTENSION IF NOT EXISTS vector;
try:
    from pgvector.django import VectorField
except ImportError:  # allows unit tests to run without the extension
    VectorField = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

EMBEDDING_DIMENSIONS = 1536  # OpenAI text-embedding-ada-002; swap for other models


def _vector_field(**kwargs):
    if VectorField is None:
        raise RuntimeError("pgvector is not installed. Run: pip install pgvector")
    return VectorField(**kwargs)


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField()

    # Structured requirements blob: {"required_skills": [...], "preferred_skills": [...], ...}
    requirements_raw = models.JSONField(default=dict)

    # Hard Gate criteria — each entry maps a criterion name to its config dict.
    # Example:
    #   {
    #     "minimum_experience": {"type": "years_experience", "minimum_years": 5},
    #     "python_required":    {"type": "keyword_presence", "keywords": ["Python"],
    #                            "sections": ["skills", "experience"]},
    #     "aws_cert":           {"type": "certification",   "required": ["AWS Solutions Architect"]},
    #   }
    must_haves = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------

class Candidate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)

    # Raw resume text as submitted.
    resume_raw = models.TextField()

    # Parser output. Top-level keys are section names matching SectionEmbedding.Section.
    # Additional keys: "total_experience_years" (float), "certifications" (list[str]).
    # Example:
    #   {
    #     "summary": "...",
    #     "experience": "...",
    #     "skills": "Python, Django, PostgreSQL",
    #     "education": "...",
    #     "certifications": ["AWS Solutions Architect"],
    #     "total_experience_years": 7,
    #   }
    resume_parsed = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"


# ---------------------------------------------------------------------------
# Application — links Candidate to Job; carries pipeline status
# ---------------------------------------------------------------------------

class Application(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        GATE_FAILED = "gate_failed", "Gate Failed"
        GATE_UNKNOWN = "gate_unknown", "Gate Unknown"
        GATE_PASSED = "gate_passed", "Gate Passed"
        SCORED = "scored", "Scored"
        UNDER_REVIEW = "under_review", "Under Human Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="applications")
    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name="applications"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("job", "candidate")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.candidate} → {self.job} [{self.status}]"


# ---------------------------------------------------------------------------
# Hard Gate Result  (Stage 1)
# ---------------------------------------------------------------------------

class HardGateResult(models.Model):
    class Outcome(models.TextChoices):
        PASS = "pass", "Pass"
        FAIL = "fail", "Fail"
        UNKNOWN = "unknown", "Unknown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.OneToOneField(
        Application, on_delete=models.CASCADE, related_name="gate_result"
    )
    # Aggregate outcome across all criteria.
    outcome = models.CharField(max_length=10, choices=Outcome.choices)

    # Per-criterion results. Structure:
    #   {
    #     "minimum_experience": {"outcome": "pass", "evidence": "7 years; required 5"},
    #     "python_required":    {"outcome": "fail", "evidence": "Missing: ['Python']"},
    #   }
    criterion_results = models.JSONField(default=dict)

    evaluated_at = models.DateTimeField(auto_now_add=True)
    latency_ms = models.FloatField(help_text="Wall-clock time for the full gate evaluation")

    class Meta:
        ordering = ["-evaluated_at"]

    def __str__(self) -> str:
        return f"Gate[{self.outcome}] for {self.application_id}"


# ---------------------------------------------------------------------------
# Section Embeddings  (Stage 2 inputs)
# ---------------------------------------------------------------------------

class ResumeSection(models.TextChoices):
    SUMMARY = "summary", "Summary"
    EXPERIENCE = "experience", "Experience"
    SKILLS = "skills", "Skills"
    EDUCATION = "education", "Education"
    CERTIFICATIONS = "certifications", "Certifications"
    PROJECTS = "projects", "Projects"


class SectionEmbedding(models.Model):
    """Per-section vector embedding for a candidate's resume."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name="embeddings"
    )
    section = models.CharField(max_length=30, choices=ResumeSection.choices)
    content = models.TextField(help_text="Raw text that was embedded")

    # Populated at runtime; declared with a sentinel when pgvector isn't installed.
    embedding = models.JSONField(
        null=True,
        blank=True,
        help_text="Use pgvector.django.VectorField in production migration",
    )

    model_name = models.CharField(max_length=100, default="text-embedding-ada-002")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("candidate", "section")
        ordering = ["candidate", "section"]

    def __str__(self) -> str:
        return f"Embedding[{self.section}] for candidate {self.candidate_id}"


class JobSectionEmbedding(models.Model):
    """Per-section vector embedding for a job description."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="embeddings")
    section = models.CharField(max_length=30)
    content = models.TextField()
    embedding = models.JSONField(null=True, blank=True)
    model_name = models.CharField(max_length=100, default="text-embedding-ada-002")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("job", "section")

    def __str__(self) -> str:
        return f"JobEmbedding[{self.section}] for job {self.job_id}"


# ---------------------------------------------------------------------------
# Semantic Match Result  (Stage 2 output)
# ---------------------------------------------------------------------------

class SemanticMatchResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.OneToOneField(
        Application, on_delete=models.CASCADE, related_name="semantic_match"
    )

    # Reciprocal Rank Fusion score in [0, 1].
    rrf_score = models.FloatField()

    # Per-section cosine similarities feeding into RRF.
    # {"experience": 0.87, "skills": 0.91, ...}
    section_scores = models.JSONField(default=dict)

    # Ranks from each retrieval channel (nullable: channel may not produce a rank).
    lexical_rank = models.IntegerField(null=True, blank=True)
    semantic_rank = models.IntegerField(null=True, blank=True)

    evaluated_at = models.DateTimeField(auto_now_add=True)
    latency_ms = models.FloatField()

    def __str__(self) -> str:
        return f"SemanticMatch[{self.rrf_score:.3f}] for {self.application_id}"


# ---------------------------------------------------------------------------
# Rubric Score  (Stage 3)
# ---------------------------------------------------------------------------

class RubricScore(models.Model):
    """
    Competency scores on a 1–5 scale, weighted into a normalized 0–1 score.

    Weights:
        core_skills          0.30
        relevant_experience  0.30
        scope_impact         0.20
        domain_alignment     0.10
        education_certs      0.10
    """

    WEIGHTS = {
        "core_skills": 0.30,
        "relevant_experience": 0.30,
        "scope_impact": 0.20,
        "domain_alignment": 0.10,
        "education_certs": 0.10,
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.OneToOneField(
        Application, on_delete=models.CASCADE, related_name="rubric_score"
    )

    # Raw LLM-assigned scores [1, 5].
    core_skills = models.FloatField()
    relevant_experience = models.FloatField()
    scope_impact = models.FloatField()
    domain_alignment = models.FloatField()
    education_certs = models.FloatField()

    # Weighted average of raw scores, normalized to [0, 1].
    normalized_score = models.FloatField()

    # Heuristic quality of supporting evidence (citation density, specificity).
    evidence_quality = models.FloatField(
        help_text="Heuristic 0–1: how well evidence supports the rubric scores"
    )

    # LLM model used for evaluation.
    model_name = models.CharField(max_length=100)

    evaluated_at = models.DateTimeField(auto_now_add=True)
    latency_ms = models.FloatField()

    def __str__(self) -> str:
        return f"RubricScore[{self.normalized_score:.3f}] for {self.application_id}"


# ---------------------------------------------------------------------------
# Final Score  (Stage 4)
# ---------------------------------------------------------------------------

class FinalScore(models.Model):
    """
    FinalScore = 0.0                                              if gate_outcome == FAIL
    FinalScore = 0.45 * semantic_match
              + 0.45 * rubric_score_norm
              + 0.10 * evidence_quality                           otherwise
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.OneToOneField(
        Application, on_delete=models.CASCADE, related_name="final_score"
    )

    # The composite score in [0, 1]; 0.0 is the hard-gate short-circuit value.
    score = models.FloatField()

    # Snapshot of whether the gate passed (useful for downstream queries without joins).
    gate_passed = models.BooleanField()

    # Confidence level — derived from stage-level signal quality.
    # Low confidence → surface to human review sooner.
    confidence = models.FloatField(null=True, blank=True)

    computed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"FinalScore[{self.score:.3f}] for {self.application_id}"


# ---------------------------------------------------------------------------
# Human Review  (Stage 5 — Human-in-the-Loop)
# ---------------------------------------------------------------------------

class HumanReview(models.Model):
    class Decision(models.TextChoices):
        APPROVE = "approve", "Approve"
        REJECT = "reject", "Reject"
        OVERRIDE_PASS = "override_pass", "Override AI — Move to Pass"
        OVERRIDE_FAIL = "override_fail", "Override AI — Move to Fail"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="reviews"
    )
    reviewer_email = models.EmailField()
    decision = models.CharField(max_length=20, choices=Decision.choices)

    # Mandatory for any override decision; enforced at the API serializer layer.
    override_reason = models.TextField(
        blank=True,
        default="",
        help_text="Required when decision is override_pass or override_fail",
    )

    # Snapshot of the AI score at review time (for audit drift tracking).
    ai_score_at_review = models.FloatField()
    confidence_at_review = models.FloatField(null=True, blank=True)

    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reviewed_at"]

    def __str__(self) -> str:
        return f"Review[{self.decision}] by {self.reviewer_email} on {self.application_id}"
