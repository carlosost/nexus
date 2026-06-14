"""
M0.6 — Demo seed data specification.

Pure Python — no Django imports. Import this from unit tests and from seed_demo.py.

Design rules:
  - Job.title is the natural unique key for get_or_create.
  - Candidate.email is the natural unique key for get_or_create.
  - resume_parsed for each candidate is crafted to produce a specific gate outcome:
      Alice  → gate PASS   (all criteria met)
      Bob    → gate UNKNOWN (total_experience_years absent → experience check unknown)
      Carol  → gate FAIL   (2 years < 5 required, Django keyword absent)

Hard gate criteria wired to the job:
  "min_experience"   : years_experience ≥ 5
  "python_required"  : keyword_presence ["Python"] in skills + experience
  "django_required"  : keyword_presence ["Django"] in skills + experience
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Job spec
# ---------------------------------------------------------------------------

JOB_SPEC: dict = {
    "title": "Senior Backend Engineer",
    "description": (
        "We are looking for a Senior Backend Engineer with deep Python and Django "
        "experience to lead backend development of our data platform."
    ),
    "requirements_raw": {
        "required_skills": ["Python", "Django", "PostgreSQL", "REST APIs"],
        "preferred_skills": ["Redis", "Docker", "Kubernetes"],
        "minimum_experience_years": 5,
    },
    "must_haves": {
        "min_experience": {
            "type": "years_experience",
            "minimum_years": 5,
        },
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
    },
}


# ---------------------------------------------------------------------------
# Candidate specs — ordered by expected pipeline outcome
# ---------------------------------------------------------------------------

CANDIDATE_SPECS: list[dict] = [
    # ------------------------------------------------------------------
    # Candidate A — Alice Chen
    # Expected gate outcome: PASS on all criteria
    # Expected final score: high (> 0.70)
    # ------------------------------------------------------------------
    {
        "name": "Alice Chen",
        "email": "alice@demo.example.com",
        "resume_raw": (
            "Alice Chen — alice@demo.example.com\n\n"
            "Experience\n"
            "Senior Python Engineer, Acme Corp, 2017–2024 (7 years)\n"
            "Led Django monolith-to-microservices migration. Reduced p99 latency "
            "by 40 ms. Managed team of 6 engineers.\n\n"
            "Skills\n"
            "Python Django PostgreSQL Redis Docker Kubernetes REST APIs\n\n"
            "Education\n"
            "BSc Computer Science, University of California, Berkeley, 2016\n\n"
            "Certifications\n"
            "AWS Solutions Architect Professional (2022)\n"
        ),
        "resume_parsed": {
            "total_experience_years": 7,
            "summary": "Senior backend engineer with 7 years of Python and Django development.",
            "experience": (
                "Senior Python Engineer at Acme Corp 2017-2024. "
                "Led Django monolith-to-microservices migration. "
                "Reduced p99 latency by 40ms. Managed team of 6 engineers."
            ),
            "skills": "Python Django PostgreSQL Redis Docker Kubernetes REST APIs",
            "education": "BSc Computer Science, University of California, Berkeley, 2016",
            "certifications": ["AWS Solutions Architect Professional"],
        },
    },

    # ------------------------------------------------------------------
    # Candidate B — Bob Rodriguez
    # Expected gate outcome: UNKNOWN
    # Reason: total_experience_years is absent from resume_parsed →
    #         years_experience criterion returns UNKNOWN.
    #         Python and Django are present so those criteria PASS.
    #         Aggregate: UNKNOWN (UNKNOWN > PASS; no FAIL present).
    # Expected final score: pipeline continues with reduced confidence.
    # ------------------------------------------------------------------
    {
        "name": "Bob Rodriguez",
        "email": "bob@demo.example.com",
        "resume_raw": (
            "Bob Rodriguez — bob@demo.example.com\n\n"
            "Profile\n"
            "Backend engineer transitioning from PHP to Python/Django.\n\n"
            "Experience\n"
            "Python Developer, StartupX, 2020–2024\n"
            "Built REST APIs using Django REST Framework.\n\n"
            "Skills\n"
            "Python Django REST Framework PostgreSQL\n\n"
            "Education\n"
            "BSc Software Engineering, 2019\n"
        ),
        "resume_parsed": {
            # NOTE: total_experience_years intentionally absent.
            # This triggers GateOutcome.UNKNOWN on the years_experience criterion.
            "summary": "Backend engineer with Python and Django experience.",
            "experience": (
                "Python Developer at StartupX 2020-2024. "
                "Built REST APIs using Django REST Framework. "
                "Migrated legacy PHP endpoints to Python."
            ),
            "skills": "Python Django REST Framework PostgreSQL",
            "education": "BSc Software Engineering 2019",
            "certifications": [],
        },
    },

    # ------------------------------------------------------------------
    # Candidate C — Carol Smith
    # Expected gate outcome: FAIL
    # Reason: 2 years < 5 required (FAIL), Django not in skills or experience (FAIL).
    #         Python is present (PASS on python_required).
    #         Aggregate: FAIL (FAIL takes precedence).
    # Expected final score: 0.0 (hard-gate short-circuit).
    # ------------------------------------------------------------------
    {
        "name": "Carol Smith",
        "email": "carol@demo.example.com",
        "resume_raw": (
            "Carol Smith — carol@demo.example.com\n\n"
            "Experience\n"
            "Junior Python Developer, WebAgency, 2022–2024 (2 years)\n"
            "Built small web applications using Flask.\n\n"
            "Skills\n"
            "Python Flask SQLite HTML CSS\n\n"
            "Education\n"
            "Diploma in Web Development, 2022\n"
        ),
        "resume_parsed": {
            "total_experience_years": 2,
            "summary": "Junior Python developer with 2 years of experience.",
            "experience": (
                "Junior Python Developer at WebAgency 2022-2024. "
                "Built small web applications using Flask and SQLite."
            ),
            "skills": "Python Flask SQLite HTML CSS",
            "education": "Diploma in Web Development 2022",
            "certifications": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Convenience lookups
# ---------------------------------------------------------------------------

CANDIDATES_BY_EMAIL: dict[str, dict] = {
    c["email"]: c for c in CANDIDATE_SPECS
}
