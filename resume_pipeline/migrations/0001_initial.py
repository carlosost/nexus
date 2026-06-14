import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Job",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField()),
                ("requirements_raw", models.JSONField(default=dict)),
                ("must_haves", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Candidate",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("email", models.EmailField(unique=True)),
                ("resume_raw", models.TextField()),
                ("resume_parsed", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Application",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="applications", to="resume_pipeline.job")),
                ("candidate", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="applications", to="resume_pipeline.candidate")),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("gate_failed", "Gate Failed"),
                        ("gate_unknown", "Gate Unknown"),
                        ("gate_passed", "Gate Passed"),
                        ("scored", "Scored"),
                        ("under_review", "Under Human Review"),
                        ("approved", "Approved"),
                        ("rejected", "Rejected"),
                    ],
                    default="pending",
                    max_length=20,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="application",
            constraint=models.UniqueConstraint(fields=("job", "candidate"), name="unique_job_candidate"),
        ),
        migrations.AlterUniqueTogether(
            name="application",
            unique_together={("job", "candidate")},
        ),
        migrations.CreateModel(
            name="HardGateResult",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("application", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="gate_result", to="resume_pipeline.application")),
                ("outcome", models.CharField(
                    choices=[("pass", "Pass"), ("fail", "Fail"), ("unknown", "Unknown")],
                    max_length=10,
                )),
                ("criterion_results", models.JSONField(default=dict)),
                ("evaluated_at", models.DateTimeField(auto_now_add=True)),
                ("latency_ms", models.FloatField(help_text="Wall-clock time for the full gate evaluation")),
            ],
            options={"ordering": ["-evaluated_at"]},
        ),
        migrations.CreateModel(
            name="SectionEmbedding",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("candidate", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="embeddings", to="resume_pipeline.candidate")),
                ("section", models.CharField(
                    choices=[
                        ("summary", "Summary"),
                        ("experience", "Experience"),
                        ("skills", "Skills"),
                        ("education", "Education"),
                        ("certifications", "Certifications"),
                        ("projects", "Projects"),
                    ],
                    max_length=30,
                )),
                ("content", models.TextField(help_text="Raw text that was embedded")),
                ("embedding", models.JSONField(blank=True, help_text="Use pgvector.django.VectorField in production migration", null=True)),
                ("model_name", models.CharField(default="text-embedding-ada-002", max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["candidate", "section"]},
        ),
        migrations.AlterUniqueTogether(
            name="sectionembedding",
            unique_together={("candidate", "section")},
        ),
        migrations.CreateModel(
            name="JobSectionEmbedding",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="embeddings", to="resume_pipeline.job")),
                ("section", models.CharField(max_length=30)),
                ("content", models.TextField()),
                ("embedding", models.JSONField(blank=True, null=True)),
                ("model_name", models.CharField(default="text-embedding-ada-002", max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AlterUniqueTogether(
            name="jobsectionembedding",
            unique_together={("job", "section")},
        ),
        migrations.CreateModel(
            name="SemanticMatchResult",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("application", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="semantic_match", to="resume_pipeline.application")),
                ("rrf_score", models.FloatField()),
                ("section_scores", models.JSONField(default=dict)),
                ("lexical_rank", models.IntegerField(blank=True, null=True)),
                ("semantic_rank", models.IntegerField(blank=True, null=True)),
                ("evaluated_at", models.DateTimeField(auto_now_add=True)),
                ("latency_ms", models.FloatField()),
            ],
        ),
        migrations.CreateModel(
            name="RubricScore",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("application", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="rubric_score", to="resume_pipeline.application")),
                ("core_skills", models.FloatField()),
                ("relevant_experience", models.FloatField()),
                ("scope_impact", models.FloatField()),
                ("domain_alignment", models.FloatField()),
                ("education_certs", models.FloatField()),
                ("normalized_score", models.FloatField()),
                ("evidence_quality", models.FloatField(help_text="Heuristic 0–1: how well evidence supports the rubric scores")),
                ("model_name", models.CharField(max_length=100)),
                ("evaluated_at", models.DateTimeField(auto_now_add=True)),
                ("latency_ms", models.FloatField()),
            ],
        ),
        migrations.CreateModel(
            name="FinalScore",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("application", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="final_score", to="resume_pipeline.application")),
                ("score", models.FloatField()),
                ("gate_passed", models.BooleanField()),
                ("confidence", models.FloatField(blank=True, null=True)),
                ("computed_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="HumanReview",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("application", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to="resume_pipeline.application")),
                ("reviewer_email", models.EmailField()),
                ("decision", models.CharField(
                    choices=[
                        ("approve", "Approve"),
                        ("reject", "Reject"),
                        ("override_pass", "Override AI — Move to Pass"),
                        ("override_fail", "Override AI — Move to Fail"),
                    ],
                    max_length=20,
                )),
                ("override_reason", models.TextField(blank=True, default="", help_text="Required when decision is override_pass or override_fail")),
                ("ai_score_at_review", models.FloatField()),
                ("confidence_at_review", models.FloatField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-reviewed_at"]},
        ),
    ]
