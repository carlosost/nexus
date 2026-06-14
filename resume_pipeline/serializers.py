"""
DRF Serializers for the Human-in-the-Loop API.

Serializer responsibilities:
  - HumanReviewSerializer: validates input, enforces override_reason constraint.
  - ApplicationScoreSerializer: read-only score card for the reviewer UI.
  - RubricBreakdownSerializer: per-competency scores nested in the score card.

Override reason enforcement rule (encoded as a serializer-level validator):
  Decision in {override_pass, override_fail} → override_reason must be
  non-empty and non-whitespace. This is checked BEFORE the view touches
  the DB — a 400 is returned immediately on failure.
"""

from __future__ import annotations

from rest_framework import serializers

from resume_pipeline.models import FinalScore, HumanReview, RubricScore


# ---------------------------------------------------------------------------
# Rubric breakdown (nested, read-only)
# ---------------------------------------------------------------------------

class RubricBreakdownSerializer(serializers.Serializer):
    """
    Per-competency scores exposed to the reviewer UI.

    Nested inside ApplicationScoreSerializer so the reviewer sees
    the full rubric picture, not just the normalized composite.
    """
    core_skills = serializers.FloatField(read_only=True)
    relevant_experience = serializers.FloatField(read_only=True)
    scope_impact = serializers.FloatField(read_only=True)
    domain_alignment = serializers.FloatField(read_only=True)
    education_certs = serializers.FloatField(read_only=True)
    normalized_score = serializers.FloatField(read_only=True)
    evidence_quality = serializers.FloatField(read_only=True)


# ---------------------------------------------------------------------------
# Application score card (read-only)
# ---------------------------------------------------------------------------

class ApplicationScoreSerializer(serializers.Serializer):
    """
    Full AI score card surfaced to the human reviewer.

    All fields are read-only — the score card is a view, not an input form.
    """
    application_id = serializers.UUIDField(read_only=True, source="application.id")
    final_score = serializers.FloatField(read_only=True)
    confidence = serializers.FloatField(read_only=True, allow_null=True)
    gate_passed = serializers.BooleanField(read_only=True)
    gate_outcome = serializers.SerializerMethodField(read_only=True)
    semantic_score = serializers.SerializerMethodField(read_only=True)
    rubric_score = serializers.SerializerMethodField(read_only=True)
    rubric_breakdown = serializers.SerializerMethodField(read_only=True)

    def get_gate_outcome(self, obj: FinalScore) -> str:
        try:
            return obj.application.gate_result.outcome
        except Exception:
            return "unknown"

    def get_semantic_score(self, obj: FinalScore) -> float | None:
        try:
            return obj.application.semantic_match.rrf_score
        except Exception:
            return None

    def get_rubric_score(self, obj: FinalScore) -> float | None:
        try:
            return obj.application.rubric_score.normalized_score
        except Exception:
            return None

    def get_rubric_breakdown(self, obj: FinalScore) -> dict | None:
        try:
            rubric: RubricScore = obj.application.rubric_score
            return RubricBreakdownSerializer(rubric).data
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Human Review (write — POST /api/applications/{id}/reviews/)
# ---------------------------------------------------------------------------

#: Decisions that legally require a non-empty reason for auditability.
OVERRIDE_DECISIONS = {
    HumanReview.Decision.OVERRIDE_PASS,
    HumanReview.Decision.OVERRIDE_FAIL,
}


class HumanReviewSerializer(serializers.Serializer):
    """
    Input serializer for creating a human review decision.

    Validation contract:
        - reviewer_email: required, valid email format.
        - decision: required, one of HumanReview.Decision choices.
        - override_reason: required and non-blank when decision is
          override_pass or override_fail; ignored (but accepted) otherwise.
    """
    reviewer_email = serializers.EmailField(required=True)
    decision = serializers.ChoiceField(
        choices=HumanReview.Decision.choices,
        required=True,
    )
    override_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        trim_whitespace=False,  # trimming is done in validate() so we can catch whitespace
    )

    def validate(self, data: dict) -> dict:
        """Cross-field validation: enforce reason for override decisions."""
        decision = data.get("decision", "")
        reason = data.get("override_reason", "").strip()

        if decision in OVERRIDE_DECISIONS and not reason:
            raise serializers.ValidationError(
                {
                    "override_reason": (
                        f"A non-empty reason is required for '{decision}' decisions. "
                        "This is mandatory for audit compliance."
                    )
                }
            )

        # Normalize: store stripped reason in validated data.
        data["override_reason"] = reason
        return data
