# Architecture Decisions

This document records the *why* behind three load-bearing design choices in Elvex Nexus. It follows a simplified ADR format: **Context → Decision → Consequences**. If you're about to "fix" one of these because it looks unconventional, read the rationale first — there's usually a deliberate trade-off underneath it.

---

## ADR-001: Markdown-First Job Creation

### Context

Every Job record needs five things before the pipeline can run against it: a title, a description, a structured requirements blob (`requirements_raw`), and a set of Hard Gate criteria (`must_haves`) that the pipeline evaluates as `pass` / `fail` / `unknown`. The obvious UI choice is a multi-field web form — a text input for the title, a textarea for the description, a repeatable widget for skills, and a criterion builder for must-haves.

We rejected that approach.

### Decision

`POST /api/jobs/` accepts a single field, `raw_markdown`, containing a structured Markdown document:

```markdown
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
```

`parse_job_markdown()` (`resume_pipeline/ingestion/job_parser.py`) is a pure function — no I/O, no ORM access — that walks the heading structure and emits a `JobSpec` dataclass. The view (`JobListCreateView.post`) maps `JobSpec` onto `Job.objects.create(**job_spec.to_model_kwargs())`. Malformed sections raise a `JobParseError(field_key, detail)`, which the view translates into a `422` with a field-level error map — so `{"must_haves": "..."}` tells the caller exactly which heading block broke, not just "bad request."

**Why Markdown beats a multi-field form here:**

1. **Developer experience.** A recruiter or hiring manager already has a job description in some text form — an email thread, a Notion doc, a Google Doc export. Markdown is the lowest-friction target format: paste, tweak two headings, submit. A multi-field form means re-typing structured data that already exists as prose.
2. **Standardization without rigidity.** The heading structure (`# Title`, `## Description`, `## Requirements`, `## Must Haves`) gives us a single source of truth for "what a valid job spec looks like" — codified once in `JOB_SPEC` (`resume_pipeline/management/commands/_seed_data.py`) and enforced once in the parser. A form would need a corresponding field for every nested structure (per-skill rows, per-criterion rows with a type-dependent sub-schema for `years_experience` vs. `keyword_presence`) — that's `O(criteria)` UI complexity for a problem Markdown solves with three heading levels.
3. **LLM context-readiness.** The same Markdown blob that creates the Job record is *already* the ideal shape to hand to an LLM as context — for rubric scoring prompts, for future "suggest must-haves from this job description" tooling, or for re-embedding (see ADR-003). A form-backed job would require a serialization step before it could be used as LLM input; the Markdown-first approach means ingestion format and LLM-context format are the same artifact.

### Consequences

- **Trade-off accepted:** Markdown parsing is more brittle than discrete form fields — a missing blank line or a renamed heading can break extraction. We mitigate this with strict, field-attributed `JobParseError`s (422, not a generic 500) and 16 BDD scenarios (`features/job_lifecycle.feature`) covering both the happy path and every malformed-input case we've identified.
- **Trade-off accepted:** There's no client-side autocomplete or validation-as-you-type the way a structured form could offer. The frontend (`JobIngestionModal`) compensates with a format hint and surfaces parser errors inline rather than pre-validating client-side.
- **Win:** Adding a new `must_haves` criterion type requires one new parser branch and one new `HardGateEvaluator._check_<type>` handler — no form-schema migration.

---

## ADR-002: Resume Processing Failovers — PyMuPDF Primary, pdfplumber Fallback

### Context

Resume PDFs are not uniform. Most are single-column documents that any competent PDF text extractor handles correctly. A meaningful minority — particularly resumes built from design templates — use multi-column layouts, text boxes, or tables, where naive PDF text extraction interleaves columns and produces garbled, sub-50-character output.

### Decision

`ResumeParser` (`resume_pipeline/ingestion/parser.py`) is backend-pluggable and tries two extractors in sequence:

1. `**PyMuPDFBackend` (primary)** — `pymupdf` (`fitz`) is the fast path. It's a C-extension-backed library with low per-document latency, and it handles the single-column majority case correctly and quickly.
2. `**PdfplumberBackend` (fallback)** — invoked only when the primary backend's output falls under a length threshold (the parser's fallback trigger is "primary yielded fewer than 50 characters"). `pdfplumber` is slower but layout-aware — it can reconstruct reading order from multi-column and table-based layouts that defeat a naive text-stream extractor.

```python
def parse(self, filepath: str) -> ParsedDocument:
    # Never raises — on failure returns status=FAILED with empty text/sections.
    text, page_count, parser_used, status = self._extract(filepath)
    ...
```

The result is a `ParsedDocument` with a `status` field (`ok` / `fallback_used` / `failed`) and a `parser_used` field, both surfaced through `audit_logger` — so you can query "what fraction of resumes needed the fallback path" in production logs without re-parsing anything.

**Why a tiered pipeline instead of always using the more capable parser:**

- **Speed at the median.** The overwhelming majority of resumes are single-column. Running `pdfplumber`'s layout-reconstruction logic against every document would pay its latency cost on every request for a problem that affects a minority of inputs. The tiered approach pays the slow path only when the fast path demonstrably failed.
- **Graceful degradation, not graceful failure.** `parse()` is documented to *never raise*. If both backends fail, the caller gets a `ParsedDocument` with `status=FAILED` and empty sections — the `Candidate` record is still created (with empty `resume_parsed`), and the Hard Gate stage naturally produces `UNKNOWN` outcomes for any criterion that needs data the parser couldn't extract (see `HardGateEvaluator._check_years_experience`, which explicitly returns `UNKNOWN` when `total_experience_years` is absent). A parsing failure degrades the pipeline's confidence, not its availability.

### Consequences

- **Trade-off accepted:** A candidate whose resume defeats both backends gets a Hard Gate outcome of `UNKNOWN` rather than a hard rejection — by design (per the precedence rule `FAIL > UNKNOWN > PASS`, this never silently becomes a `PASS`), but it does mean such a candidate needs a human reviewer to look at the raw PDF rather than trusting the pipeline's verdict.
- **Win:** The fallback trigger and both backends are dependency-injectable (`ResumeParser(primary=..., fallback=..., detector=...)`), so unit tests exercise the failover logic with mock backends — no real PDF fixtures required for the branching logic itself.

---

## ADR-003: Vector Embeddings Execution Lifecycle

### Context

Two entities need vector embeddings for downstream candidate-fitness scoring: `Candidate` resumes (per-section: summary, experience, skills, education, certifications) and `Job` postings (per-section: title, description, requirements, must_haves). Both embedding tables (`SectionEmbedding`, `JobSectionEmbedding`) feed Stage 2 of the pipeline — `SemanticMatchEvaluator` — which computes cosine similarity between a candidate's and a job's per-section vectors, then fuses those similarities with a lexical (full-text search) rank via Reciprocal Rank Fusion (`search/rrf.py`) to produce the `rrf_score` stored on `SemanticMatchResult`.

The open design question: **when** should embeddings be (re)computed?

### Decision

Embeddings are computed **synchronously on mutation**, not on a schedule and not lazily on first read:

- `embed_job_sections(job)` (`resume_pipeline/pipeline/job_embedder.py`) is called immediately after a `Job` is created via `POST /api/jobs/`, and again after any `PATCH` that changes job fields.
- The candidate-side equivalent runs after a `Candidate` is created from a parsed resume (`POST /api/candidates/`).

Each call **upserts** rather than appends — `get_or_create(job=job, section=section_name, ...)` followed by a conditional `save()` only if content or vector actually changed:

```python
embedding_obj, _ = JobSectionEmbedding.objects.get_or_create(
    job=job,
    section=section_name,
    defaults={"content": text, "embedding": vector, "model_name": _model_name()},
)
if embedding_obj.content != text or embedding_obj.embedding != vector:
    embedding_obj.content = text
    embedding_obj.embedding = vector
    embedding_obj.save(update_fields=["content", "embedding", "model_name"])
```

This is enforced by `unique_together = ("job", "section")` at the model level, so a re-embed after a `PATCH` cannot silently create duplicate rows — `JobSectionEmbedding.objects.filter(job=job).count()` stays constant across any number of edits.

Failure handling is deliberately permissive: embedding errors (e.g., `TimeoutError` from the embedding API) are caught at the call site in the view and **swallowed** — the `Job` or `Candidate` row is still persisted, and a 201 is still returned. The system treats "the record exists but isn't embedded yet" as a recoverable, retriable state, not a transaction failure.

**Why trigger on mutation instead of batch/cron or lazy-on-read:**

1. **Freshness matters more than throughput here.** Semantic Match (Stage 2) is the very next pipeline stage a new Job or Candidate is likely to participate in — often within the same review session a recruiter just created the record in. A nightly batch job would mean a job posted at 9 AM can't be meaningfully matched against until the next cron run; that's an unacceptable latency for an interactive recruiting tool.
2. **Mutation is the only point where staleness is introduced.** Embeddings only need to change when the underlying text changes. Triggering on create/update (rather than on a schedule) means we recompute exactly when — and only when — recomputation is necessary, with zero polling overhead and zero stale-read risk in between.
3. **Lazy-on-read was rejected** because it pushes embedding latency onto the read path of `SemanticMatchEvaluator`, which runs as part of the scoring pipeline — a path where we want predictable, already-warm latency, not a cold-start embedding call blocking a pipeline run.

### Consequences

- **Trade-off accepted:** Write latency on `POST /api/jobs/` and `POST /api/candidates/` includes the embedding API round-trip (mitigated today by the `mock` backend's deterministic zero-network vector generation in non-production environments, and by swallowing `TimeoutError` so a slow embed never fails the write).
- **Win:** `SemanticMatchEvaluator` can always assume embeddings exist and are current for any `Job`/`Candidate` that successfully completed its create/update call — no defensive "is this stale?" check needed at score time.
- **Win:** Because re-embedding is idempotent (upsert, not insert), replaying a `PATCH` or retrying a failed embed call is always safe — there's no cleanup step needed if a request is retried.

