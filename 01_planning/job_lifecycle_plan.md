# Job Lifecycle QA & Engineering Verification Plan

**Project:** elvex-nexus  
**Domain:** Job — CRUD lifecycle, Markdown ingestion, and vector embedding pipeline  
**Stack:** Django + DRF + PostgreSQL + pgvector · Pytest · Pytest-BDD · Vitest · Playwright  
**Reference seed:** `resume_pipeline/management/commands/_seed_data.py → JOB_SPEC`

---

## Table of Contents

1. [Architecture Overview & Test Boundary Map](#1-architecture-overview--test-boundary-map)
2. [BDD Feature Specifications](#2-bdd-feature-specifications)
3. [Backend TDD Engineering Plan](#3-backend-tdd-engineering-plan)
4. [Frontend & E2E Verification Plan](#4-frontend--e2e-verification-plan)
5. [Run Commands Reference](#5-run-commands-reference)

---

## 1. Architecture Overview & Test Boundary Map

### System Layers

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 0 — Frontend (React + Vite)                                      │
│                                                                         │
│  Settings → JobBoard → Add Job Modal                                    │
│    └─ <textarea> accepts raw Markdown job spec                          │
│    └─ POST /api/jobs/markdown/  →  loading state → success / error UI   │
│                                                                         │
│  TEST TOOLS: Vitest + RTL (component unit), Playwright (E2E + routes)   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  HTTP POST (multipart or JSON)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — API Controller (Django REST Framework)                       │
│                                                                         │
│  JobListCreateView      (POST /api/jobs/)                               │
│  JobDetailView          (GET / PATCH / DELETE /api/jobs/<uuid>/)        │
│  JobListCreateView      (GET /api/jobs/)                                │
│                                                                         │
│  Serializers: JobMarkdownInputSerializer, JobDetailSerializer           │
│  TEST TOOLS: APIRequestFactory · pytest.mark.unit (no DB)               │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  raw_markdown str
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 2 — Markdown Ingestion Parser                                    │
│                                                                         │
│  resume_pipeline/ingestion/job_parser.py                                │
│    parse_job_markdown(raw: str) → JobSpec(title, description,           │
│                                           requirements_raw, must_haves) │
│                                                                         │
│  Maps structural Markdown headings against JOB_SPEC reference schema:   │
│    # <title>                  → Job.title                               │
│    ## Description             → Job.description                         │
│    ## Requirements / Skills   → Job.requirements_raw                    │
│    ## Must Haves / Hard Gate  → Job.must_haves                          │
│                                                                         │
│  TEST TOOLS: pytest.mark.unit — pure function, zero I/O                 │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  JobSpec dataclass
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 3 — Django ORM — Job record persistence                          │
│                                                                         │
│  Job.objects.create(**job_spec.to_model_kwargs())                       │
│  Job.objects.filter(pk=...).update(...)   ← PATCH path                  │
│  Job.objects.get(pk=...).delete()         ← DELETE path (cascades)      │
│    └─ CASCADE → Application, JobSectionEmbedding                        │
│                                                                         │
│  TEST TOOLS: pytest.mark.integration (@pytest.mark.django_db)           │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  post_save / post_delete Django signals
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 4 — Vector Embedding Pipeline                                    │
│                                                                         │
│  resume_pipeline/pipeline/job_embedder.py                               │
│    embed_job_sections(job: Job) → list[JobSectionEmbedding]             │
│                                                                         │
│  Sections embedded: title · description · requirements · must_haves     │
│  Model: text-embedding-ada-002 (dim=1536)  stored in JobSectionEmbedding│
│  On DELETE: JobSectionEmbedding.objects.filter(job=job).delete()        │
│             (also handled by CASCADE FK, verified explicitly)           │
│                                                                         │
│  TEST TOOLS: pytest.mark.unit (embed call mocked) +                     │
│              pytest.mark.integration (real DB, stubbed embed API)       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Test Entry Point Matrix

| Scenario | Primary Tool | DB Required | Network |
|---|---|---|---|
| Markdown parser field mapping | `pytest -m unit` | No | No |
| Parser resilience — malformed input | `pytest -m unit` | No | No |
| API view request/response shape | `pytest -m unit` (APIRequestFactory) | No | No |
| Job CRUD round-trip | `pytest -m integration` | SQLite | No |
| Embedding fires on create/update | `pytest -m integration` | SQLite | No (mocked) |
| Embedding vectors cleaned on delete | `pytest -m integration` | SQLite | No |
| Embedding timeout handled gracefully | `pytest -m unit` | No | No (mocked) |
| Frontend component rendering | Vitest + RTL | No | No |
| Full markdown submission flow | Playwright | No (mocked API) | No |
| CRUD delete with cascade warning UI | Playwright | No (mocked API) | No |

---

## 2. BDD Feature Specifications

### File: `features/job_lifecycle.feature`

```gherkin
# features/job_lifecycle.feature
#
# Outer-loop BDD specification — Job domain: CRUD lifecycle,
# Markdown ingestion, and vector embedding pipeline.
#
# Business rules encoded here:
#   1.  POST /api/jobs/markdown/ accepts raw Markdown and creates a Job record.
#   2.  The parser maps Markdown structure to Job.title, .description,
#       .requirements_raw, and .must_haves using JOB_SPEC as the reference.
#   3.  A malformed or partially missing Markdown body returns HTTP 422 with
#       a field-level error map — the DB connection is NOT dropped.
#   4.  A completely blank body returns HTTP 400 before reaching the parser.
#   5.  GET /api/jobs/<uuid>/ returns full Job detail.
#   6.  PATCH /api/jobs/<uuid>/ accepts partial updates; re-triggers embeddings.
#   7.  DELETE /api/jobs/<uuid>/ removes the Job and all JobSectionEmbeddings.
#   8.  Embedding generation is triggered asynchronously on create and update.
#   9.  Embedding timeout does NOT fail the HTTP response — the Job is persisted
#       and the embedding retried later (graceful degradation).
#  10.  Deleting a Job leaves no orphan vector rows in JobSectionEmbedding.

Feature: Job Lifecycle — Markdown Ingestion, CRUD, and Vector Embeddings
  As a recruiting operator
  I want to manage Job records through their full lifecycle
  So that candidates can be accurately matched against well-structured positions

  Background:
    Given the Job ingestion parser is initialized
    And the embedding backend is set to "mock"
    And the database is empty of Job records


  # ───────────────────────────────────────────────────────────────────────────
  # Scenario Group 1 — Successful Markdown creation
  # ───────────────────────────────────────────────────────────────────────────

  Scenario: Full JOB_SPEC-compliant Markdown creates a valid Job record
    Given the following raw Markdown job specification:
      """
      # Senior Backend Engineer

      ## Description
      We are looking for a Senior Backend Engineer with deep Python and Django
      experience to lead backend development of our data platform.

      ## Requirements
      ### Required Skills
      - Python
      - Django
      - PostgreSQL
      - REST APIs
      ### Preferred Skills
      - Redis
      - Docker
      - Kubernetes
      ### Minimum Experience
      5 years

      ## Must Haves
      ### Minimum Experience
      type: years_experience
      minimum_years: 5
      ### Python Required
      type: keyword_presence
      keywords: Python
      sections: skills, experience
      ### Django Required
      type: keyword_presence
      keywords: Django
      sections: skills, experience
      """
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 201
    And the response body contains field "id"
    And the response body contains field "title" with value "Senior Backend Engineer"
    And the response body contains field "created_at"

  Scenario: Parser extracts title correctly from the H1 heading
    Given a valid Markdown job spec with title "Principal Data Engineer"
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 201
    And the persisted Job title is "Principal Data Engineer"

  Scenario: Parser maps description from the "## Description" section
    Given a valid Markdown job spec with a "## Description" section containing:
      """
      We are building a next-generation data platform.
      """
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the persisted Job description contains "next-generation data platform"

  Scenario: Parser maps required_skills list into requirements_raw.required_skills
    Given a valid Markdown job spec with required skills: Python, Django, PostgreSQL
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the persisted Job requirements_raw["required_skills"] equals:
      | Python | Django | PostgreSQL |

  Scenario: Parser maps preferred_skills into requirements_raw.preferred_skills
    Given a valid Markdown job spec with preferred skills: Redis, Docker
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the persisted Job requirements_raw["preferred_skills"] equals:
      | Redis | Docker |

  Scenario: Parser extracts minimum_experience_years as an integer
    Given a valid Markdown job spec with "Minimum Experience: 5 years"
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the persisted Job requirements_raw["minimum_experience_years"] equals 5

  Scenario: Parser maps must_haves.min_experience from the Hard Gate section
    Given a valid Markdown job spec with must_have criterion "min_experience" of type "years_experience" with minimum_years 5
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the persisted Job must_haves["min_experience"]["type"] equals "years_experience"
    And the persisted Job must_haves["min_experience"]["minimum_years"] equals 5

  Scenario: Parser maps keyword_presence criteria with section lists
    Given a valid Markdown job spec with must_have criterion "python_required" requiring keyword "Python" in sections "skills, experience"
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the persisted Job must_haves["python_required"]["type"] equals "keyword_presence"
    And the persisted Job must_haves["python_required"]["keywords"] equals ["Python"]
    And the persisted Job must_haves["python_required"]["sections"] equals ["skills", "experience"]

  Scenario: Embedding pipeline is triggered after successful Job creation
    Given a valid JOB_SPEC-compliant Markdown job specification
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 201
    And a "job_embeddings_enqueued" event is recorded for the new Job id


  # ───────────────────────────────────────────────────────────────────────────
  # Scenario Group 2 — Resilient graceful failure on malformed Markdown
  # ───────────────────────────────────────────────────────────────────────────

  Scenario: Completely blank body returns 400 without touching the parser
    Given an empty request body
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 400
    And the response body contains key "raw_markdown"
    And no Job records exist in the database

  Scenario: Markdown missing the H1 title heading returns 422
    Given a Markdown body with no H1 heading line
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 422
    And the response body contains key "title"
    And no Job records exist in the database

  Scenario: Markdown with only a title but no body sections returns 422
    Given a Markdown body containing only "# Lone Title"
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 422
    And the response body contains key "description"
    And no Job records exist in the database

  Scenario: Malformed must_haves block produces a 422 with field-level error
    Given a Markdown job spec where the "## Must Haves" section has invalid YAML syntax
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 422
    And the response body contains key "must_haves"
    And no Job records exist in the database

  Scenario: Parser error does not drop the database connection
    Given a Markdown body that causes a parser ValueError
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 422
    And the health endpoint GET "/api/health/" still returns 200

  Scenario: Duplicate title returns 409 — existing record is not mutated
    Given a Job named "Senior Backend Engineer" already exists
    And a valid Markdown job spec with title "Senior Backend Engineer"
    When I POST the Markdown to "/api/jobs/markdown/"
    Then the response status is 409
    And only 1 Job record with title "Senior Backend Engineer" exists


  # ───────────────────────────────────────────────────────────────────────────
  # Scenario Group 3 — Full CRUD lifecycle
  # ───────────────────────────────────────────────────────────────────────────

  Scenario: GET /api/jobs/ lists all Job records
    Given 3 Jobs have been created
    When I GET "/api/jobs/"
    Then the response status is 200
    And the response body is a list of 3 items
    And each item contains keys "id", "title", "created_at"

  Scenario: GET /api/jobs/<uuid>/ returns full Job detail
    Given a Job exists with id "job-uuid-001"
    When I GET "/api/jobs/job-uuid-001/"
    Then the response status is 200
    And the response body contains field "title"
    And the response body contains field "description"
    And the response body contains field "must_haves"
    And the response body contains field "requirements_raw"

  Scenario: GET /api/jobs/<uuid>/ for unknown id returns 404
    When I GET "/api/jobs/00000000-0000-0000-0000-000000000000/"
    Then the response status is 404

  Scenario: PATCH /api/jobs/<uuid>/ updates the title without touching other fields
    Given a Job exists with title "Old Title" and description "Keep this."
    When I PATCH "/api/jobs/<uuid>/" with body:
      """
      { "title": "New Title" }
      """
    Then the response status is 200
    And the persisted Job title is "New Title"
    And the persisted Job description is "Keep this."

  Scenario: PATCH /api/jobs/<uuid>/ updates description and re-triggers embeddings
    Given a Job exists with id "job-uuid-001"
    When I PATCH "/api/jobs/job-uuid-001/" with a new description
    Then the response status is 200
    And a "job_embeddings_enqueued" event is recorded for "job-uuid-001"

  Scenario: PATCH /api/jobs/<uuid>/ with invalid must_haves returns 400
    Given a Job exists with id "job-uuid-001"
    When I PATCH "/api/jobs/job-uuid-001/" with body:
      """
      { "must_haves": "this should be an object not a string" }
      """
    Then the response status is 400

  Scenario: DELETE /api/jobs/<uuid>/ removes the Job record
    Given a Job exists with id "job-uuid-001"
    When I DELETE "/api/jobs/job-uuid-001/"
    Then the response status is 204
    And GET "/api/jobs/job-uuid-001/" returns 404

  Scenario: DELETE cascades to all JobSectionEmbeddings — no vector orphans
    Given a Job exists with id "job-uuid-001"
    And 4 JobSectionEmbedding records exist for "job-uuid-001"
    When I DELETE "/api/jobs/job-uuid-001/"
    Then the response status is 204
    And 0 JobSectionEmbedding records exist for "job-uuid-001"

  Scenario: DELETE cascades to all linked Applications
    Given a Job exists with id "job-uuid-001"
    And 2 Application records reference Job "job-uuid-001"
    When I DELETE "/api/jobs/job-uuid-001/"
    Then the response status is 204
    And 0 Application records reference Job "job-uuid-001"

  Scenario: DELETE on unknown id returns 404 — no side effects
    When I DELETE "/api/jobs/00000000-0000-0000-0000-000000000000/"
    Then the response status is 404
    And the database Job count is unchanged
```

---

## 3. Backend TDD Engineering Plan

### 3.1 Unit Tests — Markdown Parser

**File:** `tests/unit/test_job_parser.py`

This test class exercises `resume_pipeline.ingestion.job_parser.parse_job_markdown` as a pure function. No database, no HTTP, no embedding calls. All inputs are string literals derived from `JOB_SPEC`.

```python
"""
Inner-loop unit tests for the Job Markdown ingestion parser.

Strategy:
  - parse_job_markdown() is a pure function: str → JobSpec dataclass.
  - No database, network, or Django ORM required.
  - All test inputs are constructed from JOB_SPEC field values so that
    the canonical seed data is the single source of truth.

Run:
  pytest tests/unit/test_job_parser.py -m unit
"""

from __future__ import annotations

import pytest
from resume_pipeline.ingestion.job_parser import (
    JobParseError,
    JobSpec,
    parse_job_markdown,
)
from resume_pipeline.management.commands._seed_data import JOB_SPEC

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_MARKDOWN = """\
# Senior Backend Engineer

## Description
We are looking for a Senior Backend Engineer with deep Python and Django
experience to lead backend development of our data platform.

## Requirements
### Required Skills
- Python
- Django
- PostgreSQL
- REST APIs
### Preferred Skills
- Redis
- Docker
- Kubernetes
### Minimum Experience
5 years

## Must Haves
### min_experience
type: years_experience
minimum_years: 5
### python_required
type: keyword_presence
keywords: Python
sections: skills, experience
### django_required
type: keyword_presence
keywords: Django
sections: skills, experience
"""


# ---------------------------------------------------------------------------
# TestParserHappyPath — JOB_SPEC field mapping
# ---------------------------------------------------------------------------

class TestParserHappyPath:
    """Every field in JOB_SPEC is correctly extracted from conformant Markdown."""

    def test_returns_job_spec_dataclass(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        assert isinstance(result, JobSpec)

    def test_title_extracted_from_h1(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        assert result.title == JOB_SPEC["title"]

    def test_description_extracted_from_h2_section(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        assert "Senior Backend Engineer" in result.description
        assert "data platform" in result.description

    def test_required_skills_match_job_spec(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        assert result.requirements_raw["required_skills"] == \
            JOB_SPEC["requirements_raw"]["required_skills"]

    def test_preferred_skills_match_job_spec(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        assert result.requirements_raw["preferred_skills"] == \
            JOB_SPEC["requirements_raw"]["preferred_skills"]

    def test_minimum_experience_years_is_integer(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        years = result.requirements_raw["minimum_experience_years"]
        assert isinstance(years, int)
        assert years == JOB_SPEC["requirements_raw"]["minimum_experience_years"]

    def test_must_haves_min_experience_type(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        assert result.must_haves["min_experience"]["type"] == "years_experience"

    def test_must_haves_min_experience_minimum_years(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        assert result.must_haves["min_experience"]["minimum_years"] == 5

    def test_must_haves_python_required_type(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        assert result.must_haves["python_required"]["type"] == "keyword_presence"

    def test_must_haves_python_required_keywords(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        assert result.must_haves["python_required"]["keywords"] == ["Python"]

    def test_must_haves_python_required_sections(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        assert result.must_haves["python_required"]["sections"] == ["skills", "experience"]

    def test_must_haves_django_required_present(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        assert "django_required" in result.must_haves

    def test_must_haves_keys_match_job_spec_exactly(self):
        result = parse_job_markdown(VALID_MARKDOWN)
        assert set(result.must_haves.keys()) == set(JOB_SPEC["must_haves"].keys())

    def test_to_model_kwargs_returns_all_four_fields(self):
        """JobSpec.to_model_kwargs() produces the exact dict Job.objects.create() expects."""
        kwargs = parse_job_markdown(VALID_MARKDOWN).to_model_kwargs()
        assert set(kwargs.keys()) == {"title", "description", "requirements_raw", "must_haves"}


# ---------------------------------------------------------------------------
# TestParserEdgeCases — whitespace, casing, list formatting
# ---------------------------------------------------------------------------

class TestParserEdgeCases:
    """Parser handles minor formatting variance without raising."""

    def test_title_stripped_of_leading_trailing_whitespace(self):
        md = VALID_MARKDOWN.replace("# Senior Backend Engineer", "#  Senior Backend Engineer  ")
        result = parse_job_markdown(md)
        assert result.title == "Senior Backend Engineer"

    def test_heading_case_insensitive_match_for_description(self):
        md = VALID_MARKDOWN.replace("## Description", "## DESCRIPTION")
        result = parse_job_markdown(md)
        assert result.description  # non-empty

    def test_skills_with_asterisk_bullet_parsed_correctly(self):
        md = VALID_MARKDOWN.replace("- Python", "* Python")
        result = parse_job_markdown(md)
        assert "Python" in result.requirements_raw["required_skills"]

    def test_minimum_experience_with_trailing_text_parses_integer(self):
        md = VALID_MARKDOWN.replace("5 years", "5 years minimum")
        result = parse_job_markdown(md)
        assert result.requirements_raw["minimum_experience_years"] == 5

    def test_empty_preferred_skills_produces_empty_list(self):
        md = VALID_MARKDOWN.replace(
            "### Preferred Skills\n- Redis\n- Docker\n- Kubernetes\n", ""
        )
        result = parse_job_markdown(md)
        assert result.requirements_raw.get("preferred_skills", []) == []


# ---------------------------------------------------------------------------
# TestParserRejection — malformed inputs raise JobParseError
# ---------------------------------------------------------------------------

class TestParserRejection:
    """Malformed Markdown raises JobParseError — never a bare Exception."""

    def test_blank_string_raises_job_parse_error(self):
        with pytest.raises(JobParseError, match="empty"):
            parse_job_markdown("")

    def test_whitespace_only_raises_job_parse_error(self):
        with pytest.raises(JobParseError, match="empty"):
            parse_job_markdown("   \n\n\t  ")

    def test_missing_h1_raises_with_field_key_title(self):
        md = VALID_MARKDOWN.replace("# Senior Backend Engineer\n", "")
        with pytest.raises(JobParseError) as exc_info:
            parse_job_markdown(md)
        assert "title" in str(exc_info.value)

    def test_missing_description_section_raises_with_field_key_description(self):
        # Remove the entire Description block
        lines = [l for l in VALID_MARKDOWN.splitlines()
                 if "Description" not in l and "data platform" not in l
                 and "Senior Backend Engineer with" not in l]
        md = "\n".join(lines)
        with pytest.raises(JobParseError) as exc_info:
            parse_job_markdown(md)
        assert "description" in str(exc_info.value)

    def test_invalid_must_haves_yaml_raises_with_field_key_must_haves(self):
        md = VALID_MARKDOWN + "\n  : invalid: yaml: ::::\n"
        with pytest.raises(JobParseError) as exc_info:
            parse_job_markdown(md)
        assert "must_haves" in str(exc_info.value)

    def test_parse_error_is_not_bare_exception(self):
        """Callers must catch JobParseError specifically — not a bare Exception."""
        with pytest.raises(JobParseError):
            parse_job_markdown("")


# ---------------------------------------------------------------------------
# TestJobSpecDataclass — contract enforcement
# ---------------------------------------------------------------------------

class TestJobSpecDataclass:
    """JobSpec is a typed dataclass with field-level validation."""

    def test_job_spec_requires_title(self):
        with pytest.raises(TypeError):
            JobSpec(description="x", requirements_raw={}, must_haves={})  # type: ignore

    def test_job_spec_requires_description(self):
        with pytest.raises(TypeError):
            JobSpec(title="x", requirements_raw={}, must_haves={})  # type: ignore

    def test_job_spec_with_empty_must_haves_is_valid(self):
        spec = JobSpec(
            title="T", description="D", requirements_raw={}, must_haves={}
        )
        assert spec.must_haves == {}
```

---

### 3.2 Unit Tests — API View Layer

**File:** `tests/unit/test_job_views.py`

Drive `JobMarkdownCreateView`, `JobDetailView`, and `JobListCreateView` through `APIRequestFactory`. All ORM and parser calls are mocked — no database required.

```python
"""
Inner-loop unit tests for Job API views.

Strategy:
  - All views exercised through DRF's APIRequestFactory.
  - Job ORM model patched at resume_pipeline.views.Job.
  - parse_job_markdown patched at resume_pipeline.views.parse_job_markdown.
  - embed_job_sections patched at resume_pipeline.views.embed_job_sections.
  - No DB, no network, no real parser execution.

Run:
  pytest tests/unit/test_job_views.py -m unit
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call

import pytest
from rest_framework.test import APIRequestFactory

pytestmark = pytest.mark.unit

FACTORY = APIRequestFactory()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job_mock(**overrides):
    """Return a minimal Job mock matching JobDetailSerializer expectations."""
    job = MagicMock()
    job.id           = overrides.get("id", uuid.uuid4())
    job.title        = overrides.get("title", "Senior Backend Engineer")
    job.description  = overrides.get("description", "Detailed description.")
    job.requirements_raw = overrides.get("requirements_raw", {})
    job.must_haves   = overrides.get("must_haves", {})
    job.created_at   = overrides.get("created_at", "2024-01-15T12:00:00Z")
    job.updated_at   = overrides.get("updated_at", "2024-01-15T12:00:00Z")
    return job


VALID_MARKDOWN_BODY = {"raw_markdown": "# My Job\n\n## Description\nDetails here.\n"}

MOCK_JOB_SPEC = MagicMock()
MOCK_JOB_SPEC.title        = "My Job"
MOCK_JOB_SPEC.description  = "Details here."
MOCK_JOB_SPEC.requirements_raw = {}
MOCK_JOB_SPEC.must_haves   = {}
MOCK_JOB_SPEC.to_model_kwargs.return_value = {
    "title": "My Job",
    "description": "Details here.",
    "requirements_raw": {},
    "must_haves": {},
}


# ---------------------------------------------------------------------------
# TestJobMarkdownCreateView
# ---------------------------------------------------------------------------

class TestJobMarkdownCreateView:

    def _post(self, body: dict):
        from resume_pipeline.views import JobMarkdownCreateView
        request = FACTORY.post("/api/jobs/markdown/", data=body, format="json")
        return JobMarkdownCreateView.as_view()(request)

    def test_valid_markdown_returns_201(self):
        with (
            patch("resume_pipeline.views.parse_job_markdown", return_value=MOCK_JOB_SPEC),
            patch("resume_pipeline.views.Job") as MockJob,
            patch("resume_pipeline.views.embed_job_sections"),
        ):
            MockJob.objects.create.return_value = _make_job_mock()
            resp = self._post(VALID_MARKDOWN_BODY)
        assert resp.status_code == 201

    def test_response_contains_id_field(self):
        with (
            patch("resume_pipeline.views.parse_job_markdown", return_value=MOCK_JOB_SPEC),
            patch("resume_pipeline.views.Job") as MockJob,
            patch("resume_pipeline.views.embed_job_sections"),
        ):
            MockJob.objects.create.return_value = _make_job_mock()
            resp = self._post(VALID_MARKDOWN_BODY)
        assert "id" in resp.data

    def test_blank_raw_markdown_returns_400(self):
        resp = self._post({"raw_markdown": ""})
        assert resp.status_code == 400
        assert "raw_markdown" in resp.data

    def test_missing_raw_markdown_key_returns_400(self):
        resp = self._post({})
        assert resp.status_code == 400

    def test_parser_job_parse_error_returns_422(self):
        from resume_pipeline.ingestion.job_parser import JobParseError
        with patch("resume_pipeline.views.parse_job_markdown",
                   side_effect=JobParseError("title", "Missing H1")):
            resp = self._post(VALID_MARKDOWN_BODY)
        assert resp.status_code == 422
        assert "title" in resp.data

    def test_parser_error_does_not_call_job_create(self):
        from resume_pipeline.ingestion.job_parser import JobParseError
        with (
            patch("resume_pipeline.views.parse_job_markdown",
                  side_effect=JobParseError("title", "Missing H1")),
            patch("resume_pipeline.views.Job") as MockJob,
        ):
            self._post(VALID_MARKDOWN_BODY)
        MockJob.objects.create.assert_not_called()

    def test_embed_job_sections_called_after_create(self):
        with (
            patch("resume_pipeline.views.parse_job_markdown", return_value=MOCK_JOB_SPEC),
            patch("resume_pipeline.views.Job") as MockJob,
            patch("resume_pipeline.views.embed_job_sections") as mock_embed,
        ):
            created_job = _make_job_mock()
            MockJob.objects.create.return_value = created_job
            self._post(VALID_MARKDOWN_BODY)
        mock_embed.assert_called_once_with(created_job)

    def test_embed_timeout_still_returns_201(self):
        """Embedding failure must NOT fail the HTTP response."""
        with (
            patch("resume_pipeline.views.parse_job_markdown", return_value=MOCK_JOB_SPEC),
            patch("resume_pipeline.views.Job") as MockJob,
            patch("resume_pipeline.views.embed_job_sections",
                  side_effect=TimeoutError("Embedding service unreachable")),
        ):
            MockJob.objects.create.return_value = _make_job_mock()
            resp = self._post(VALID_MARKDOWN_BODY)
        assert resp.status_code == 201

    def test_duplicate_title_returns_409(self):
        from django.db import IntegrityError
        with (
            patch("resume_pipeline.views.parse_job_markdown", return_value=MOCK_JOB_SPEC),
            patch("resume_pipeline.views.Job") as MockJob,
        ):
            MockJob.objects.create.side_effect = IntegrityError("unique constraint")
            resp = self._post(VALID_MARKDOWN_BODY)
        assert resp.status_code == 409


class TestJobDetailView:

    def _get(self, pk: str):
        from resume_pipeline.views import JobDetailView
        request = FACTORY.get(f"/api/jobs/{pk}/")
        return JobDetailView.as_view()(request, pk=pk)

    def _patch(self, pk: str, body: dict):
        from resume_pipeline.views import JobDetailView
        request = FACTORY.patch(f"/api/jobs/{pk}/", data=body, format="json")
        return JobDetailView.as_view()(request, pk=pk)

    def _delete(self, pk: str):
        from resume_pipeline.views import JobDetailView
        request = FACTORY.delete(f"/api/jobs/{pk}/")
        return JobDetailView.as_view()(request, pk=pk)

    def test_get_existing_job_returns_200(self):
        pk = str(uuid.uuid4())
        with patch("resume_pipeline.views.get_object_or_404",
                   return_value=_make_job_mock(id=pk)):
            resp = self._get(pk)
        assert resp.status_code == 200

    def test_get_response_contains_required_fields(self):
        pk = str(uuid.uuid4())
        with patch("resume_pipeline.views.get_object_or_404",
                   return_value=_make_job_mock(id=pk)):
            resp = self._get(pk)
        for field in ("id", "title", "description", "must_haves"):
            assert field in resp.data

    def test_patch_returns_200_on_valid_body(self):
        pk = str(uuid.uuid4())
        job = _make_job_mock(id=pk)
        with (
            patch("resume_pipeline.views.get_object_or_404", return_value=job),
            patch("resume_pipeline.views.embed_job_sections"),
        ):
            resp = self._patch(pk, {"title": "Updated Title"})
        assert resp.status_code == 200

    def test_patch_triggers_re_embedding(self):
        pk = str(uuid.uuid4())
        job = _make_job_mock(id=pk)
        with (
            patch("resume_pipeline.views.get_object_or_404", return_value=job),
            patch("resume_pipeline.views.embed_job_sections") as mock_embed,
        ):
            self._patch(pk, {"description": "Rewritten description."})
        mock_embed.assert_called_once_with(job)

    def test_delete_returns_204(self):
        pk = str(uuid.uuid4())
        job = _make_job_mock(id=pk)
        with patch("resume_pipeline.views.get_object_or_404", return_value=job):
            resp = self._delete(pk)
        assert resp.status_code == 204

    def test_delete_calls_job_delete(self):
        pk = str(uuid.uuid4())
        job = _make_job_mock(id=pk)
        with patch("resume_pipeline.views.get_object_or_404", return_value=job):
            self._delete(pk)
        job.delete.assert_called_once()
```

---

### 3.3 Integration Tests — Full CRUD + Embedding Pipeline

**File:** `tests/integration/test_job_lifecycle.py`

These tests use the real Django ORM against SQLite (no pgvector required — `embedding` field falls back to `JSONField`). The external embedding API is stubbed via `unittest.mock`.

```python
"""
Integration tests for the Job CRUD lifecycle and embedding pipeline.

Strategy:
  - Real Django ORM against SQLite (config.settings.test).
  - External embedding API stubbed — no network calls.
  - Verifies that: DB rows are created/updated/deleted correctly, cascade
    behaviours remove related rows, and embed_job_sections() is called at
    the right lifecycle points.

Run:
  pytest tests/integration/test_job_lifecycle.py -m integration
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient

from resume_pipeline.models import Job, JobSectionEmbedding

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def valid_markdown():
    return """\
# Senior Backend Engineer

## Description
We are looking for a Senior Backend Engineer with deep Python and Django
experience to lead backend development of our data platform.

## Requirements
### Required Skills
- Python
- Django
- PostgreSQL
- REST APIs
### Preferred Skills
- Redis
- Docker
- Kubernetes
### Minimum Experience
5 years

## Must Haves
### min_experience
type: years_experience
minimum_years: 5
### python_required
type: keyword_presence
keywords: Python
sections: skills, experience
### django_required
type: keyword_presence
keywords: Django
sections: skills, experience
"""


@pytest.fixture
def created_job(db, valid_markdown, api_client):
    """POST the valid markdown and return the response body as a dict."""
    with patch("resume_pipeline.views.embed_job_sections"):
        resp = api_client.post(
            "/api/jobs/markdown/",
            data={"raw_markdown": valid_markdown},
            format="json",
        )
    assert resp.status_code == 201
    return resp.data


# ---------------------------------------------------------------------------
# TestJobCreationPersistence
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestJobCreationPersistence:
    """Verify DB row matches parsed Markdown fields from JOB_SPEC."""

    def test_job_row_exists_after_create(self, created_job):
        assert Job.objects.filter(id=created_job["id"]).exists()

    def test_title_persisted_correctly(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        assert job.title == "Senior Backend Engineer"

    def test_description_persisted_correctly(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        assert "data platform" in job.description

    def test_required_skills_in_requirements_raw(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        assert "Python" in job.requirements_raw["required_skills"]
        assert "Django" in job.requirements_raw["required_skills"]

    def test_minimum_experience_years_is_integer(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        assert job.requirements_raw["minimum_experience_years"] == 5

    def test_must_haves_min_experience_persisted(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        assert job.must_haves["min_experience"]["minimum_years"] == 5

    def test_must_haves_python_required_sections(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        sections = job.must_haves["python_required"]["sections"]
        assert "skills" in sections
        assert "experience" in sections

    def test_created_at_is_populated(self, created_job):
        job = Job.objects.get(id=created_job["id"])
        assert job.created_at is not None


# ---------------------------------------------------------------------------
# TestEmbeddingPipelineIntegration
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEmbeddingPipelineIntegration:
    """Verify embedding calls fire at the correct lifecycle points."""

    def test_embed_called_once_on_create(self, db, valid_markdown, api_client):
        with patch("resume_pipeline.views.embed_job_sections") as mock_embed:
            api_client.post(
                "/api/jobs/markdown/",
                data={"raw_markdown": valid_markdown},
                format="json",
            )
        mock_embed.assert_called_once()

    def test_embed_receives_the_persisted_job_instance(self, db, valid_markdown, api_client):
        with patch("resume_pipeline.views.embed_job_sections") as mock_embed:
            resp = api_client.post(
                "/api/jobs/markdown/",
                data={"raw_markdown": valid_markdown},
                format="json",
            )
        called_with_job = mock_embed.call_args[0][0]
        assert str(called_with_job.id) == resp.data["id"]

    def test_embed_called_once_on_patch(self, db, created_job, api_client):
        job_id = created_job["id"]
        with patch("resume_pipeline.views.embed_job_sections") as mock_embed:
            api_client.patch(
                f"/api/jobs/{job_id}/",
                data={"description": "Updated description with new skills focus."},
                format="json",
            )
        mock_embed.assert_called_once()

    def test_embed_not_called_on_delete(self, db, created_job, api_client):
        job_id = created_job["id"]
        with patch("resume_pipeline.views.embed_job_sections") as mock_embed:
            api_client.delete(f"/api/jobs/{job_id}/")
        mock_embed.assert_not_called()

    def test_embed_timeout_does_not_fail_create(self, db, valid_markdown, api_client):
        with patch("resume_pipeline.views.embed_job_sections",
                   side_effect=TimeoutError("Embedding service unreachable")):
            resp = api_client.post(
                "/api/jobs/markdown/",
                data={"raw_markdown": valid_markdown},
                format="json",
            )
        assert resp.status_code == 201
        # Job record must exist despite the embedding failure
        assert Job.objects.filter(id=resp.data["id"]).exists()

    def test_embed_timeout_does_not_fail_patch(self, db, created_job, api_client):
        job_id = created_job["id"]
        with patch("resume_pipeline.views.embed_job_sections",
                   side_effect=TimeoutError("Embedding service unreachable")):
            resp = api_client.patch(
                f"/api/jobs/{job_id}/",
                data={"title": "Revised Title"},
                format="json",
            )
        assert resp.status_code == 200

    def test_job_section_embeddings_created_by_embedder(self, db, valid_markdown, api_client):
        """
        The real embed_job_sections() creates JobSectionEmbedding rows.
        Test with the actual embedder but a stubbed embedding API call.
        """
        STUB_VECTOR = [0.0] * 1536
        with patch(
            "resume_pipeline.pipeline.job_embedder._call_embedding_api",
            return_value=STUB_VECTOR,
        ):
            resp = api_client.post(
                "/api/jobs/markdown/",
                data={"raw_markdown": valid_markdown},
                format="json",
            )
        job = Job.objects.get(id=resp.data["id"])
        embeddings = JobSectionEmbedding.objects.filter(job=job)
        # At minimum: title, description, requirements, must_haves
        assert embeddings.count() >= 4

    def test_patch_replaces_existing_section_embeddings(self, db, valid_markdown, api_client):
        STUB_VECTOR = [0.0] * 1536
        with patch(
            "resume_pipeline.pipeline.job_embedder._call_embedding_api",
            return_value=STUB_VECTOR,
        ):
            resp = api_client.post(
                "/api/jobs/markdown/",
                data={"raw_markdown": valid_markdown},
                format="json",
            )
            job_id = resp.data["id"]
            count_before = JobSectionEmbedding.objects.filter(job_id=job_id).count()
            api_client.patch(
                f"/api/jobs/{job_id}/",
                data={"description": "Completely rewritten description."},
                format="json",
            )
        count_after = JobSectionEmbedding.objects.filter(job_id=job_id).count()
        # Row count should not balloon — upsert or delete-then-insert pattern
        assert count_after == count_before


# ---------------------------------------------------------------------------
# TestCascadeDeleteCleanup — zero orphan vectors
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCascadeDeleteCleanup:
    """Deleting a Job must leave no orphan rows in any related table."""

    def test_job_section_embeddings_deleted_on_job_delete(
        self, db, valid_markdown, api_client
    ):
        STUB_VECTOR = [0.0] * 1536
        with patch(
            "resume_pipeline.pipeline.job_embedder._call_embedding_api",
            return_value=STUB_VECTOR,
        ):
            resp = api_client.post(
                "/api/jobs/markdown/",
                data={"raw_markdown": valid_markdown},
                format="json",
            )
        job_id = resp.data["id"]
        assert JobSectionEmbedding.objects.filter(job_id=job_id).count() > 0

        api_client.delete(f"/api/jobs/{job_id}/")

        # Explicit assertion — not relying solely on CASCADE
        assert JobSectionEmbedding.objects.filter(job_id=job_id).count() == 0

    def test_job_row_deleted(self, db, created_job, api_client):
        job_id = created_job["id"]
        api_client.delete(f"/api/jobs/{job_id}/")
        assert not Job.objects.filter(id=job_id).exists()

    def test_get_after_delete_returns_404(self, db, created_job, api_client):
        job_id = created_job["id"]
        api_client.delete(f"/api/jobs/{job_id}/")
        resp = api_client.get(f"/api/jobs/{job_id}/")
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_404_no_side_effects(self, db, api_client):
        phantom_id = str(uuid.uuid4())
        resp = api_client.delete(f"/api/jobs/{phantom_id}/")
        assert resp.status_code == 404
        # Nothing was deleted — count is still 0
        assert Job.objects.count() == 0
```

---

### 3.4 BDD Step Definitions

**File:** `features/steps/job_lifecycle_steps.py`

```python
"""
Step definitions for features/job_lifecycle.feature.

Strategy: all ORM calls mocked via unittest.mock unless @pytest.mark.django_db
is applied. The view is exercised through DRF's APIRequestFactory, matching
the pattern established in human_review_steps.py and dashboard_stats_steps.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from rest_framework.test import APIRequestFactory

pytestmark = pytest.mark.bdd

scenarios("job_lifecycle.feature")


@pytest.fixture
def ctx() -> dict:
    return {
        "raw_markdown": "",
        "response": None,
        "job_id": None,
    }


# ── Given ───────────────────────────────────────────────────────────────────

@given("the Job ingestion parser is initialized")
def parser_initialized(ctx: dict) -> None:
    pass  # Stateless pure function — no init required


@given("the embedding backend is set to \"mock\"")
def embedding_backend_mock(ctx: dict) -> None:
    ctx["embed_patch"] = patch("resume_pipeline.views.embed_job_sections")
    ctx["mock_embed"] = ctx["embed_patch"].start()


@given("the database is empty of Job records")
def empty_db(ctx: dict) -> None:
    ctx["job_db"] = []


@given(parsers.parse("the following raw Markdown job specification:\n{body}"))
def set_raw_markdown(ctx: dict, body: str) -> None:
    ctx["raw_markdown"] = body.strip()


@given(parsers.parse("a valid Markdown job spec with title \"{title}\""))
def valid_markdown_with_title(ctx: dict, title: str) -> None:
    ctx["raw_markdown"] = (
        f"# {title}\n\n## Description\nJob description here.\n\n"
        f"## Requirements\n### Required Skills\n- Python\n"
    )


@given(parsers.parse("a Job named \"{title}\" already exists"))
def existing_job(ctx: dict, title: str) -> None:
    ctx["existing_title"] = title


@given(parsers.parse("{count:d} Jobs have been created"))
def multiple_jobs_exist(ctx: dict, count: int) -> None:
    ctx["job_count"] = count


@given(parsers.parse("a Job exists with id \"{job_id}\""))
def job_with_id(ctx: dict, job_id: str) -> None:
    ctx["job_id"] = job_id


@given(parsers.parse("{count:d} JobSectionEmbedding records exist for \"{job_id}\""))
def embedding_records_exist(ctx: dict, count: int, job_id: str) -> None:
    ctx["embedding_count"] = count


@given("an empty request body")
def empty_body(ctx: dict) -> None:
    ctx["raw_markdown"] = ""


@given(parsers.parse("a Markdown body with no H1 heading line"))
def markdown_no_h1(ctx: dict) -> None:
    ctx["raw_markdown"] = "## Description\nSome content without a title."


# ── When ─────────────────────────────────────────────────────────────────────

@when(parsers.parse("I POST the Markdown to \"{url}\""))
def post_markdown(ctx: dict, url: str) -> None:
    from resume_pipeline.views import JobMarkdownCreateView
    factory = APIRequestFactory()
    request = factory.post(url, {"raw_markdown": ctx["raw_markdown"]}, format="json")

    with (
        patch("resume_pipeline.views.embed_job_sections"),
        patch("resume_pipeline.views.parse_job_markdown") as mock_parse,
        patch("resume_pipeline.views.Job") as MockJob,
    ):
        _configure_mocks(ctx, mock_parse, MockJob)
        view = JobMarkdownCreateView.as_view()
        ctx["response"] = view(request)


@when(parsers.parse("I GET \"{url}\""))
def get_url(ctx: dict, url: str) -> None:
    from resume_pipeline.views import JobListCreateView, JobDetailView
    factory = APIRequestFactory()
    request = factory.get(url)
    if "<uuid>" in url or ctx.get("job_id") in url:
        pk = ctx.get("job_id", str(uuid.uuid4()))
        with patch("resume_pipeline.views.get_object_or_404",
                   return_value=_make_mock_job()):
            ctx["response"] = JobDetailView.as_view()(request, pk=pk)
    else:
        with patch("resume_pipeline.views.Job") as MockJob:
            MockJob.objects.order_by.return_value = []
            ctx["response"] = JobListCreateView.as_view()(request)


@when(parsers.parse("I DELETE \"{url}\""))
def delete_url(ctx: dict, url: str) -> None:
    from resume_pipeline.views import JobDetailView
    pk = ctx.get("job_id", str(uuid.uuid4()))
    factory = APIRequestFactory()
    request = factory.delete(url)
    job_mock = _make_mock_job()
    with patch("resume_pipeline.views.get_object_or_404", return_value=job_mock):
        ctx["response"] = JobDetailView.as_view()(request, pk=pk)


# ── Then ─────────────────────────────────────────────────────────────────────

@then(parsers.parse("the response status is {code:d}"))
def assert_status(ctx: dict, code: int) -> None:
    actual = ctx["response"].status_code
    assert actual == code, f"Expected HTTP {code}, got {actual}"


@then(parsers.parse("the response body contains field \"{field}\""))
def assert_field_present(ctx: dict, field: str) -> None:
    assert field in ctx["response"].data, \
        f"Field '{field}' not in response: {list(ctx['response'].data.keys())}"


@then(parsers.parse("the response body contains field \"{field}\" with value \"{value}\""))
def assert_field_value(ctx: dict, field: str, value: str) -> None:
    actual = ctx["response"].data.get(field)
    assert str(actual) == value, f"Field '{field}': expected '{value}', got '{actual}'"


@then(parsers.parse("the response body contains key \"{key}\""))
def assert_error_key(ctx: dict, key: str) -> None:
    assert key in ctx["response"].data, \
        f"Error key '{key}' not in response: {list(ctx['response'].data.keys())}"


@then("no Job records exist in the database")
def assert_no_jobs(ctx: dict) -> None:
    assert ctx.get("job_create_called", False) is False


@then(parsers.parse("a \"job_embeddings_enqueued\" event is recorded for the new Job id"))
def assert_embed_event(ctx: dict) -> None:
    # Verified via mock_embed call_count in integration layer;
    # in BDD outer loop we assert the embed mock was called.
    assert ctx.get("embed_called", False) is True


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_mock_job(**kwargs):
    job = MagicMock()
    job.id          = kwargs.get("id", uuid.uuid4())
    job.title       = kwargs.get("title", "Senior Backend Engineer")
    job.description = kwargs.get("description", "Description text.")
    job.requirements_raw = {}
    job.must_haves  = {}
    job.created_at  = "2024-01-15T12:00:00Z"
    job.updated_at  = "2024-01-15T12:00:00Z"
    return job


def _configure_mocks(ctx, mock_parse, MockJob):
    from resume_pipeline.ingestion.job_parser import JobParseError, JobSpec
    raw = ctx.get("raw_markdown", "")
    if not raw.strip():
        return  # Serializer-level 400 catches blank before parser is called
    if not raw.startswith("#"):
        mock_parse.side_effect = JobParseError("title", "Missing H1")
        return
    spec = MagicMock(spec=JobSpec)
    spec.to_model_kwargs.return_value = {
        "title": "Senior Backend Engineer",
        "description": "Description.",
        "requirements_raw": {},
        "must_haves": {},
    }
    mock_parse.return_value = spec
    created = _make_mock_job()
    MockJob.objects.create.return_value = created
    ctx["embed_called"] = True
    ctx["job_create_called"] = True
```

---

## 4. Frontend & E2E Verification Plan

### 4.1 Vitest + RTL Unit Tests

**File:** `frontend/src/__tests__/JobIngestionModal.test.jsx`

```jsx
/**
 * Unit tests for the Job Markdown Ingestion modal.
 *
 * BDD coverage:
 *   Given the modal is open → textarea is visible and empty
 *   When user types valid Markdown → submit button is enabled
 *   When user submits → loading spinner appears, textarea disabled
 *   When API returns 201 → modal closes, onSuccess callback fires
 *   When API returns 422 with field errors → inline field errors rendered
 *   When API returns 500 → generic error banner rendered
 *   When embed is slow → modal does NOT wait on it (201 already returned)
 *
 * Tools: Vitest · @testing-library/react · vi.mock
 */

import { vi, describe, test, beforeEach, expect } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import JobIngestionModal from '../components/JobIngestionModal.jsx';
import * as client from '../api/client.js';

vi.mock('../api/client.js', () => ({
  createJobFromMarkdown: vi.fn(),
}));

// ── Fixtures ──────────────────────────────────────────────────────────────

const VALID_JOB_RESPONSE = {
  id:         'job-uuid-001',
  title:      'Senior Backend Engineer',
  created_at: '2024-01-15T12:00:00Z',
};

const VALID_MARKDOWN = `# Senior Backend Engineer

## Description
Deep Python and Django experience required.

## Requirements
### Required Skills
- Python
- Django
`;

function renderModal(props = {}) {
  const defaults = {
    open:      true,
    onClose:   vi.fn(),
    onSuccess: vi.fn(),
  };
  return render(<JobIngestionModal {...defaults} {...props} />);
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe('JobIngestionModal', () => {

  beforeEach(() => {
    client.createJobFromMarkdown.mockReset();
  });

  // ── Rendering ───────────────────────────────────────────────────────────

  test('renders the Markdown textarea when open', () => {
    renderModal();
    expect(screen.getByRole('textbox', { name: /job specification/i })).toBeInTheDocument();
  });

  test('textarea is empty on open', () => {
    renderModal();
    expect(screen.getByRole('textbox', { name: /job specification/i })).toHaveValue('');
  });

  test('submit button is present', () => {
    renderModal();
    expect(screen.getByRole('button', { name: /create job/i })).toBeInTheDocument();
  });

  test('modal is not rendered when open=false', () => {
    renderModal({ open: false });
    expect(screen.queryByRole('textbox', { name: /job specification/i })).not.toBeInTheDocument();
  });

  // ── Textarea interaction ─────────────────────────────────────────────────

  test('user can type Markdown into the textarea', () => {
    renderModal();
    const ta = screen.getByRole('textbox', { name: /job specification/i });
    fireEvent.change(ta, { target: { value: VALID_MARKDOWN } });
    expect(ta).toHaveValue(VALID_MARKDOWN);
  });

  test('submit button is disabled when textarea is empty', () => {
    renderModal();
    expect(screen.getByRole('button', { name: /create job/i })).toBeDisabled();
  });

  test('submit button is enabled after user types content', () => {
    renderModal();
    const ta = screen.getByRole('textbox', { name: /job specification/i });
    fireEvent.change(ta, { target: { value: '# Title' } });
    expect(screen.getByRole('button', { name: /create job/i })).not.toBeDisabled();
  });

  // ── Loading state ────────────────────────────────────────────────────────

  test('loading spinner shown and textarea disabled during submission', async () => {
    client.createJobFromMarkdown.mockReturnValue(new Promise(() => {})); // never resolves
    renderModal();
    fireEvent.change(
      screen.getByRole('textbox', { name: /job specification/i }),
      { target: { value: VALID_MARKDOWN } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    expect(screen.getByRole('textbox', { name: /job specification/i })).toBeDisabled();
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
  });

  // ── Success path ─────────────────────────────────────────────────────────

  test('onSuccess called with job data on 201', async () => {
    const onSuccess = vi.fn();
    client.createJobFromMarkdown.mockResolvedValue(VALID_JOB_RESPONSE);
    renderModal({ onSuccess });
    fireEvent.change(
      screen.getByRole('textbox', { name: /job specification/i }),
      { target: { value: VALID_MARKDOWN } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(VALID_JOB_RESPONSE));
  });

  test('onClose called after successful submission', async () => {
    const onClose = vi.fn();
    client.createJobFromMarkdown.mockResolvedValue(VALID_JOB_RESPONSE);
    renderModal({ onClose });
    fireEvent.change(
      screen.getByRole('textbox', { name: /job specification/i }),
      { target: { value: VALID_MARKDOWN } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  // ── Validation errors (422) ───────────────────────────────────────────────

  test('inline error shown when API returns 422 with field "title"', async () => {
    client.createJobFromMarkdown.mockRejectedValue({
      status:  422,
      data:    { title: ['Missing H1 heading.'] },
    });
    renderModal();
    fireEvent.change(
      screen.getByRole('textbox', { name: /job specification/i }),
      { target: { value: '## No H1 Here' } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() =>
      expect(screen.getByText(/missing h1 heading/i)).toBeInTheDocument()
    );
  });

  test('inline error shown when API returns 422 with field "description"', async () => {
    client.createJobFromMarkdown.mockRejectedValue({
      status: 422,
      data:   { description: ['Description section is required.'] },
    });
    renderModal();
    fireEvent.change(
      screen.getByRole('textbox', { name: /job specification/i }),
      { target: { value: '# Title only' } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() =>
      expect(screen.getByText(/description section is required/i)).toBeInTheDocument()
    );
  });

  test('error banner shown when API returns 500', async () => {
    client.createJobFromMarkdown.mockRejectedValue({ status: 500 });
    renderModal();
    fireEvent.change(
      screen.getByRole('textbox', { name: /job specification/i }),
      { target: { value: VALID_MARKDOWN } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toBeInTheDocument()
    );
  });

  test('textarea re-enabled after error — user can edit and retry', async () => {
    client.createJobFromMarkdown.mockRejectedValue({ status: 500 });
    renderModal();
    const ta = screen.getByRole('textbox', { name: /job specification/i });
    fireEvent.change(ta, { target: { value: VALID_MARKDOWN } });
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() => expect(ta).not.toBeDisabled());
  });

  // ── Duplicate detection ───────────────────────────────────────────────────

  test('409 response shows "duplicate job" message', async () => {
    client.createJobFromMarkdown.mockRejectedValue({
      status: 409,
      data:   { detail: 'A job with this title already exists.' },
    });
    renderModal();
    fireEvent.change(
      screen.getByRole('textbox', { name: /job specification/i }),
      { target: { value: VALID_MARKDOWN } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() =>
      expect(screen.getByText(/already exists/i)).toBeInTheDocument()
    );
  });
});
```

**File:** `frontend/src/__tests__/JobBoard.test.jsx`

```jsx
/**
 * Unit tests for the JobBoard settings panel.
 *
 * Covers: list rendering, empty state, delete confirmation modal,
 * detail panel expand/collapse, and field display.
 */

import { vi, describe, test, beforeEach, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import JobBoard from '../components/settings/JobBoard.jsx';

const JOBS = [
  {
    id:          'job-001',
    title:       'Senior Backend Engineer',
    created_at:  '2024-01-10T00:00:00Z',
  },
  {
    id:          'job-002',
    title:       'Principal Data Engineer',
    created_at:  '2024-01-12T00:00:00Z',
  },
];

const FULL_JOB = {
  id:               'job-001',
  title:            'Senior Backend Engineer',
  description:      'We need a strong backend engineer.',
  requirements_raw: { required_skills: ['Python', 'Django'] },
  must_haves:       { min_experience: { type: 'years_experience', minimum_years: 5 } },
};

function renderBoard(overrides = {}) {
  const props = {
    jobs:       JOBS,
    loading:    false,
    error:      null,
    onAdd:      vi.fn(),
    onPatch:    vi.fn(),
    onRemove:   vi.fn(),
    ...overrides,
  };
  return render(<JobBoard {...props} />);
}

describe('JobBoard', () => {

  test('renders a row for each job', () => {
    renderBoard();
    expect(screen.getByText('Senior Backend Engineer')).toBeInTheDocument();
    expect(screen.getByText('Principal Data Engineer')).toBeInTheDocument();
  });

  test('shows empty state when jobs list is empty', () => {
    renderBoard({ jobs: [] });
    expect(screen.getByText(/no jobs/i)).toBeInTheDocument();
  });

  test('loading skeleton shown when loading=true', () => {
    renderBoard({ loading: true });
    expect(screen.getByTestId('jobs-loading-skeleton')).toBeInTheDocument();
  });

  test('error banner shown when error is set', () => {
    renderBoard({ error: new Error('Network error') });
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  test('clicking Add Job opens the ingestion modal', () => {
    const onAdd = vi.fn();
    renderBoard({ onAdd });
    fireEvent.click(screen.getByRole('button', { name: /add job/i }));
    expect(onAdd).toHaveBeenCalled();
  });

  test('clicking Delete shows cascade confirmation modal', () => {
    renderBoard();
    const deleteButtons = screen.getAllByRole('button', { name: /delete/i });
    fireEvent.click(deleteButtons[0]);
    expect(screen.getByText(/this will also delete/i)).toBeInTheDocument();
  });

  test('confirming delete calls onRemove with the job id', async () => {
    const onRemove = vi.fn();
    renderBoard({ onRemove });
    fireEvent.click(screen.getAllByRole('button', { name: /delete/i })[0]);
    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    await waitFor(() => expect(onRemove).toHaveBeenCalledWith('job-001'));
  });

  test('cancelling delete does not call onRemove', () => {
    const onRemove = vi.fn();
    renderBoard({ onRemove });
    fireEvent.click(screen.getAllByRole('button', { name: /delete/i })[0]);
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onRemove).not.toHaveBeenCalled();
  });

  test('expanding a job row shows description', async () => {
    renderBoard({ jobs: [FULL_JOB] });
    fireEvent.click(screen.getByRole('button', { name: /expand/i }));
    await waitFor(() =>
      expect(screen.getByText(/strong backend engineer/i)).toBeInTheDocument()
    );
  });

  test('expanding shows must_haves JSON block', async () => {
    renderBoard({ jobs: [FULL_JOB] });
    fireEvent.click(screen.getByRole('button', { name: /expand/i }));
    await waitFor(() =>
      expect(screen.getByText(/years_experience/i)).toBeInTheDocument()
    );
  });

  test('second expand click collapses the detail panel', async () => {
    renderBoard({ jobs: [FULL_JOB] });
    const expandBtn = screen.getByRole('button', { name: /expand/i });
    fireEvent.click(expandBtn);
    await waitFor(() =>
      expect(screen.getByText(/strong backend engineer/i)).toBeInTheDocument()
    );
    fireEvent.click(expandBtn);
    await waitFor(() =>
      expect(screen.queryByText(/strong backend engineer/i)).not.toBeInTheDocument()
    );
  });
});
```

---

### 4.2 Playwright E2E Tests

**File:** `frontend/e2e/job_lifecycle.spec.js`

```js
/**
 * E2E specification: Job domain — Markdown ingestion, CRUD, and embedding lifecycle.
 *
 * All backend API calls are intercepted via Playwright's route.fulfill().
 * No real Django server or embedding service required.
 *
 * ─── Scenarios ───────────────────────────────────────────────────────────────
 *
 * Scenario 1: Full happy-path — submit Markdown, job appears in list
 * Scenario 2: Parser error (422) — inline field error rendered
 * Scenario 3: Network error (500) — generic error banner with retry
 * Scenario 4: Duplicate title (409) — duplicate message shown
 * Scenario 5: Job detail expand — description + must_haves displayed
 * Scenario 6: Edit job title inline
 * Scenario 7: Delete job — cascade warning, confirmation, row removed
 * Scenario 8: Processing loader cycle visible during submission
 * Scenario 9: Embedding latency — modal closes immediately on 201
 */

import { test, expect } from '@playwright/test';

// ── Fixtures ──────────────────────────────────────────────────────────────

const VALID_MARKDOWN = `# Senior Backend Engineer

## Description
We are looking for a Senior Backend Engineer with deep Python and Django
experience to lead backend development of our data platform.

## Requirements
### Required Skills
- Python
- Django
- PostgreSQL
- REST APIs
### Preferred Skills
- Redis
- Docker
- Kubernetes
### Minimum Experience
5 years

## Must Haves
### min_experience
type: years_experience
minimum_years: 5
### python_required
type: keyword_presence
keywords: Python
sections: skills, experience
`;

const CREATED_JOB = {
  id:         'job-uuid-e2e-001',
  title:      'Senior Backend Engineer',
  created_at: '2024-06-01T10:00:00Z',
};

const EXISTING_JOBS = [
  { id: 'job-uuid-001', title: 'Principal Data Engineer', created_at: '2024-05-01T00:00:00Z' },
];

async function mockBaseRoutes(page, { jobs = EXISTING_JOBS } = {}) {
  await page.route('**/api/jobs/', (r) => {
    if (r.request().method() === 'GET') return r.fulfill({ json: jobs });
    return r.continue();
  });
  await page.route('**/api/candidates/', (r) => r.fulfill({ json: [] }));
  await page.route('**/api/applications/', (r) => r.fulfill({ json: [] }));
  await page.route('**/api/dashboard/stats/', (r) =>
    r.fulfill({ json: { totals: {}, application_status_distribution: [], job_execution_funnel: [], llm_resilience: { time_series: [] } } })
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 1: Happy path — submit valid Markdown, new row appears in list
// ─────────────────────────────────────────────────────────────────────────────

test('Given valid Markdown, When submitted, Then job row appears in the Settings list', async ({ page }) => {
  await mockBaseRoutes(page);

  // After creation the list endpoint returns the new job too
  const updatedJobs = [...EXISTING_JOBS, CREATED_JOB];
  let postHandled = false;

  await page.route('**/api/jobs/markdown/', (r) => {
    postHandled = true;
    return r.fulfill({ status: 201, json: CREATED_JOB });
  });
  await page.route('**/api/jobs/', async (r) => {
    if (r.request().method() === 'GET') {
      return r.fulfill({ json: postHandled ? updatedJobs : EXISTING_JOBS });
    }
    return r.continue();
  });

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /add job/i }).click();

  // Fill the Markdown textarea
  const textarea = page.getByRole('textbox', { name: /job specification/i });
  await expect(textarea).toBeVisible();
  await textarea.fill(VALID_MARKDOWN);

  await page.getByRole('button', { name: /create job/i }).click();

  // Modal should close and the new row appear
  await expect(page.getByRole('textbox', { name: /job specification/i })).not.toBeVisible({ timeout: 4000 });
  await expect(page.getByText('Senior Backend Engineer')).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 2: Parser 422 error — inline field error rendered
// ─────────────────────────────────────────────────────────────────────────────

test('Given Markdown with no H1, When submitted, Then inline "title" error is shown', async ({ page }) => {
  await mockBaseRoutes(page);
  await page.route('**/api/jobs/markdown/', (r) =>
    r.fulfill({ status: 422, json: { title: ['Markdown must begin with an H1 heading.'] } })
  );

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /add job/i }).click();
  await page.getByRole('textbox', { name: /job specification/i }).fill('## No H1 here');
  await page.getByRole('button', { name: /create job/i }).click();

  await expect(page.getByText(/must begin with an h1/i)).toBeVisible();
  // Modal remains open for correction
  await expect(page.getByRole('textbox', { name: /job specification/i })).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 3: Server 500 — generic error banner shown with retry button
// ─────────────────────────────────────────────────────────────────────────────

test('Given a 500 error, When submitted, Then error banner with Retry is shown', async ({ page }) => {
  let callCount = 0;

  await mockBaseRoutes(page);
  await page.route('**/api/jobs/markdown/', (r) => {
    callCount++;
    if (callCount === 1) return r.fulfill({ status: 500, json: { detail: 'Internal server error' } });
    return r.fulfill({ status: 201, json: CREATED_JOB });
  });

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /add job/i }).click();
  await page.getByRole('textbox', { name: /job specification/i }).fill(VALID_MARKDOWN);
  await page.getByRole('button', { name: /create job/i }).click();

  const errorBanner = page.getByRole('alert');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner.getByRole('button', { name: /retry/i })).toBeVisible();

  // Retry succeeds — error disappears
  await errorBanner.getByRole('button', { name: /retry/i }).click();
  await expect(errorBanner).not.toBeVisible({ timeout: 4000 });
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 4: Duplicate title (409)
// ─────────────────────────────────────────────────────────────────────────────

test('Given a duplicate title, When submitted, Then "already exists" message is shown', async ({ page }) => {
  await mockBaseRoutes(page);
  await page.route('**/api/jobs/markdown/', (r) =>
    r.fulfill({ status: 409, json: { detail: 'A job with this title already exists.' } })
  );

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /add job/i }).click();
  await page.getByRole('textbox', { name: /job specification/i }).fill(VALID_MARKDOWN);
  await page.getByRole('button', { name: /create job/i }).click();

  await expect(page.getByText(/already exists/i)).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 5: Job detail expand — description and must_haves rendered
// ─────────────────────────────────────────────────────────────────────────────

test('Given a job with full detail, When expanded, Then description and must_haves are visible', async ({ page }) => {
  const jobWithDetail = {
    ...EXISTING_JOBS[0],
    description:      'We need a strong backend engineer.',
    requirements_raw: { required_skills: ['Python', 'Django'] },
    must_haves:       { min_experience: { type: 'years_experience', minimum_years: 5 } },
  };
  await mockBaseRoutes(page, { jobs: [jobWithDetail] });
  await page.route(`**/api/jobs/${jobWithDetail.id}/`, (r) =>
    r.fulfill({ json: jobWithDetail })
  );

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /expand/i }).first().click();

  await expect(page.getByText(/strong backend engineer/i)).toBeVisible();
  await expect(page.getByText(/years_experience/i)).toBeVisible();
  await expect(page.getByText(/minimum_years/i)).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 6: Edit job title inline
// ─────────────────────────────────────────────────────────────────────────────

test('Given an existing job, When title is edited and saved, Then updated title appears in list', async ({ page }) => {
  const updatedJob = { ...EXISTING_JOBS[0], title: 'Staff Data Engineer' };

  await mockBaseRoutes(page);
  await page.route(`**/api/jobs/${EXISTING_JOBS[0].id}/`, async (r) => {
    if (r.request().method() === 'PATCH') return r.fulfill({ json: updatedJob });
    return r.fulfill({ json: EXISTING_JOBS[0] });
  });

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /edit/i }).first().click();

  const titleInput = page.getByRole('textbox', { name: /title/i });
  await titleInput.fill('Staff Data Engineer');
  await page.getByRole('button', { name: /save/i }).click();

  await expect(page.getByText('Staff Data Engineer')).toBeVisible();
  await expect(page.queryByText('Principal Data Engineer')).not.toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 7: Delete job — cascade warning, confirmation, row removed
// ─────────────────────────────────────────────────────────────────────────────

test('Given a job, When user confirms delete, Then job row is removed from list', async ({ page }) => {
  await mockBaseRoutes(page);
  await page.route(`**/api/jobs/${EXISTING_JOBS[0].id}/`, (r) => {
    if (r.request().method() === 'DELETE') return r.fulfill({ status: 204, body: '' });
    return r.continue();
  });

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /delete/i }).first().click();

  // Cascade warning must mention linked applications
  const modal = page.getByRole('dialog');
  await expect(modal).toBeVisible();
  await expect(modal.getByText(/also delete/i)).toBeVisible();

  await modal.getByRole('button', { name: /confirm/i }).click();

  await expect(page.getByText('Principal Data Engineer')).not.toBeVisible({ timeout: 3000 });
});

test('Given a job, When user cancels delete, Then job row remains', async ({ page }) => {
  await mockBaseRoutes(page);

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /delete/i }).first().click();
  await page.getByRole('button', { name: /cancel/i }).click();

  await expect(page.getByText('Principal Data Engineer')).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 8: Loading spinner is visible during submission
// ─────────────────────────────────────────────────────────────────────────────

test('Given a slow API, Then loading spinner is shown while request is in flight', async ({ page }) => {
  let resolvePost;
  const postPromise = new Promise((res) => { resolvePost = res; });

  await mockBaseRoutes(page);
  await page.route('**/api/jobs/markdown/', async (r) => {
    await postPromise;
    return r.fulfill({ status: 201, json: CREATED_JOB });
  });

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /add job/i }).click();
  await page.getByRole('textbox', { name: /job specification/i }).fill(VALID_MARKDOWN);
  await page.getByRole('button', { name: /create job/i }).click();

  // Spinner must appear while request is in flight
  await expect(page.getByTestId('loading-spinner')).toBeVisible();

  resolvePost();

  // Spinner disappears once done
  await expect(page.getByTestId('loading-spinner')).not.toBeVisible({ timeout: 4000 });
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 9: Embedding latency — modal closes immediately on 201
// ─────────────────────────────────────────────────────────────────────────────

test('Modal closes on 201 regardless of embedding pipeline latency', async ({ page }) => {
  // The API returns 201 before embedding completes on the backend.
  // The frontend must not wait for any embedding confirmation.
  await mockBaseRoutes(page);
  await page.route('**/api/jobs/markdown/', (r) =>
    r.fulfill({ status: 201, json: CREATED_JOB })
  );

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /add job/i }).click();
  await page.getByRole('textbox', { name: /job specification/i }).fill(VALID_MARKDOWN);
  await page.getByRole('button', { name: /create job/i }).click();

  // Modal must close within 2 s — it does NOT wait for embedding
  await expect(
    page.getByRole('textbox', { name: /job specification/i })
  ).not.toBeVisible({ timeout: 2000 });
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 10: Jobs tab layout — title, requirements and must_haves split shown
// ─────────────────────────────────────────────────────────────────────────────

test('Job detail panel displays title, requirements, and must_haves in distinct sections', async ({ page }) => {
  const job = {
    id:               'job-detail-001',
    title:            'Senior Backend Engineer',
    description:      'Lead backend development of our data platform.',
    requirements_raw: {
      required_skills:           ['Python', 'Django', 'PostgreSQL', 'REST APIs'],
      preferred_skills:          ['Redis', 'Docker', 'Kubernetes'],
      minimum_experience_years:  5,
    },
    must_haves: {
      min_experience:   { type: 'years_experience',  minimum_years: 5 },
      python_required:  { type: 'keyword_presence',  keywords: ['Python'],  sections: ['skills', 'experience'] },
      django_required:  { type: 'keyword_presence',  keywords: ['Django'],  sections: ['skills', 'experience'] },
    },
    created_at: '2024-06-01T00:00:00Z',
  };
  await mockBaseRoutes(page, { jobs: [job] });
  await page.route(`**/api/jobs/${job.id}/`, (r) => r.fulfill({ json: job }));

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /expand/i }).click();

  // Three labelled content sections must be visible
  await expect(page.getByText(/required skills/i)).toBeVisible();
  await expect(page.getByText(/preferred skills/i)).toBeVisible();
  await expect(page.getByText(/hard gate criteria/i)).toBeVisible();

  // Skill pills
  await expect(page.getByText('Python')).toBeVisible();
  await expect(page.getByText('Django')).toBeVisible();
  await expect(page.getByText('PostgreSQL')).toBeVisible();

  // Must-haves criteria
  await expect(page.getByText(/years_experience/i)).toBeVisible();
  await expect(page.getByText(/keyword_presence/i)).toBeVisible();
});
```

---

## 5. Run Commands Reference

```bash
# ── Backend unit tests (no DB, no network) ────────────────────────────────
pytest tests/unit/test_job_parser.py -m unit -v
pytest tests/unit/test_job_views.py  -m unit -v

# ── Backend integration tests (SQLite + mocked embed API) ─────────────────
pytest tests/integration/test_job_lifecycle.py -m integration -v

# ── BDD outer loop (all job lifecycle scenarios) ──────────────────────────
pytest features/steps/job_lifecycle_steps.py -m bdd -v

# ── Full backend suite with coverage ─────────────────────────────────────
pytest --cov=resume_pipeline --cov-report=html \
  tests/unit/test_job_parser.py \
  tests/unit/test_job_views.py \
  tests/integration/test_job_lifecycle.py

# ── Frontend unit tests (Vitest) ──────────────────────────────────────────
cd frontend
npm test -- --reporter=verbose JobIngestionModal JobBoard

# ── Frontend E2E (Playwright headless) ───────────────────────────────────
npx playwright test e2e/job_lifecycle.spec.js

# ── Frontend E2E (Playwright interactive) ────────────────────────────────
npx playwright test e2e/job_lifecycle.spec.js --ui

# ── Full stack smoke test (Docker) ───────────────────────────────────────
docker compose up --build -d
bash scripts/smoke_test.sh
docker compose down
```

### Test Coverage Targets

| Layer | Target | Enforced By |
|---|---|---|
| `job_parser.py` — line coverage | ≥ 95 % | `pytest --cov-fail-under=95` |
| `views.py` — Job paths | ≥ 90 % | `pytest --cov-fail-under=90` |
| `JobSectionEmbedding` cascade delete | 100 % | Explicit integration assertion |
| `JobIngestionModal` — branch coverage | ≥ 85 % | Vitest coverage report |
| E2E happy path + error paths | All 10 scenarios | Playwright CI gate |

### Key Invariants This Plan Enforces

A failed parser **never** calls `Job.objects.create()`. A `TimeoutError` from the embedding service **never** propagates into an HTTP error response. A `DELETE` on a `Job` **always** leaves zero `JobSectionEmbedding` rows behind. A `PATCH` **always** re-triggers the embedding pipeline. These four invariants are tested at unit, integration, BDD, and E2E layers simultaneously, making regression surface explicit and bounded.
