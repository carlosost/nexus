"""
Step definitions for features/job_lifecycle.feature.

Strategy: all ORM calls are mocked via unittest.mock so no real PostgreSQL
is required. Views are exercised through DRF's APIRequestFactory, mirroring
the pattern used in dashboard_stats_steps.py and human_review_steps.py.

Context keys:
  ctx["response"]      — DRF Response from the last view call
  ctx["raw_markdown"]  — Markdown string to POST
  ctx["mock_job"]      — MagicMock representing the persisted Job object
  ctx["mock_jobs"]     — list of MagicMock job objects for list scenarios
  ctx["job_store"]     — dict[title → MagicMock] simulating DB uniqueness
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from rest_framework.test import APIRequestFactory

pytestmark = pytest.mark.bdd

scenarios("job_lifecycle.feature")


# ---------------------------------------------------------------------------
# Shared state fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx() -> dict:
    return {
        "response":      None,
        "raw_markdown":  None,
        "mock_job":      None,
        "mock_jobs":     [],
        "job_store":     {},   # title → mock_job (simulates DB uniqueness)
        "request_body":  None,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_MARKDOWN_TEMPLATE = """\
# {title}

## Description
{description}

## Requirements
### Required Skills
{skills}
### Minimum Experience
3 years

## Must Haves
### min_experience
type: years_experience
minimum_years: 3
"""


def _make_mock_job(title="Senior Backend Engineer", description="A great job.",
                   requirements_raw=None, must_haves=None) -> MagicMock:
    """Return a MagicMock that walks like a Job model instance."""
    job = MagicMock()
    job.id          = uuid.uuid4()
    job.title       = title
    job.description = description
    job.requirements_raw = requirements_raw or {"required_skills": ["Python"]}
    job.must_haves       = must_haves or {}
    job.created_at  = "2026-01-01T00:00:00Z"
    job.updated_at  = "2026-01-01T00:00:00Z"
    return job


def _post_markdown(ctx: dict, raw_markdown: str) -> None:
    """POST raw_markdown to JobListCreateView with all ORM/parser mocked."""
    from django.db import IntegrityError

    job_store = ctx["job_store"]

    def _fake_create(**kwargs):
        title = kwargs.get("title", "")
        if title in job_store:
            raise IntegrityError("duplicate key")
        mock_job = _make_mock_job(
            title=kwargs.get("title", ""),
            description=kwargs.get("description", ""),
            requirements_raw=kwargs.get("requirements_raw", {}),
            must_haves=kwargs.get("must_haves", {}),
        )
        job_store[title] = mock_job
        ctx["mock_job"]  = mock_job
        return mock_job

    with (
        patch("resume_pipeline.views.Job") as MockJob,
        patch("resume_pipeline.views.embed_job_sections"),
    ):
        # Wire Job.objects.create() through the fake that checks uniqueness
        MockJob.objects.create.side_effect = _fake_create

        factory = APIRequestFactory()
        request = factory.post(
            "/api/jobs/",
            data={"raw_markdown": raw_markdown},
            format="json",
        )

        from resume_pipeline.views import JobListCreateView
        view = JobListCreateView.as_view()
        ctx["response"] = view(request)


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

@given("the Job ingestion parser is initialized")
def parser_initialized(ctx: dict) -> None:
    """No-op — the parser is a pure function, no init required."""


@given(parsers.parse('the embedding backend is set to "{backend}"'))
def embedding_backend_set(ctx: dict, backend: str, monkeypatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", backend)


@given("the database is empty of Job records")
def db_empty(ctx: dict) -> None:
    ctx["job_store"] = {}
    ctx["mock_jobs"] = []
    ctx["mock_job"]  = None


# ---------------------------------------------------------------------------
# Given — data setup
# ---------------------------------------------------------------------------

@given("the following raw Markdown job specification:")
def raw_markdown_from_docstring(ctx: dict, docstring: str) -> None:
    ctx["raw_markdown"] = docstring


@given(parsers.parse('a valid Markdown job spec with title "{title}"'))
def valid_markdown_with_title(ctx: dict, title: str) -> None:
    ctx["raw_markdown"] = VALID_MARKDOWN_TEMPLATE.format(
        title=title,
        description="A standard job description for testing.",
        skills="- Python\n- Django",
    )


@given(parsers.parse(
    'a valid Markdown job spec with a description section containing "{text}"'
))
def valid_markdown_with_description(ctx: dict, text: str) -> None:
    ctx["raw_markdown"] = VALID_MARKDOWN_TEMPLATE.format(
        title="Test Job",
        description=text,
        skills="- Python",
    )


@given(parsers.parse("a valid Markdown job spec with required skills: {skills}"))
def valid_markdown_with_skills(ctx: dict, skills: str) -> None:
    skill_list = [s.strip() for s in skills.split(",")]
    bullets = "\n".join(f"- {s}" for s in skill_list)
    ctx["raw_markdown"] = VALID_MARKDOWN_TEMPLATE.format(
        title="Skill Test Job",
        description="A job description.",
        skills=bullets,
    )


@given(parsers.parse('a valid Markdown job spec with "Minimum Experience" of {years:d} years'))
def valid_markdown_with_experience(ctx: dict, years: int) -> None:
    md = f"""\
# Experience Test Job

## Description
Requires {years} years of experience.

## Requirements
### Required Skills
- Python
### Minimum Experience
{years} years

## Must Haves
### min_experience
type: years_experience
minimum_years: {years}
"""
    ctx["raw_markdown"] = md


@given(parsers.parse(
    'a valid Markdown job spec with must_have criterion "{key}" of type "years_experience" '
    'with minimum_years {years:d}'
))
def valid_markdown_with_must_have_years(ctx: dict, key: str, years: int) -> None:
    md = f"""\
# Must Have Test Job

## Description
Test job with must_have criterion.

## Requirements
### Required Skills
- Python

## Must Haves
### {key}
type: years_experience
minimum_years: {years}
"""
    ctx["raw_markdown"] = md


@given(parsers.parse(
    'a valid Markdown job spec with must_have criterion "{key}" requiring '
    'keyword "{keyword}" in sections "{sections}"'
))
def valid_markdown_with_must_have_keyword(
    ctx: dict, key: str, keyword: str, sections: str
) -> None:
    md = f"""\
# Keyword Test Job

## Description
Test job with keyword_presence must_have.

## Requirements
### Required Skills
- Python

## Must Haves
### {key}
type: keyword_presence
keywords: {keyword}
sections: {sections}
"""
    ctx["raw_markdown"] = md


@given("an empty request body")
def empty_request_body(ctx: dict) -> None:
    ctx["raw_markdown"] = ""


@given("a Markdown body with no H1 heading line")
def markdown_no_h1(ctx: dict) -> None:
    ctx["raw_markdown"] = "## Description\nSome text without a title.\n"


@given("a Markdown body containing only a lone title heading")
def markdown_lone_title(ctx: dict) -> None:
    ctx["raw_markdown"] = "# Lone Title\n"


@given("a Markdown job spec where the Must Haves section has invalid syntax")
def markdown_invalid_must_haves(ctx: dict) -> None:
    ctx["raw_markdown"] = """\
# Test Job

## Description
Valid description here.

## Requirements
### Required Skills
- Python

## Must Haves
--- invalid yaml line
"""


@given(parsers.parse('a Job named "{title}" already exists in the mock store'))
def job_already_exists(ctx: dict, title: str) -> None:
    existing = _make_mock_job(title=title, description="Existing job.")
    ctx["job_store"][title] = existing


@given(parsers.parse("{count:d} Jobs exist in the mock store"))
def n_jobs_in_mock_store(ctx: dict, count: int) -> None:
    for i in range(count):
        j = _make_mock_job(title=f"Job {i + 1}", description=f"Description {i + 1}.")
        ctx["mock_jobs"].append(j)


@given(parsers.parse(
    'a Job exists in the mock store with title "{title}" and description "{description}"'
))
def job_exists_in_mock_store(ctx: dict, title: str, description: str) -> None:
    mock_job = _make_mock_job(title=title, description=description)
    ctx["job_store"][title] = mock_job
    ctx["mock_job"]         = mock_job


# ---------------------------------------------------------------------------
# When — trigger HTTP actions
# ---------------------------------------------------------------------------

@when(parsers.parse('I POST the Markdown to "{path}"'))
def post_markdown_to_path(ctx: dict, path: str) -> None:
    _post_markdown(ctx, ctx["raw_markdown"] or "")


@when(parsers.parse('I GET "{path}"'))
def get_path(ctx: dict, path: str) -> None:
    """Drive list or detail GET endpoints with mocked ORM."""
    from resume_pipeline.views import JobListCreateView, JobDetailView
    import uuid as uuid_mod

    factory = APIRequestFactory()

    # Detect if the path ends with a UUID segment
    parts = [p for p in path.strip("/").split("/") if p]
    # path examples: /api/jobs/  →  ["api", "jobs"]
    #                /api/jobs/00000000-.../  →  ["api", "jobs", "00000000-..."]

    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "jobs":
        # Detail view
        pk_str = parts[2]
        try:
            pk = uuid_mod.UUID(pk_str)
        except ValueError:
            pk = uuid_mod.UUID("00000000-0000-0000-0000-000000000000")

        from django.http import Http404
        with patch("resume_pipeline.views.get_object_or_404", side_effect=Http404):
            request = factory.get(path)
            view = JobDetailView.as_view()
            ctx["response"] = view(request, pk=str(pk))
    else:
        # List view
        mock_jobs = ctx.get("mock_jobs", [])
        with patch("resume_pipeline.views.Job") as MockJob:
            MockJob.objects.order_by.return_value = mock_jobs
            request = factory.get(path)
            view = JobListCreateView.as_view()
            ctx["response"] = view(request)


@when("I DELETE the Job")
def delete_job(ctx: dict) -> None:
    """DELETE the mock_job in ctx."""
    from resume_pipeline.views import JobDetailView

    mock_job = ctx.get("mock_job")
    if not mock_job:
        pytest.skip("No mock_job in context")

    with patch("resume_pipeline.views.get_object_or_404", return_value=mock_job):
        factory = APIRequestFactory()
        request = factory.delete(f"/api/jobs/{mock_job.id}/")
        view = JobDetailView.as_view()
        ctx["response"] = view(request, pk=str(mock_job.id))


# ---------------------------------------------------------------------------
# Then — response status
# ---------------------------------------------------------------------------

@then(parsers.parse("the response status is {code:d}"))
def assert_status(ctx: dict, code: int) -> None:
    assert ctx["response"].status_code == code, (
        f"Expected {code}, got {ctx['response'].status_code}. "
        f"Body: {getattr(ctx['response'], 'data', '(no data)')}"
    )


# ---------------------------------------------------------------------------
# Then — response body field checks
# ---------------------------------------------------------------------------

@then(parsers.parse('the response body contains field "{field}"'))
def assert_response_has_field(ctx: dict, field: str) -> None:
    data = ctx["response"].data
    assert field in data, f"Field '{field}' missing from response: {list(data.keys())}"


@then(parsers.parse('the response body contains field "{field}" with value "{value}"'))
def assert_response_field_value(ctx: dict, field: str, value: str) -> None:
    data = ctx["response"].data
    assert field in data, f"Field '{field}' not in response"
    assert str(data[field]) == value, (
        f"Field '{field}': expected '{value}', got '{data[field]}'"
    )


@then(parsers.parse('the response body contains key "{key}"'))
def assert_response_has_key(ctx: dict, key: str) -> None:
    data = ctx["response"].data
    assert key in data, f"Key '{key}' missing from response: {list(data.keys())}"


@then(parsers.parse("the response body is a list of {count:d} items"))
def assert_response_list_length(ctx: dict, count: int) -> None:
    data = ctx["response"].data
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    assert len(data) == count, f"Expected {count} items, got {len(data)}"


# ---------------------------------------------------------------------------
# Then — persisted Job field assertions
# ---------------------------------------------------------------------------

@then(parsers.parse('the persisted Job title is "{expected}"'))
def assert_persisted_title(ctx: dict, expected: str) -> None:
    job = ctx.get("mock_job")
    assert job is not None, "No mock_job in context"
    assert job.title == expected, f"Title: expected '{expected}', got '{job.title}'"


@then(parsers.parse('the persisted Job description contains "{text}"'))
def assert_persisted_description_contains(ctx: dict, text: str) -> None:
    job = ctx.get("mock_job")
    assert job is not None, "No mock_job in context"
    assert text in job.description, (
        f"Description does not contain '{text}': {job.description!r}"
    )


@then(parsers.parse('the persisted Job has required_skills containing "{skill}"'))
def assert_persisted_required_skill(ctx: dict, skill: str) -> None:
    job = ctx.get("mock_job")
    assert job is not None, "No mock_job in context"
    skills = job.requirements_raw.get("required_skills", [])
    assert skill in skills, f"'{skill}' not in required_skills: {skills}"


@then(parsers.parse("the persisted Job minimum_experience_years equals {years:d}"))
def assert_persisted_min_exp_years(ctx: dict, years: int) -> None:
    job = ctx.get("mock_job")
    assert job is not None, "No mock_job in context"
    actual = job.requirements_raw.get("minimum_experience_years")
    assert actual == years, f"minimum_experience_years: expected {years}, got {actual}"


@then(parsers.parse('the persisted Job must_haves "{key}" type equals "{expected}"'))
def assert_must_haves_type(ctx: dict, key: str, expected: str) -> None:
    job = ctx.get("mock_job")
    assert job is not None, "No mock_job in context"
    assert key in job.must_haves, f"'{key}' not in must_haves: {list(job.must_haves.keys())}"
    actual = job.must_haves[key].get("type")
    assert actual == expected, f"must_haves['{key}']['type']: expected '{expected}', got '{actual}'"


@then(parsers.parse('the persisted Job must_haves "{key}" minimum_years equals {years:d}'))
def assert_must_haves_min_years(ctx: dict, key: str, years: int) -> None:
    job = ctx.get("mock_job")
    assert job is not None, "No mock_job in context"
    actual = job.must_haves[key].get("minimum_years")
    assert actual == years, f"must_haves['{key}']['minimum_years']: expected {years}, got {actual}"


@then(parsers.parse('the persisted Job must_haves "{key}" keywords contains "{kw}"'))
def assert_must_haves_keywords(ctx: dict, key: str, kw: str) -> None:
    job = ctx.get("mock_job")
    assert job is not None, "No mock_job in context"
    keywords = job.must_haves[key].get("keywords", [])
    assert kw in keywords, f"'{kw}' not in must_haves['{key}']['keywords']: {keywords}"


@then(parsers.parse('the persisted Job must_haves "{key}" sections contains "{section}"'))
def assert_must_haves_sections(ctx: dict, key: str, section: str) -> None:
    job = ctx.get("mock_job")
    assert job is not None, "No mock_job in context"
    sections = job.must_haves[key].get("sections", [])
    assert section in sections, (
        f"'{section}' not in must_haves['{key}']['sections']: {sections}"
    )


# ---------------------------------------------------------------------------
# Then — database-state assertions (against mock store)
# ---------------------------------------------------------------------------

@then("no Job records exist in the database")
def assert_no_jobs(ctx: dict) -> None:
    assert len(ctx["job_store"]) == 0, (
        f"Expected empty job store, found: {list(ctx['job_store'].keys())}"
    )


@then(parsers.parse("only {count:d} Job record with title \"{title}\" exists"))
def assert_single_job_title(ctx: dict, count: int, title: str) -> None:
    matching = [k for k in ctx["job_store"] if k == title]
    assert len(matching) == count, (
        f"Expected {count} job(s) with title '{title}', found {len(matching)}"
    )


