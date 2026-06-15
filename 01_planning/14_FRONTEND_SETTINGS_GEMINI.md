# Carlos
write a Claude Cowork prompt to build a plan to enhance frontend by adding a Settings page where the user can view, edit, delete all Jobs and Candidates. Also, we need to move features to create new Jobs, Candidates and Application to this new Settings page. remember to also request to use the mixed approach BDD + TDD applied to frontend and create end to end tests.

---
# Gemini
Here is the tailored, production-grade prompt for your Claude CoWork thread. It cleanly restructures your frontend layout, centralizes administrative actions into a dedicated workspace, and enforces a high-quality testing paradigm that combines behavioral expectations with component isolation and end-to-end coverage.

---

**Copy and paste the text below into your Claude CoWork thread:**

```markdown
Act as a Lead Frontend Engineer and QA Architect. We need to evolve our React + Vite frontend architecture by decoupling our main analytical dashboard from administrative data management. 

### Current Layout Status:
We currently handle entity creation (Jobs, Candidates, and Applications) directly on the main dashboard. We want to clean up this user experience by moving these management hooks into a centralized **Settings Page**.

### Target Feature & Refactoring Requirements:

1. **The New Settings Page Ecosystem:**
   - Create a dedicated `/settings` route or view panel acting as our administrative control center.
   - **Job Administration Board:** A section providing a comprehensive list of all existing Jobs. For each Job, the user must be able to:
     * **View:** Expand or click to see the parsing output and internal rubrics.
     * **Edit:** Adjust metadata or targeted parameters.
     * **Delete:** Trigger an API call to remove the Job (handling cascades gracefully).
     * **Create:** Host the file-upload pipeline to submit a new Job Description PDF to the backend.
   - **Candidate Administration Board:** A matching section for managing Candidate records, providing full **CRUD capabilities** (Create via resume PDF upload, View parsed details, Edit metadata, and Delete).
   - **Application Association Center:** Move the feature to link an existing Job to an existing Candidate here. This panel should fetch active collections of both entities and submit a POST request to generate a new application matrix row.

2. **Main Dashboard Simplification:**
   - The primary dashboard page is now strictly read-only and operational. It focusing purely on displaying the main Application inventory table, tracking asynchronous processing states, handling multi-selection, and triggering the async evaluation pipeline.

3. **Frontend Testing Infrastructure (Mixed BDD + TDD + E2E Approach):**
   We need to ensure these administrative actions are completely bulletproof before hooking them up to the real API. Provide a testing strategy that spans:
   - **BDD (Behavior-Driven Development) Scenarios:** Outline functional Given/When/Then user stories for the Settings actions (e.g., *Given a user is on the Settings page, when they upload an invalid file format for a Candidate, then the form catches the error and throws an alert without crashing the page*).
   - **TDD (Test-Driven Development) Component Isolation:** Specify how we will write failing unit/integration tests using **Vitest** and **React Testing Library** to mock API responses and test button clicks, loading skeletons, and structural state variations for our CRUD forms before the implementation code is complete.
   - **End-to-End (E2E) Verification:** Define the testing specs for **Playwright** or **Cypress** to test the complete sequence across pages (e.g., *Upload a new Job on the Settings page $\rightarrow$ link it to a Candidate $\rightarrow$ navigate back to the Main Dashboard $\rightarrow$ verify the new Application row appears and can be selected for evaluation*).

### Expected Output Structure:
Please deliver:
1. **Refactored View Layout and Route Blueprint:** Showing how components move into the new `/settings` domain.
2. **Comprehensive Step-by-Step Implementation Strategy:** Chronologically mapped out to prevent broken views.
3. **The Complete Testing Matrix:** Including explicit code boilerplates for a Vitest unit component file and a Playwright E2E browser file mocking our file uploads and deletion endpoints.

Let's ensure this administrative separation is incredibly clean and completely tested!

```