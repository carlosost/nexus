"""
run_pipeline management command.

Runs the 4-stage evaluation pipeline for one or more Applications and
persists the results (HardGateResult, SemanticMatchResult, RubricScore,
FinalScore) to the database.

Usage:
    # Run for a specific application UUID
    python manage.py run_pipeline <uuid>

    # Run for all pending applications
    python manage.py run_pipeline --all

    # Re-run even if already scored (overwrites existing results)
    python manage.py run_pipeline <uuid> --force
    python manage.py run_pipeline --all --force

    # Use a specific LLM backend (overrides LLM_BACKEND env var)
    python manage.py run_pipeline --all --backend mock
    python manage.py run_pipeline --all --backend openai
    python manage.py run_pipeline --all --backend anthropic
"""

from __future__ import annotations

import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from resume_pipeline.models import Application, FinalScore
from resume_pipeline.services import PipelineService


class Command(BaseCommand):
    help = "Run the evaluation pipeline for one or all pending Applications."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "application_id",
            nargs="?",
            help="UUID of the Application to evaluate.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            default=False,
            help="Run for all pending applications.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Re-run even if the application already has a FinalScore.",
        )
        parser.add_argument(
            "--backend",
            choices=["mock", "openai", "anthropic"],
            default=None,
            help="LLM backend to use (overrides LLM_BACKEND env var).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["backend"]:
            os.environ["LLM_BACKEND"] = options["backend"]

        if options["all"]:
            qs = Application.objects.select_related("candidate", "job")
            if not options["force"]:
                qs = qs.filter(status=Application.Status.PENDING)
            if not qs.exists():
                self.stdout.write("No applications found.")
                return
            applications = list(qs)
        elif options["application_id"]:
            try:
                applications = [
                    Application.objects.select_related("candidate", "job").get(
                        pk=options["application_id"]
                    )
                ]
            except Application.DoesNotExist:
                raise CommandError(f"Application {options['application_id']} not found.")
        else:
            raise CommandError("Provide an application UUID or use --all.")

        service = PipelineService()
        passed = failed = skipped = 0

        for app in applications:
            if not options["force"] and FinalScore.objects.filter(application=app).exists():
                self.stdout.write(f"  SKIP  {app.id}  {app.candidate.name} (already scored)")
                skipped += 1
                continue

            try:
                result = service.run(app)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  OK    {app.id}  {app.candidate.name:<20}"
                        f"  gate={result['gate_outcome']:<8}"
                        f"  final={result['final_score']:.3f}"
                        f"  status={result['status']}"
                    )
                )
                passed += 1
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"  ERROR {app.id}  {app.candidate.name}  {exc}")
                )
                failed += 1

        self.stdout.write(
            f"\nDone — passed={passed}  failed={failed}  skipped={skipped}"
        )
