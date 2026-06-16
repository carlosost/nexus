"""
ExperienceExtractor — post-processing step for ResumeParser.

Attempts two strategies in priority order:
  1. Explicit statement in the summary section (e.g. "15+ years of experience")
  2. Date-range calculation from the experience section (merge-intervals)

Returns (value, source) where source is "summary_statement", "date_calculation",
or None when neither strategy yields a result.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional


# Month abbreviations → 1-based integer
_MONTH_MAP: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    # Long forms
    "january": 1, "february": 2, "march": 3, "april": 4,
    "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12,
}

# Patterns for explicit self-reported experience in a summary section
_SUMMARY_PATTERNS: list[re.Pattern] = [
    re.compile(r'(\d+)\+?\s*years?\s+of\s+(?:professional\s+)?experience', re.IGNORECASE),
    re.compile(r'over\s+(\d+)\s*\+?\s*years?\s+of\s+(?:professional\s+)?experience', re.IGNORECASE),
    re.compile(r'more\s+than\s+(\d+)\s*\+?\s*years?\s+of\s+(?:professional\s+)?experience', re.IGNORECASE),
    re.compile(r'over\s+(\d+)\s*\+?\s*years?', re.IGNORECASE),
    re.compile(r'more\s+than\s+(\d+)\s*\+?\s*years?', re.IGNORECASE),
]

# Matches a single date endpoint: "Jun 2022", "June 2022", "2022", "Present", "Current", "Now"
_DATE_TOKEN = r'(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+)?\d{4}|present|current|now'

# Range separator: en-dash, em-dash, hyphen, or "to"
_SEP = r'\s*(?:–|—|-|to)\s*'

_DATE_RANGE_RE = re.compile(
    rf'({_DATE_TOKEN}){_SEP}({_DATE_TOKEN})',
    re.IGNORECASE,
)


def _parse_date(token: str) -> Optional[datetime]:
    token = token.strip().lower()
    if token in ("present", "current", "now"):
        return datetime.today()

    # Try "Mon YYYY" or "Month YYYY"
    parts = token.split()
    if len(parts) == 2:
        month_str, year_str = parts
        month = _MONTH_MAP.get(month_str)
        if month and year_str.isdigit():
            return datetime(int(year_str), month, 1)

    # Year-only: default to January
    if token.isdigit() and len(token) == 4:
        return datetime(int(token), 1, 1)

    return None


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> float:
    """Return total years of non-overlapping duration."""
    if not intervals:
        return 0.0
    intervals.sort(key=lambda x: x[0])
    merged: list[tuple[datetime, datetime]] = [intervals[0]]
    for start, end in intervals[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    total_days = sum((end - start).days for start, end in merged)
    return round(total_days / 365.25, 1)


class ExperienceExtractor:
    """
    Extracts total_experience_years from parsed resume sections.

    Usage::

        extractor = ExperienceExtractor()
        value, source = extractor.extract(sections)
        if value is not None:
            sections["total_experience_years"] = value
    """

    def extract(self, sections: dict) -> tuple[Optional[float], Optional[str]]:
        """
        Returns (value, source).  source is one of:
          "summary_statement" — extracted from explicit phrase in summary
          "date_calculation"  — computed from date ranges in experience section
          None                — not found; value is also None
        """
        value = self._from_summary(sections.get("summary", ""))
        if value is not None:
            return value, "summary_statement"

        value = self._from_dates(sections.get("experience", ""))
        if value is not None:
            return value, "date_calculation"

        return None, None

    # ------------------------------------------------------------------
    # Strategy A — explicit summary statement
    # ------------------------------------------------------------------

    def _from_summary(self, text: str) -> Optional[float]:
        if not text:
            return None
        for pattern in _SUMMARY_PATTERNS:
            m = pattern.search(text)
            if m:
                return float(m.group(1))
        return None

    # ------------------------------------------------------------------
    # Strategy B — date range calculation
    # ------------------------------------------------------------------

    def _from_dates(self, text: str) -> Optional[float]:
        if not text:
            return None
        intervals: list[tuple[datetime, datetime]] = []
        for m in _DATE_RANGE_RE.finditer(text):
            start = _parse_date(m.group(1))
            end   = _parse_date(m.group(2))
            if start is not None and end is not None and end >= start:
                intervals.append((start, end))
        if not intervals:
            return None
        total = _merge_intervals(intervals)
        return total if total > 0 else None
