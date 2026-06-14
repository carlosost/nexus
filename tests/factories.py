"""
Test-only model factories using factory-boy.

WARNING: These factories are for TEST SUITES ONLY.
         DO NOT use factory.create() in the seed_demo management command —
         it causes IntegrityError on unique/unique_together constraints when run
         twice. The seed_demo command uses get_or_create with natural unique keys.

Usage in tests:
    from tests.factories import JobFactory, CandidateFactory, ApplicationFactory

    # In-memory instance (no DB hit):
    job = JobFactory.build()

    # Persisted instance (requires @pytest.mark.django_db):
    job = JobFactory.create()
    candidate = CandidateFactory.create()
    app = ApplicationFactory.create(job=job, candidate=candidate)
"""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from resume_pipeline.models import Application, Candidate, Job


class JobFactory(DjangoModelFactory):
    class Meta:
        model = Job
        # django_get_or_create prevents IntegrityError if factory is called
        # multiple times with the same title in a single test session.
        django_get_or_create = ("title",)

    title = factory.Sequence(lambda n: f"Backend Engineer Role {n}")
    description = factory.LazyAttribute(
        lambda o: f"Job description for {o.title}"
    )
    requirements_raw = factory.LazyFunction(
        lambda: {
            "required_skills": ["Python", "Django"],
            "preferred_skills": ["Docker"],
            "minimum_experience_years": 5,
        }
    )
    must_haves = factory.LazyFunction(
        lambda: {
            "min_experience": {
                "type": "years_experience",
                "minimum_years": 5,
            },
            "python_required": {
                "type": "keyword_presence",
                "keywords": ["Python"],
                "sections": ["skills", "experience"],
            },
        }
    )


class CandidateFactory(DjangoModelFactory):
    class Meta:
        model = Candidate
        django_get_or_create = ("email",)

    name = factory.Sequence(lambda n: f"Test Candidate {n}")
    email = factory.Sequence(lambda n: f"candidate{n}@test.example.com")
    resume_raw = factory.LazyAttribute(
        lambda o: f"Resume for {o.name}. 5 years Python experience."
    )
    resume_parsed = factory.LazyFunction(
        lambda: {
            "total_experience_years": 5,
            "experience": "Python developer at TestCo 2019-2024.",
            "skills": "Python Django PostgreSQL",
            "education": "BSc Computer Science 2018",
            "certifications": [],
        }
    )


class ApplicationFactory(DjangoModelFactory):
    class Meta:
        model = Application
        django_get_or_create = ("job", "candidate")

    job = factory.SubFactory(JobFactory)
    candidate = factory.SubFactory(CandidateFactory)
    status = Application.Status.PENDING
