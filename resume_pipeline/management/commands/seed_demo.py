"""
M0.6 — seed_demo management command.

Usage:
    python manage.py seed_demo            # idempotent: safe to run repeatedly
    python manage.py seed_demo --purge    # wipe demo data first (dev only)

Idempotency:
    Uses get_or_create with natural unique keys so the command exits 0 on every
    subsequent run with zero data mutations. Never uses factory-boy at runtime.

Purge guard:
    --purge is blocked in production (IS_PRODUCTION=True setting). It exists
    only for development resets of the demo dataset.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from resume_pipeline.models import Job, Candidate, Application
from resume_pipeline.management.commands._seed_data import (
    JOB_SPEC,
    CANDIDATE_SPECS,
)

logger = logging.getLogger("pipeline.audit")


class Command(BaseCommand):
    help = "Seed the database with demo data (1 Job + 3 Candidates). Idempotent."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--purge",
            action="store_true",
            default=False,
            help="Delete all demo records before seeding. Dev environments only.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["purge"]:
            self._purge()

        jobs_created, candidates_created = self._seed()

        idempotent = jobs_created == 0 and candidates_created == 0
        completion_event = {
            "event": "demo_seed_completed",
            "jobs_created": jobs_created,
            "candidates_created": candidates_created,
            "idempotent": idempotent,
        }
        logger.info(json.dumps(completion_event))
        self.stdout.write(
            self.style.SUCCESS(
                f"seed_demo complete — "
                f"jobs_created={jobs_created} "
                f"candidates_created={candidates_created} "
                f"idempotent={idempotent}"
            )
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _seed(self) -> tuple[int, int]:
        """
        Create demo records using get_or_create with natural unique keys.
        Returns (jobs_created, candidates_created).
        """
        # Job — unique on title
        job, job_created = Job.objects.get_or_create(
            title=JOB_SPEC["title"],
            defaults={
                "description": JOB_SPEC["description"],
                "requirements_raw": JOB_SPEC["requirements_raw"],
                "must_haves": JOB_SPEC["must_haves"],
            },
        )

        candidates_created = 0
        for spec in CANDIDATE_SPECS:
            # Candidate — unique on email
            candidate, cand_created = Candidate.objects.get_or_create(
                email=spec["email"],
                defaults={
                    "name": spec["name"],
                    "resume_raw": spec["resume_raw"],
                    "resume_parsed": spec["resume_parsed"],
                },
            )
            if cand_created:
                candidates_created += 1

            # Application — unique on (job, candidate)
            Application.objects.get_or_create(
                job=job,
                candidate=candidate,
            )

        return (1 if job_created else 0), candidates_created

    def _purge(self) -> None:
        """
        Remove all demo records. Blocked in production.
        """
        is_production = getattr(settings, "IS_PRODUCTION", False)
        if is_production:
            raise CommandError(
                "--purge is not allowed in production (IS_PRODUCTION=True)."
            )

        self.stdout.write("Purging demo data...")
        Application.objects.filter(job__title=JOB_SPEC["title"]).delete()
        Candidate.objects.filter(
            email__in=[s["email"] for s in CANDIDATE_SPECS]
        ).delete()
        Job.objects.filter(title=JOB_SPEC["title"]).delete()
        self.stdout.write("  Done.")
