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
        # A line starting with "---" (no ":") hits the else-branch guard in the parser
        md = VALID_MARKDOWN + "\n--- unexpected\n"
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
