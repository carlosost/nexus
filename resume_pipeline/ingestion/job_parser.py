"""
Job Markdown ingestion parser.

Exports:
    JobParseError   — raised on unrecoverable parse failure; carries a field key
    JobSpec         — dataclass representing parsed job fields
    parse_job_markdown(raw: str) -> JobSpec
                    — pure function: no I/O, no Django ORM calls

Markdown structure expected (mirrors JOB_SPEC from _seed_data.py):

    # <Job Title>

    ## Description
    <free text>

    ## Requirements
    ### Required Skills
    - Skill1
    - Skill2
    ### Preferred Skills
    - Skill3
    ### Minimum Experience
    N years

    ## Must Haves
    ### <criterion_key>
    type: <years_experience|keyword_presence>
    minimum_years: N          # for years_experience
    keywords: Keyword1, ...   # for keyword_presence
    sections: section1, ...   # for keyword_presence

Heading matching is case-insensitive. Bullet markers may be - or *.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class JobParseError(Exception):
    """
    Raised when the Markdown body cannot be mapped to a valid Job.

    Attributes:
        field_key (str): the Job field that failed (e.g. "title", "description",
                         "must_haves") — used by the view to build field-level
                         error responses.
        detail (str):    human-readable explanation.
    """

    def __init__(self, field_key: str, detail: str) -> None:
        self.field_key = field_key
        self.detail    = detail
        super().__init__(f"{field_key}: {detail}")


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

@dataclass
class JobSpec:
    """Parsed representation of a Markdown job specification."""

    title:            str
    description:      str
    requirements_raw: dict = field(default_factory=dict)
    must_haves:       dict = field(default_factory=dict)

    def to_model_kwargs(self) -> dict:
        """Return a dict suitable for Job.objects.create(**kwargs)."""
        return {
            "title":            self.title,
            "description":      self.description,
            "requirements_raw": self.requirements_raw,
            "must_haves":       self.must_haves,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_job_markdown(raw: str) -> JobSpec:
    """
    Parse a raw Markdown string into a JobSpec.

    Raises:
        JobParseError: if any required field is missing or a block is malformed.

    This function is intentionally dependency-free (no Django, no DB, no network).
    """
    if not raw or not raw.strip():
        raise JobParseError("raw_markdown", "empty")

    lines = raw.splitlines()

    title            = _extract_title(lines)
    description      = _extract_section(lines, "description")
    requirements_raw = _extract_requirements(lines)
    must_haves       = _extract_must_haves(lines)

    return JobSpec(
        title=title,
        description=description,
        requirements_raw=requirements_raw,
        must_haves=must_haves,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_title(lines: list[str]) -> str:
    """Return text of the first H1 heading, stripped of whitespace."""
    for line in lines:
        if line.startswith("# ") or line == "#":
            title = line.lstrip("#").strip()
            if title:
                return title
    raise JobParseError("title", "Markdown must begin with an H1 heading (# Title)")


def _extract_section(lines: list[str], section_name: str) -> str:
    """
    Extract the text body of a top-level ## <section_name> section.
    Matching is case-insensitive. Returns the first non-empty block found.

    Raises:
        JobParseError: if the section is absent or its body is empty.
    """
    body_lines: list[str] = []
    inside = False

    for line in lines:
        if _is_h2(line, section_name):
            inside = True
            body_lines = []
            continue
        if inside:
            # Stop at the next H2 or H1
            if line.startswith("## ") or line.startswith("# "):
                break
            body_lines.append(line)

    if not inside:
        raise JobParseError(
            section_name,
            f"Markdown is missing a '## {section_name.capitalize()}' section",
        )

    body = "\n".join(body_lines).strip()
    if not body:
        raise JobParseError(
            section_name,
            f"'## {section_name.capitalize()}' section is present but empty",
        )
    return body


def _extract_requirements(lines: list[str]) -> dict:
    """
    Parse the ## Requirements section into:
      {
        "required_skills":          [...],
        "preferred_skills":         [...],
        "minimum_experience_years": int,
      }
    Missing subsections are silently omitted (not a hard error).
    """
    req_lines = _section_lines(lines, "requirements")
    if not req_lines:
        # Requirements section is optional — return empty dict
        return {}

    required_skills:    list[str] = []
    preferred_skills:   list[str] = []
    min_exp_years:      int | None = None

    current_sub: str | None = None

    for line in req_lines:
        stripped = line.strip()

        if _is_h3(line, "required skills"):
            current_sub = "required"
            continue
        if _is_h3(line, "preferred skills"):
            current_sub = "preferred"
            continue
        if _is_h3(line, "minimum experience"):
            current_sub = "min_exp"
            continue
        # Any other H3 resets the context
        if line.startswith("### "):
            current_sub = None
            continue

        if current_sub == "required" and _is_bullet(stripped):
            required_skills.append(stripped.lstrip("-* ").strip())
        elif current_sub == "preferred" and _is_bullet(stripped):
            preferred_skills.append(stripped.lstrip("-* ").strip())
        elif current_sub == "min_exp" and stripped:
            years = _parse_years(stripped)
            if years is not None:
                min_exp_years = years

    result: dict = {}
    if required_skills:
        result["required_skills"] = required_skills
    if preferred_skills:
        result["preferred_skills"] = preferred_skills
    if min_exp_years is not None:
        result["minimum_experience_years"] = min_exp_years

    return result


def _extract_must_haves(lines: list[str]) -> dict:
    """
    Parse the ## Must Haves section into a dict matching the JOB_SPEC schema:
      {
        "<criterion_key>": {
          "type": "years_experience" | "keyword_presence",
          "minimum_years": int,          # years_experience only
          "keywords": [...],             # keyword_presence only
          "sections": [...],             # keyword_presence only
        },
        ...
      }

    Raises:
        JobParseError("must_haves", ...) if the block contains malformed YAML-like lines.
    """
    mh_lines = _section_lines(lines, "must haves")
    if not mh_lines:
        return {}

    must_haves: dict = {}
    current_key: str | None = None
    current_criterion: dict = {}

    try:
        for line in mh_lines:
            stripped = line.strip()
            if not stripped:
                continue

            if line.startswith("### "):
                # Save previous criterion
                if current_key and current_criterion:
                    must_haves[current_key] = current_criterion
                current_key       = line.lstrip("#").strip().lower().replace(" ", "_")
                current_criterion = {}
                continue

            if ":" in stripped:
                raw_key, _, raw_val = stripped.partition(":")
                k = raw_key.strip().lower()
                v = raw_val.strip()

                if k == "type":
                    current_criterion["type"] = v
                elif k == "minimum_years":
                    current_criterion["minimum_years"] = int(v)
                elif k == "keywords":
                    current_criterion["keywords"] = [kw.strip() for kw in v.split(",") if kw.strip()]
                elif k == "sections":
                    current_criterion["sections"] = [s.strip() for s in v.split(",") if s.strip()]
            else:
                # Unexpected non-key-value content — only an issue if it looks like
                # broken YAML (starts with special chars). Plain prose is tolerated.
                if stripped.startswith((":", "---", "...")):
                    raise JobParseError("must_haves", f"Malformed line in Must Haves block: {stripped!r}")

        # Save the last criterion
        if current_key and current_criterion:
            must_haves[current_key] = current_criterion

    except ValueError as exc:
        raise JobParseError("must_haves", f"Failed to parse Must Haves block: {exc}") from exc

    return must_haves


# ---------------------------------------------------------------------------
# Line-level utilities
# ---------------------------------------------------------------------------

def _is_h2(line: str, name: str) -> bool:
    """True if line is '## <name>' (case-insensitive, stripped)."""
    if not line.startswith("## "):
        return False
    return line[3:].strip().lower() == name.lower()


def _is_h3(line: str, name: str) -> bool:
    """True if line is '### <name>' (case-insensitive, stripped)."""
    if not line.startswith("### "):
        return False
    return line[4:].strip().lower() == name.lower()


def _is_bullet(text: str) -> bool:
    """True if the stripped line starts with - or *."""
    return bool(text) and text[0] in ("-", "*")


def _parse_years(text: str) -> int | None:
    """Extract the first integer from a string like '5 years' or '5 years minimum'."""
    m = re.search(r"\b(\d+)\b", text)
    return int(m.group(1)) if m else None


def _section_lines(lines: list[str], section_name: str) -> list[str]:
    """
    Return the body lines of the first ## <section_name> section found
    (case-insensitive match on section_name). Returns empty list if absent.
    Stops at the next ## or # heading.
    """
    body: list[str] = []
    inside = False

    for line in lines:
        if _is_h2(line, section_name):
            inside = True
            body = []
            continue
        if inside:
            if line.startswith("## ") or line.startswith("# "):
                break
            body.append(line)

    return body if inside else []
