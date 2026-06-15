Here is a comprehensive, production-ready Claude prompt designed to generate a highly rigorous engineering plan for your automated pipeline.

Because your architecture involves complex tasks like parsing Markdown into dynamic schema patterns (matching a local file configuration) and managing vector data lifecycles, this prompt explicitly forces Claude to structure its testing plan through **TDD (Test-Driven Development)**, **BDD (Behavior-Driven Development)**, and **E2E (End-to-End)** paradigms.

---

```markdown
I need you to author a comprehensive, production-ready QA and Engineering Verification Plan (`job_lifecycle_plan.md`). This plan will establish the blueprint for validating the complete CRUD lifecycle and automated vector embedding process for the "Job" domain model in our application (`elvex-nexus`).

### Core Architectural Context
* **Backend:** Python, Django, PostgreSQL, PgVector (or dedicated Vector Store).
* **Testing Stack:** Pytest (Unit/Integration), Pytest-BDD (Feature files), Playwright (Frontend E2E), Vitest (Frontend Unit).
* **The Domain Input Workflow:** Users create a Job *exclusively* by submitting a single raw Markdown text block containing the entire job specification. 
* **The Parser:** The system parses this Markdown file cleanly into discrete database properties (`title`, `description`, `requirements`, `must_have_requirements`) by mapping structural layouts against a reference schema defined in our project context (`_seed_data.py` -> `JOB_SPEC`).
* **Downstream Mechanics:** When a Job is mutated or created, an automated downstream pipeline computes and updates semantic vector embeddings. These embeddings are later used to calculate overall Candidate fitness scores, base requirement matches, and special "exceptional criteria" highlights.

### Document Structure & Requirements
Please generate the markdown file with the following explicit sections:

#### 1. Architecture Overview & Test Boundary Map
* Briefly map out the test entry points: Where components shift from Frontend (Playwright) -> API Controller -> Markdown Ingestion Parser Layer -> Vector Database Generation -> Async Pipeline Engine.

#### 2. BDD Feature Specifications (`.feature` blueprints)
Write full, Gherkin-syntax test scenarios covering the full user flow matrix. Include scenarios for:
* **Successful Creation:** Markdown accurately formatted to match `JOB_SPEC` mapping rules.
* **Resilient Graceful Failure:** Handling broken/malformed markdown gracefully without dropping the database connection.
* **Full CRUD Loops:** Scenarios explicitly validating Edit (re-parsing and modifying embeddings) and Delete (cleaning up relational tables and dead vector indices).

#### 3. Backend TDD Engineering Plan (Pytest & Vector Verification)
* Describe specific unit test methods for the parsing logic (verifying exact mapping against `JOB_SPEC`).
* Detail integration test logic for the **Job Embedding Process**. Define steps to assert that an embed pipeline fires on creation/modification, handles remote embedding timeouts cleanly, and explicitly cleans up vectors on database deletion to prevent system leaks.

#### 4. Frontend & E2E Verification Plan (Vitest & Playwright)
* Formulate frontend unit test strategies using Vitest to verify data views, markdown text-area handling, and status alerts.
* Provide complete Playwright E2E blueprints that mock a developer submitting a full job markdown file, tracking processing loader cycles, checking the layout rendering of split categories (Title, Requirements, Must Haves), and deleting the job block safely.

Ensure the final output plan is structured clearly, reads like a technical team spec sheet, and adheres strictly to rigorous TDD/BDD testing methodologies.

```

---

### Pro-Tip for Execution:

If you want Claude to explicitly match your layout exactly without guessing, copy and paste the `JOB_SPEC` dictionary structure out of your `_seed_data.py` file and append it to the bottom of the prompt under a header like: `### Reference Code: JOB_SPEC Schema`.