# Experience Extractor — Implementation Plan

## Problem

The hard gate evaluator checks `resume["total_experience_years"]` (a float) to enforce
minimum experience requirements. The field is documented as part of the `resume_parsed`
JSON schema (`models.py`, line 86) but is never populated: `ResumeParser` stores only
raw section text blobs and performs no structured extraction.

Result: every `years_experience` gate criterion resolves to `UNKNOWN` rather than
`PASS` or `FAIL`, regardless of the candidate's actual tenure.

### Observed failure (June 2026)

```
gate_transition  criterion=min_experience  outcome=unknown
evidence="Field 'total_experience_years' absent from parsed resume"
```

Resume in question had both:
- An explicit statement in the summary: **"15+ years of experience"**
- Six dated roles spanning 2004–Present with parseable month-year ranges

---

## Solution Overview

Add a new `ExperienceExtractor` class that runs after `SectionDetector` inside
`ResumeParser.parse()`. It tries two strategies in order, takes the first result, and
merges `total_experience_years` into the sections dict before it is stored.

```
ResumeParser.parse(filepath)
  ├── _extract()                      ← unchanged (pymupdf / pdfplumber)
  ├── SectionDetector.detect(text)    ← unchanged
  └── ExperienceExtractor.extract(sections)   ← NEW
        └── sections["total_experience_years"] = value
            stored in Candidate.resume_parsed  ← no migration needed (JSONField)
```

---

## Extraction Strategies

### Priority 1 — Explicit statement in summary

Search the `summary` section for self-reported experience figures. Highest confidence
because the candidate has already done the calculation.

Patterns (case-insensitive):

| Pattern | Example match | Extracted value |
|---|---|---|
| `(\d+)\+?\s*years?\s+of\s+(?:professional\s+)?experience` | "15+ years of experience" | `15.0` |
| `over\s+(\d+)\s*\+?\s*years?` | "over 10 years" | `10.0` |
| `more\s+than\s+(\d+)\s*\+?\s*years?` | "more than 8 years" | `8.0` |

The `+` suffix is treated as a floor (conservative). The numeric value is extracted
and returned as a `float`.

### Priority 2 — Date range calculation from experience section

Parse all date spans from the `experience` section text, compute the total
non-overlapping duration using a merge-intervals algorithm.

#### Date formats supported

| Format | Example |
|---|---|
| Full month-year range | `Jun 2022 – Present`, `Apr 2021 – Jun 2022` |
| Abbreviated month | `Jun 2022`, `Apr 2021` |
| Year-only | `2004 – 2009`, `Oct 2009 – Sep 2011` |
| "Present" / "Current" / "Now" | resolved to `datetime.today()` |
| En-dash, em-dash, hyphen, `to` | all accepted as range separators |

#### Worked example — Carlos Ost resume

| Role | Start | End | Duration |
|---|---|---|---|
| Ci&T / IBM / Vai-Ingdesi | Jan 2004 | Dec 2009 | 6.0 y |
| Embratel | Oct 2009 | Sep 2011 | 1.9 y |
| Telefônica / Vivo | Sep 2011 | Aug 2016 | 4.9 y |
| Saffe | Jun 2017 | Apr 2021 | 3.8 y |
| Globant | Apr 2021 | Jun 2022 | 1.2 y |
| Meez | Jun 2022 | Present | ~4.0 y |

After merge-intervals (roles at Globant/Meez are contiguous; Embratel/Telefônica
overlap slightly): **≈ 20.8 years**.

The summary strategy returns `15.0` (candidate's own conservative figure) and takes
priority over the calculated `20.8`.

#### Merge-intervals algorithm

```
1. Parse all (start_date, end_date) pairs from text
2. Sort by start_date
3. Walk sorted list: if current.start <= prev.end, extend prev.end = max(prev.end, current.end)
4. Sum durations of merged intervals
5. Round to 1 decimal place
```

This prevents double-counting overlapping tenures (e.g., consulting alongside employment).

---

## Fallback behaviour

If neither strategy produces a value, `ExperienceExtractor.extract()` returns `None`
and no key is added to `sections`. The hard gate then returns `UNKNOWN` as before —
unchanged behaviour, no regression.

---

## Source attribution and confidence

`extract()` returns a `(value, source)` tuple:

| `source` | Meaning |
|---|---|
| `"summary_statement"` | Extracted from explicit phrase in summary |
| `"date_calculation"` | Computed from parsed date ranges in experience |
| `None` | Not found; value is also `None` |

---

## Audit logging

New event `experience_years_extracted` added to `logging_module.py`:

```json
{
  "ts": "...",
  "event": "experience_years_extracted",
  "application_id": "...",
  "value": 15.0,
  "source": "summary_statement"
}
```

Emitted from `ResumeParser.parse()` when a value is found. If neither strategy succeeds,
no event is emitted (avoids noise for genuinely incomplete resumes).

---

## Files changed

| File | Change |
|---|---|
| `resume_pipeline/ingestion/experience_extractor.py` | **New** — `ExperienceExtractor` class |
| `resume_pipeline/ingestion/parser.py` | Add ~5 lines after `SectionDetector.detect()` call |
| `resume_pipeline/logging_module.py` | Add `log_experience_years_extracted()` method |
| `tests/unit/test_experience_extractor.py` | **New** — unit tests, `@pytest.mark.unit` |

No model migration. No serializer change. No frontend change.

---

## Test plan

All tests in `tests/unit/test_experience_extractor.py`, marked `@pytest.mark.unit`
(no DB, no network).

### Strategy A — summary statement

| Scenario | Input | Expected value |
|---|---|---|
| Standard phrase | "15+ years of experience" | `15.0` |
| Floor notation | "over 10 years of professional experience" | `10.0` |
| Alternate phrasing | "more than 8 years of experience" | `8.0` |
| No match | "Experienced engineer with broad skills" | `None` |
| No summary key | `{}` | `None` |

### Strategy B — date calculation

| Scenario | Expected behaviour |
|---|---|
| Full month-year ranges | Correct duration computed |
| Year-only range (`2004–2009`) | Jan used as default month |
| "Present" end date | Resolved to today, duration correct |
| Two overlapping roles | Counted once (merge-intervals) |
| No date ranges found | Returns `None` |
| Single entry, no end date | Treated as still active if "Present" implied |

### Priority / integration

| Scenario | Expected behaviour |
|---|---|
| Both summary and dates present | Summary value returned, date calc skipped |
| Only dates present | Date calc value returned |
| Neither present | `(None, None)` returned |
| `extract()` wired in `ResumeParser` | `sections["total_experience_years"]` present after parse |

---

## Open questions / future work

- **Re-parsing existing candidates**: candidates already stored without `total_experience_years`
  will retain `UNKNOWN` on the gate until their resume is re-uploaded or a backfill
  management command is added. A `recalculate_experience_years` management command
  could be a follow-up.
- **Multi-language resumes**: date formats in Portuguese (e.g., "jun 2022 – presente")
  are not in scope for this iteration but month abbreviation tables can be extended later.
- **Gap years**: the merge-intervals approach counts only active employment periods.
  Career gaps are not counted, which is the correct behaviour for "years of experience".
