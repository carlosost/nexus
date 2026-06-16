"""
Unit tests for ExperienceExtractor.

No DB, no network. Marked @pytest.mark.unit.
"""

import pytest
from datetime import datetime
from unittest.mock import patch

from resume_pipeline.ingestion.experience_extractor import ExperienceExtractor


@pytest.fixture
def extractor():
    return ExperienceExtractor()


# ── Strategy A — summary statement ───────────────────────────────────────────

@pytest.mark.unit
class TestSummaryStatement:

    @pytest.mark.parametrize("text,expected", [
        ("15+ years of experience in software engineering",        15.0),
        ("over 10 years of professional experience",              10.0),
        ("more than 8 years of experience",                        8.0),
        ("I have 20 years of experience leading teams",           20.0),
        ("5 years of experience",                                  5.0),
        ("over 12 years",                                         12.0),
        ("more than 3 years",                                      3.0),
    ])
    def test_extracts_years(self, extractor, text, expected):
        value, source = extractor.extract({"summary": text})
        assert value == expected
        assert source == "summary_statement"

    def test_no_match_returns_none(self, extractor):
        value, source = extractor.extract({"summary": "Experienced engineer with broad skills"})
        assert value is None

    def test_no_summary_key_returns_none(self, extractor):
        value, source = extractor.extract({})
        assert value is None

    def test_empty_summary_returns_none(self, extractor):
        value, source = extractor.extract({"summary": ""})
        assert value is None


# ── Strategy B — date range calculation ──────────────────────────────────────

@pytest.mark.unit
class TestDateCalculation:

    def test_full_month_year_range(self, extractor):
        text = "Jun 2022 – Present\nSenior Engineer at Acme"
        # Pin "today" so the test is deterministic
        today = datetime(2026, 6, 1)
        with patch("resume_pipeline.ingestion.experience_extractor.datetime") as mock_dt:
            mock_dt.today.return_value = today
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            value, source = extractor.extract({"experience": text})
        assert source == "date_calculation"
        assert value is not None
        assert value > 3.0  # ~4 years

    def test_year_only_range(self, extractor):
        text = "2004 – 2009"
        value, source = extractor.extract({"experience": text})
        assert source == "date_calculation"
        assert value == pytest.approx(5.0, abs=0.2)

    def test_present_resolved_to_today(self, extractor):
        today = datetime(2026, 1, 1)
        with patch("resume_pipeline.ingestion.experience_extractor.datetime") as mock_dt:
            mock_dt.today.return_value = today
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            value, source = extractor.extract({"experience": "Jan 2024 – Present"})
        assert source == "date_calculation"
        assert value == pytest.approx(2.0, abs=0.2)

    def test_overlapping_roles_counted_once(self, extractor):
        # Two roles that overlap by 1 year: 2018–2021 and 2020–2022
        text = "Jan 2018 – Dec 2021\nJan 2020 – Dec 2022"
        value, source = extractor.extract({"experience": text})
        # Merged to Jan 2018 – Dec 2022 = ~5 years, not 3+3=6
        assert source == "date_calculation"
        assert value == pytest.approx(5.0, abs=0.2)

    def test_no_date_ranges_returns_none(self, extractor):
        value, source = extractor.extract({"experience": "Led backend development at Acme."})
        assert value is None
        assert source is None

    def test_no_experience_key_returns_none(self, extractor):
        value, source = extractor.extract({})
        assert value is None
        assert source is None

    def test_empty_experience_returns_none(self, extractor):
        value, source = extractor.extract({"experience": ""})
        assert value is None

    def test_multiple_non_overlapping_roles(self, extractor):
        text = (
            "Jan 2004 – Dec 2009\n"
            "Jan 2010 – Dec 2014\n"
            "Jan 2015 – Dec 2019\n"
        )
        value, source = extractor.extract({"experience": text})
        assert source == "date_calculation"
        # ~16 years total (3 contiguous 5-year spans)
        assert value == pytest.approx(16.0, abs=0.5)

    def test_range_separator_variants(self, extractor):
        for sep in [" – ", " — ", " - ", " to "]:
            text = f"Jan 2020{sep}Dec 2021"
            value, _ = extractor.extract({"experience": text})
            assert value is not None, f"Failed to parse separator: {sep!r}"

    def test_abbreviated_months(self, extractor):
        text = "Apr 2021 – Jun 2022"
        value, source = extractor.extract({"experience": text})
        assert source == "date_calculation"
        assert value == pytest.approx(1.2, abs=0.1)


# ── Priority / integration ────────────────────────────────────────────────────

@pytest.mark.unit
class TestPriority:

    def test_summary_takes_priority_over_dates(self, extractor):
        sections = {
            "summary":    "15+ years of experience",
            "experience": "Jan 2000 – Dec 2023",
        }
        value, source = extractor.extract(sections)
        assert source == "summary_statement"
        assert value == 15.0

    def test_falls_back_to_dates_when_no_summary_match(self, extractor):
        sections = {
            "summary":    "Experienced software engineer",
            "experience": "Jan 2018 – Dec 2022",
        }
        value, source = extractor.extract(sections)
        assert source == "date_calculation"
        assert value == pytest.approx(5.0, abs=0.2)

    def test_returns_none_tuple_when_nothing_found(self, extractor):
        value, source = extractor.extract({"summary": "", "experience": ""})
        assert value is None
        assert source is None

    def test_sections_dict_updated_with_value(self, extractor):
        """Caller should store value into sections when not None."""
        sections = {"summary": "10+ years of experience"}
        value, source = extractor.extract(sections)
        assert value == 10.0
        sections["total_experience_years"] = value
        assert sections["total_experience_years"] == 10.0
