"""
Migration: add is_evaluated_via_fallback flag to RubricScore.

This supports the LLM Resilience Fallback Framework — when a primary LLM
provider (e.g., OpenAI) fails after tenacity retries and a secondary provider
(e.g., Anthropic) completes the evaluation, the resulting RubricScore row is
stamped with is_evaluated_via_fallback=True.

This flag is:
  - Returned in the GET /api/applications/<uuid>/score/ response body.
  - Used by the frontend to render a visual alert on the reviewer score card.
  - Written to the pipeline.audit log as part of the score_computed event.

Safe to apply on a live database: BooleanField(default=False) requires no
back-fill and the ALTER TABLE is non-blocking on PostgreSQL 14+.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("resume_pipeline", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="rubricscore",
            name="is_evaluated_via_fallback",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "True when the primary LLM provider was unavailable and a "
                    "fallback provider completed this rubric evaluation."
                ),
            ),
        ),
    ]
