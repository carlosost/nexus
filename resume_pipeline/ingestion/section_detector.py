"""
M0.5 — Resume section detector.

Primary path: spaCy PhraseMatcher over a canonical alias list.
Fallback (unit tests / no model): pure regex line matching.

Unit tests mock ``_run_nlp`` to call ``_regex_fallback`` directly, so no
spaCy model download is required to run the test suite.
Integration tests (marked ``@pytest.mark.integration``) exercise real spaCy.
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Canonical sections and their known header aliases
# ---------------------------------------------------------------------------

SECTION_ALIASES: dict[str, list[str]] = {
    "experience": [
        "experience",
        "work experience",
        "work history",
        "employment history",
        "professional experience",
        "career history",
        "relevant experience",
    ],
    "skills": [
        "skills",
        "technical skills",
        "core competencies",
        "technologies",
        "key skills",
        "areas of expertise",
        "technical proficiencies",
    ],
    "education": [
        "education",
        "academic background",
        "academic history",
        "educational background",
        "qualifications",
        "academic qualifications",
    ],
    "certifications": [
        "certifications",
        "certificates",
        "professional certifications",
        "licenses",
        "accreditations",
        "professional development",
    ],
    "projects": [
        "projects",
        "personal projects",
        "open source",
        "portfolio",
        "side projects",
        "notable projects",
    ],
    "summary": [
        "summary",
        "professional summary",
        "profile",
        "about me",
        "career objective",
        "objective",
        "executive summary",
    ],
}

# Reverse map: lowercase alias → canonical key
_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias.lower(): canonical
    for canonical, aliases in SECTION_ALIASES.items()
    for alias in aliases
}

# Regex: any canonical alias on its own trimmed line (case-insensitive)
_HEADER_RE = re.compile(
    r"^(?:" + "|".join(re.escape(a) for a in _ALIAS_TO_CANONICAL) + r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# SectionDetector
# ---------------------------------------------------------------------------

class SectionDetector:
    """
    Detect resume section boundaries from raw extracted text.

    Public API::

        detector = SectionDetector()
        sections = detector.detect(text)
        # → {"experience": "...", "skills": "...", ...}

    In unit tests, patch ``_run_nlp`` to delegate to ``_regex_fallback``::

        with patch.object(detector, "_run_nlp",
                          side_effect=lambda t: detector._regex_fallback(t)):
            result = detector.detect(text)
    """

    def __init__(self) -> None:
        self._nlp = self._load_nlp()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def detect(self, text: str) -> dict[str, str]:
        """
        Return a dict mapping canonical section keys to their body text.
        Returns ``{}`` on empty input — never raises.
        """
        if not text:
            return {}
        result = self._run_nlp(text)
        if not result:
            result = self._regex_fallback(text)
        return result

    # ------------------------------------------------------------------
    # NLP path (spaCy)
    # ------------------------------------------------------------------

    def _load_nlp(self):
        """Load en_core_web_sm; return None if spaCy or model is unavailable."""
        try:
            import spacy
            return spacy.load("en_core_web_sm")
        except Exception:
            return None

    def _run_nlp(self, text: str) -> dict[str, str]:
        """
        Use spaCy PhraseMatcher for header detection.
        Returns ``{}`` if the model is not loaded (triggers regex fallback in detect()).
        """
        if self._nlp is None:
            return {}

        try:
            from spacy.matcher import PhraseMatcher

            matcher = PhraseMatcher(self._nlp.vocab, attr="LOWER")
            for alias, canonical in _ALIAS_TO_CANONICAL.items():
                matcher.add(canonical, [self._nlp.make_doc(alias)])

            doc = self._nlp(text)
            matches = matcher(doc)
            if not matches:
                return {}

            # Collect (char_start, canonical_key, token_end) for each match
            hit_positions: list[tuple[int, str, int]] = []
            for match_id, start, end in matches:
                canonical = self._nlp.vocab.strings[match_id]
                char_start = doc[start].idx
                hit_positions.append((char_start, canonical, end))

            hit_positions.sort(key=lambda x: x[0])

            sections: dict[str, str] = {}
            for i, (char_start, canonical, end_token) in enumerate(hit_positions):
                # Content starts after the header line
                nl_pos = text.find("\n", char_start)
                content_start = nl_pos + 1 if nl_pos != -1 else len(text)
                next_start = hit_positions[i + 1][0] if i + 1 < len(hit_positions) else len(text)
                sections[canonical] = text[content_start:next_start].strip()

            return sections

        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Regex fallback
    # ------------------------------------------------------------------

    def _regex_fallback(self, text: str) -> dict[str, str]:
        """
        Pure-regex section detection.
        Scans lines for known header aliases, groups content until next header.
        Case-insensitive; used in unit tests and as spaCy backup.
        """
        if not text:
            return {}

        lines = text.splitlines()
        sections: dict[str, str] = {}
        current_key: str | None = None
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            canonical = _ALIAS_TO_CANONICAL.get(stripped.lower())
            if canonical is not None:
                # Flush the previous section
                if current_key is not None:
                    sections[current_key] = "\n".join(current_lines).strip()
                current_key = canonical
                current_lines = []
            elif current_key is not None:
                current_lines.append(line)

        # Flush the last section
        if current_key is not None:
            sections[current_key] = "\n".join(current_lines).strip()

        return sections
