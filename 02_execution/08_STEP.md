# Carlos

Act as a Principal Staff Engineer. We need to audit and refine our `execution_plan_v2.md` before we begin writing code. While the milestone structure and architectural boundaries are correct, a deep-dive risk assessment has surfaced three critical execution gaps that will cause our Double-Loop TDD test suite to stall or break.
We need to patch these risks directly into our V2 plan. Please update the plan and output it as a code block for `execution_plan_v2.md` addressing the following engineering realities:
1. **The pytest-bdd Parameterization Trap (Milestone 0.5):** Mapping unstructured PDF text to canonical sections via spaCy is highly variable. If we write naive BDD scenarios, our features will become unreadable or brittle. We must explicitly mandate that `features/document_ingestion.feature` utilizes Gherkin Data Tables to pass structured multi-line text strings and layout variations into our step definitions.
2. **The Idempotency Factory-Boy Blindspot (Milestone 0.6):** Our plan states that `seed_demo` must be idempotent, but it relies on `factory-boy`. Running standard factories twice on highly relational schemas (Jobs -> Candidates -> Applications -> Embeddings) will trigger IntegrityErrors or duplicate records. Update the strategy: the seeding script must strictly use Django's `.get_or_create()` with natural unique keys (like emails/slugs), or use an explicit data purging step (`Model.objects.all().delete()`) at the very beginning of the command execution block.
3. **The Telemetry Method-Binding Hazard (Telemetry Contract):** The current contract suggests patching methods at construction time (`self.evaluate = pipeline_observability.instrument(...)`). This dynamically breaks Python's method binding and reference metadata, making it incredibly painful to use `unittest.mock.patch.object` in downstream tests. Update the Telemetry Contract to enforce the standard decorator pattern directly on class methods at the definition layer (`@pipeline_observability.instrument("stage_name")`), rather than overriding instances in `__init__`.
**Your Task:**
1. Generate the updated, bulletproof version of `execution_plan_v2.md` inside a markdown block. Ensure these specific testing and execution safety measures are woven into Milestones 0.5, 0.6, and the Telemetry Contract.
2. Provide the first complete `features/document_ingestion.feature` utilizing a Gherkin Data Table for structural section mapping, along with its matching `pytest-bdd` step definitions showing how to extract data from that table cleanly.
Let's tighten this execution loop so our test suite remains reliable and fast.

---
# Claude

Now I'll make all three edits to `execution_plan_v2.md`, then rewrite the feature file and step definitions.Now rewrite the feature file with proper Data Tables:Now update the step definitions to handle the data table steps:Three files updated. Here's what changed and why:

**`execution_plan_v2.md`** — three surgical patches:

1. **Telemetry Contract** — replaced the `self.evaluate = instrument(...)` pattern with the correct `@pipeline_observability.instrument("stage_name")` class-level decorator, explained exactly why construction-time binding breaks `patch.object`, and noted that `SemanticMatchEvaluator` carries this debt into M7.

2. **M0.5 BDD section** — added a ⚠️ Parameterization Trap callout showing the brittle before vs. the correct Data Table after, and explaining that `datatable.rows[0]` is the header row and column lookup should be name-based (not positional).

3. **M0.6 Seeding** — added an Idempotency Strategy section mandating `get_or_create()` keyed on natural unique fields (`title` for Job, `email` for Candidate, `(job, candidate)` for Application), and an optional `--purge` flag guarded by `assert not settings.IS_PRODUCTION`.

**`features/document_ingestion.feature`** — the four section-detection scenarios now all use a three-column `| header_text | canonical_key | sample_content |` Data Table. Covers canonical headers, optional sections, mixed-case normalization, and header synonyms ("Work History" → "experience") — all with a single `Then each canonical_key from the table is present in the detected sections` assertion. No scenario changes required when the synonym list grows.

**`features/steps/ingestion_steps.py`** — the two new Data Table steps (`resume_text_from_section_table`, `assert_all_canonical_keys`, `assert_section_content_stored`) include the exact implementation pattern in their docstrings, including the name-based column index lookup. The file-header docstring also documents the `datatable.rows` API contract for whoever implements Step 5.