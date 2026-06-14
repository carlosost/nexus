"""
Hard Gate — Stage 1 of the resume evaluation pipeline.

Evaluates mandatory must-haves against a candidate's parsed resume.
Outcomes are strictly: pass | fail | unknown — no other values.

Design rules:
  - FAIL takes precedence over UNKNOWN in aggregation (safety-first: uncertainty
    does not override a confirmed disqualification).
  - UNKNOWN is produced when required data is absent, not when a check scores
    poorly. Scoring belongs in Stage 3 (Rubric).
  - All criterion evaluators must return a CriterionResult — never raise on
    bad data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Outcome enum
# ---------------------------------------------------------------------------

class GateOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CriterionResult:
    name: str
    outcome: GateOutcome
    evidence: Optional[str] = None


@dataclass
class HardGateEvaluation:
    criterion_results: list[CriterionResult] = field(default_factory=list)

    @property
    def outcome(self) -> GateOutcome:
        """
        Aggregate across all criterion results.

        Precedence: FAIL > UNKNOWN > PASS.
        No results → UNKNOWN (we cannot confirm a pass on zero evidence).
        """
        if not self.criterion_results:
            return GateOutcome.UNKNOWN

        outcomes = {r.outcome for r in self.criterion_results}

        if GateOutcome.FAIL in outcomes:
            return GateOutcome.FAIL
        if GateOutcome.UNKNOWN in outcomes:
            return GateOutcome.UNKNOWN
        return GateOutcome.PASS


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class HardGateEvaluator:
    """
    Evaluates a set of must-have criteria against a parsed resume.

    Usage::

        evaluator = HardGateEvaluator()
        evaluation = evaluator.evaluate(
            must_haves=job.must_haves,
            resume_parsed=candidate.resume_parsed,
        )
        if evaluation.outcome == GateOutcome.FAIL:
            # short-circuit; final score = 0
            ...
    """

    # Registry of supported criterion types.
    # Extend by adding a new `_check_<type>` method and registering it here.
    _CRITERION_HANDLERS: dict[str, str] = {
        "years_experience": "_check_years_experience",
        "keyword_presence": "_check_keyword_presence",
        "certification": "_check_certification",
    }

    def evaluate(
        self,
        must_haves: dict,
        resume_parsed: dict,
    ) -> HardGateEvaluation:
        """
        Args:
            must_haves: Mapping of criterion_name → config dict (includes "type" key).
            resume_parsed: Structured resume data produced by the resume parser.

        Returns:
            HardGateEvaluation with one CriterionResult per entry in must_haves.
        """
        evaluation = HardGateEvaluation()

        for name, config in must_haves.items():
            result = self._dispatch(name, config, resume_parsed)
            evaluation.criterion_results.append(result)

        return evaluation

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    def _dispatch(
        self, name: str, config: dict, resume: dict
    ) -> CriterionResult:
        criterion_type = config.get("type", "")
        handler_name = self._CRITERION_HANDLERS.get(criterion_type)

        if handler_name is None:
            return CriterionResult(
                name=name,
                outcome=GateOutcome.UNKNOWN,
                evidence=f"Unsupported criterion type: '{criterion_type}'",
            )

        handler = getattr(self, handler_name)
        return handler(name, config, resume)

    # ------------------------------------------------------------------
    # Criterion handlers
    # ------------------------------------------------------------------

    def _check_years_experience(
        self, name: str, config: dict, resume: dict
    ) -> CriterionResult:
        """
        Checks `resume["total_experience_years"] >= config["minimum_years"]`.

        Returns UNKNOWN when the resume doesn't carry parsed experience years.
        """
        required: Optional[float] = config.get("minimum_years")
        candidate: Optional[float] = resume.get("total_experience_years")

        if candidate is None:
            return CriterionResult(
                name=name,
                outcome=GateOutcome.UNKNOWN,
                evidence="Field 'total_experience_years' absent from parsed resume",
            )

        if required is None:
            return CriterionResult(
                name=name,
                outcome=GateOutcome.UNKNOWN,
                evidence="Criterion config missing 'minimum_years'",
            )

        if candidate >= required:
            return CriterionResult(
                name=name,
                outcome=GateOutcome.PASS,
                evidence=f"Candidate has {candidate} years; required {required}",
            )

        return CriterionResult(
            name=name,
            outcome=GateOutcome.FAIL,
            evidence=f"Candidate has {candidate} years; required {required}",
        )

    def _check_keyword_presence(
        self, name: str, config: dict, resume: dict
    ) -> CriterionResult:
        """
        Checks that required keywords appear in specified resume sections.

        config keys:
            keywords (list[str])  — terms to search for (case-insensitive)
            sections (list[str])  — resume sections to search in (default: ["skills", "experience"])
            match_threshold (float) — fraction of keywords that must match (default: 1.0)

        Returns UNKNOWN when the keyword list is empty (misconfigured criterion).
        """
        keywords: list[str] = config.get("keywords", [])
        sections: list[str] = config.get("sections", ["skills", "experience"])
        threshold: float = config.get("match_threshold", 1.0)

        if not keywords:
            return CriterionResult(
                name=name,
                outcome=GateOutcome.UNKNOWN,
                evidence="Criterion config has an empty 'keywords' list",
            )

        search_corpus = " ".join(
            str(resume.get(section, "")) for section in sections
        ).lower()

        found = [kw for kw in keywords if kw.lower() in search_corpus]
        missing = [kw for kw in keywords if kw.lower() not in search_corpus]
        match_ratio = len(found) / len(keywords)

        if match_ratio >= threshold:
            return CriterionResult(
                name=name,
                outcome=GateOutcome.PASS,
                evidence=f"Found all required keywords: {found}",
            )

        return CriterionResult(
            name=name,
            outcome=GateOutcome.FAIL,
            evidence=f"Missing keywords: {missing}; found: {found}",
        )

    def _check_certification(
        self, name: str, config: dict, resume: dict
    ) -> CriterionResult:
        """
        Checks that all required certifications are listed in the resume.

        config keys:
            required (list[str]) — certification names (case-insensitive comparison)

        Returns UNKNOWN when the certification section is absent from the parsed resume.
        """
        required_certs: list[str] = config.get("required", [])
        resume_certs: Optional[list] = resume.get("certifications")

        if resume_certs is None:
            return CriterionResult(
                name=name,
                outcome=GateOutcome.UNKNOWN,
                evidence="Field 'certifications' absent from parsed resume",
            )

        resume_certs_lower = {c.lower() for c in resume_certs}
        missing = [c for c in required_certs if c.lower() not in resume_certs_lower]

        if not missing:
            return CriterionResult(
                name=name,
                outcome=GateOutcome.PASS,
                evidence=f"All required certs present: {resume_certs}",
            )

        return CriterionResult(
            name=name,
            outcome=GateOutcome.FAIL,
            evidence=f"Missing certifications: {missing}",
        )
