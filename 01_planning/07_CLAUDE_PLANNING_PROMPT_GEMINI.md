# Carlos
write a Claude CoWork prompt requesting it to build a new plan to cover missing gaps to have a production-like application. For complete resume parser approach, ask to use PyMuPDF + spaCy, with pdfplumber as an optional fallback for layout-sensitive cases.

---
# Gemini
This is exactly the right pivot. A beautifully architected system is useless if it cannot ingest the data it needs to evaluate. Relying on PyMuPDF combined with spaCy for Named Entity Recognition (NER) and structural parsing is a highly mature, production-grade approach, and keeping `pdfplumber` as a fallback ensures you don't get blocked by weirdly formatted, highly designed resumes.

Here is the updated master prompt for Claude. It explicitly highlights the gaps we found, establishes the new parsing stack, corrects the execution order, and demands a complete, end-to-end plan that will actually result in a working product.

---

**Copy and paste the text below into your Claude CoWork thread:**

```markdown
Act as a Principal Staff Engineer. We are refining our execution plan for the AI Resume Evaluator take-home project. 

Our previous Double-Loop TDD plan had excellent architectural rigor, but a critical review revealed massive product gaps that will prevent us from delivering a working application by our June 19th deadline. We must generate a *new*, gap-free, step-by-step plan.

**The Identified Gaps We Must Fix:**
1. **The Ingestion Void:** We completely lacked a document parsing pipeline. A functional pipeline must exist before we can score anything.
2. **The Dependency Trap:** The previous plan ordered the Orchestrator (M4) before the LLM Rubric Scoring (M3). The Orchestrator requires the rubric score to calculate the final formula. 
3. **The LLM Reality Check:** We cannot just mock the LLM; we need an actual integration (OpenAI/Anthropic) using strict JSON schema enforcement (e.g., Pydantic/Instructor) and retry logic.
4. **The Cold Start Problem:** The database cannot be empty when the evaluator boots it up. We need a seeding mechanism.

**The Updated Tech Stack & Architecture:**
- **Backend:** Python, Django, PostgreSQL (+ pgvector).
- **Ingestion/Parsing (NEW):** We will strictly use `PyMuPDF` (fitz) + `spaCy` for the core text extraction and structural parsing. We will include `pdfplumber` as an optional fallback *only* for highly sensitive, multi-column layout edge cases. 
- **Scoring Pipeline:** 1. Hard Gate -> 2. Semantic Match (RRF Hybrid Search) -> 3. Rubric Score (LLM API).
- **Methodology:** We are sticking strictly to **Double-Loop TDD** (pytest-bdd for the outer business loop, pytest for the inner technical loop).

**Your Task:**
Rewrite the entire Step-by-Step Execution Plan from scratch. 

1. **Insert the Missing Milestones:** Add a dedicated parsing/ingestion milestone using the PyMuPDF+spaCy stack. Add a data-seeding milestone so the app boots with mock candidates.
2. **Fix the Execution Order:** Reorder the milestones so no component is built before its dependencies exist. All scoring stages must be complete before the Orchestrator is built.
3. **Time-Boxed Steps:** Assign strict time-boxes (e.g., "4 hours") to each milestone with a clear fallback strategy if we fall behind schedule.
4. **The First Step:** Give me the first Gherkin feature file for the new Ingestion/Parsing milestone, its step definitions, and the first failing inner-loop unit test for the PyMuPDF extraction logic.

Let's optimize this plan for a results-driven workflow. The final deliverable must be a flawlessly executing, demonstrable product, not just a theoretical backend.

```

---
# Carlos
Update the prompt to request to not overwrite existing plan, but create a new md file. Also, the prompt must consider to increment current approach and not create a new one from scratch.

---
# Gemini
This is a smart approach. Preserving the original plan as "v1" allows you to maintain a clean paper trail of your architectural decisions and pivots. It shows the evaluator that you don't just write code; you manage project scope and iterate safely.

Here is the updated master prompt. It explicitly instructs Claude to use the existing plan as the baseline, patch in the necessary upgrades, fix the dependency ordering, and output everything into a brand-new version-controlled file.

---

**Copy and paste the text below into your Claude CoWork thread:**

```markdown
Act as a Principal Staff Engineer. We are reviewing and iterating on our current Double-Loop TDD execution plan for the AI Resume Evaluator.

Our current architectural foundation is excellent, but we need to increment the plan to close some critical product gaps before our June 19th deadline. 

**Important Version Control Constraint:**
Do NOT overwrite our existing execution plan file. We must preserve our history. You must generate the updated plan as a brand new file named `execution_plan_v2.md`. 

**The Incremental Updates Required:**
Please take our existing step-by-step plan and modify it to include the following corrections and additions. Do not rewrite the methodology from scratch; just patch the existing structure.

1. **Insert an Ingestion Milestone:** Add a new step (e.g., Milestone 0.5) dedicated to a document parsing pipeline. We will use `PyMuPDF` (fitz) + `spaCy` for text extraction and structural parsing, keeping `pdfplumber` strictly as an optional fallback for complex, multi-column layouts.
2. **Insert a Database Seeding Milestone:** Add a quick step (or merge into M0) to seed the database with 1 mock Job Description and 3 mock Candidates so the app is fully demonstrable immediately on boot.
3. **Fix the Dependency Order:** Adjust the execution sequence. The Orchestrator calculates the Final Score, which strictly depends on the Rubric Score. The Rubric milestone MUST be completed before the Orchestrator milestone.
4. **Real LLM Integration:** Update the Rubric Scoring milestone tasks. We cannot just mock the LLM in production; we must implement an actual API integration (OpenAI/Anthropic) using strict JSON schema enforcement (e.g., Pydantic/Instructor) and retry logic. 

**Your Task:**
1. Output the complete, updated step-by-step execution plan into a new markdown block (designated for `execution_plan_v2.md`). Maintain our strict Double-Loop TDD methodology and the existing time-boxes, ensuring the new steps also have strict time-boxes and fallback strategies.
2. Give me the very first Gherkin feature file for the newly added Ingestion/Parsing milestone, its step definitions, and the first failing inner-loop unit test for the PyMuPDF extraction logic.

Let's lock in this V2 plan and start building.

```

---
# Carlos
Update the prompt to remember Claude to keep using Double-Loop Test-Driven Development methodology, also use logging and observability features created

---
# Perplexity
Here is the final, optimized copy-and-paste prompt. It reinforces all your constraints, explicitly demands the creation of a new `execution_plan_v2.md` file, patches the missing ingestion/seeding gaps, corrects the architectural dependency order, and firmly reminds Claude to wrap every step in Double-Loop TDD while utilizing the custom logging and observability layers.

---

**Copy and paste the text below into your Claude CoWork thread:**

```markdown
Act as a Principal Staff Engineer. We are reviewing and iterating on our current step-by-step execution plan for the AI Resume Evaluator.

Our current architectural foundation is solid, but we need to increment the plan to close some critical product gaps. 

**Important Version Control Constraint:**
Do NOT overwrite our existing execution plan file. We must preserve our architectural history. You must generate the updated plan as a brand-new file named `execution_plan_v2.md`. 

**The Incremental Updates Required:**
Please take our existing milestone-based plan and modify it to include the following corrections and additions. Do not rewrite the core methodology from scratch; patch and build upon the existing structure.

1. **Insert an Ingestion Milestone:** Add a new step (Milestone 0.5) dedicated to a document parsing pipeline. We will use `PyMuPDF` (fitz) + `spaCy` for text extraction and structural parsing, keeping `pdfplumber` strictly as an optional fallback for complex, multi-column layouts.
2. **Insert a Database Seeding Milestone:** Add a step to seed the database with 1 mock Job Description and 3 mock Candidates so the application is fully demonstrable immediately on boot.
3. **Fix the Dependency Order:** Adjust the execution sequence. The Orchestrator calculates the Final Score, which strictly depends on the Rubric Score. Therefore, the Rubric Scoring milestone MUST be fully completed before the Orchestration milestone.
4. **Real LLM Integration:** Update the Rubric Scoring milestone tasks. We cannot just mock the LLM in production; we must implement an actual API integration (OpenAI/Anthropic) using strict JSON schema enforcement (e.g., Pydantic/Instructor) and retry logic. 

**Strict Methodology Reminders to Enforce in V2:**
- **Double-Loop Test-Driven Development (Strict):** Every single milestone—including the newly added Ingestion layer—must be structured around Double-Loop TDD. Write the business specification in `pytest-bdd` (Outer Loop Gherkin syntax) to let it fail, then drop down into `pytest` (Inner Loop unit tests) to write failing technical tests before any production code is written. 
- **Telemetry Integration:** Explicitly define how our custom Logging and Observability modules are woven into each new and existing milestone. Every pipeline stage must be wrapped in our decorator-based observability tracking (for latency and performance profiling) and use our structured JSON logging (for tracking state transitions, parsing states, and LLM override audits).

**Your Task:**
1. Output the complete, updated step-by-step execution plan into a new markdown block designated for `execution_plan_v2.md`. Ensure every milestone contains a strict "time-box" and a "fallback strategy" to guarantee we meet the deadline.
2. Give me the very first Gherkin feature file for the newly added Ingestion/Parsing milestone, its step definition mapping, and the first failing inner-loop unit test for the PyMuPDF text extraction logic.

Let's lock in this V2 plan and start building.

```