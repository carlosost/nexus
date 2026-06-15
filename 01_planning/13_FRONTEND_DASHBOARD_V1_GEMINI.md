# Carlos

Now its time to give attention to frontend. write a prompt to request Claude Cowork to build a plan to enhance frontend. The main page must present a list of existing Applications and respective information. In main page the user will also be able to add a new Job, new Candidate and new Application (associating one Job to a Candidate). The user will be able to select 1 or multiple Applications and request to run the pipeline, but will not wait for this response because the plan is to run the pipeline asynchronously. Add new Job or Candidate means chose a file and submit it to backend to process. Add new Application means select a Job and a Candidate and associate them through an API call.

---
# Gemini
Here is a comprehensive, production-ready prompt tailored for your Claude CoWork thread. It translates your frontend requirements into a highly structured architectural specification—ensuring the AI plans for asynchronous tracking, clear UI components, and clean API boundaries instead of just throwing together a basic mock interface.

---

**Copy and paste the text below into your Claude CoWork thread:**

```markdown
Act as a Principal Frontend Engineer and UX Architect. We need to design a comprehensive implementation plan to build out our frontend application layer (React + Vite). 

Our backend API is running on port 8000, and our frontend dev server runs on port 5173. The primary goal of this frontend is to provide an intuitive dashboard for high-end technical candidate screening, maintaining clear boundaries between entity creation (Ingestion) and pipeline execution (Orchestration).

Please draft a detailed frontend execution plan covering component architecture, state management, and API integration paths for the following core requirements:

### 1. Main Dashboard Views & Interactive States
- **The Application Inventory List:** The central component must be a robust, scannable table or grid displaying all existing Candidate Applications. It must show critical metadata at a glance: Candidate Name, Target Job Title, Current Status (e.g., Pending, Processing, Evaluated, Failed), and Final Match Score if available.
- **Bulk Selection & Asynchronous Execution Trigger:** Users must be able to select one, multiple, or all Applications via checkboxes. A prominent global action button will allow them to trigger the evaluation pipeline for the selected batch. 
- **Non-Blocking UI UX Framework:** Crucially, triggering the pipeline must be entirely asynchronous. The UI must fire the API execution requests, instantly flip the selected applications' statuses to 'Processing' with local loading indicators, and immediately return control to the user. The plan should outline how we will handle state updating (e.g., via polling the `/api/applications/<id>/score/` endpoint every few seconds) since the backend processes these via an async model pattern.

### 2. File-Based Ingestion Actions (Modals or Dedicated Panels)
- **Add New Job:** A form/modal that allows the user to select a Job Description document (PDF) and submit it via a multipart/form-data POST request to the backend ingestion endpoint.
- **Add New Candidate:** A matching interface where a user selects a raw Resume document (PDF) and uploads it, triggering the backend's parsing and keyword isolation engine.
*Note: Both actions mean choosing a local file, validating it on the client side, and executing a clean file-stream upload.*

### 3. Relational Association Creation
- **Add New Application:** An intuitive interface (such as a modal with dropdown components) that allows the user to select one existing Job and one existing Candidate from fetched collections, and associate them together by making a clean API POST request to generate a brand-new Application record.

### Technical & Architecture Blueprint Requirements:
Please structure the response to provide:
1. **Component Hierarchy Diagram:** Map out how the views (`Dashboard`, `ApplicationTable`, `IngestionModal`, `AssociationForm`) should layer over each other.
2. **State Management Strategy:** Detail how we will manage the lists of Jobs, Candidates, and Applications cleanly (e.g., using React Context, TanStack Query/React Query, or lightweight custom hooks).
3. **API Integration Matrix:** Define the exact axios/fetch request structures, matching content-types (`application/json` vs `multipart/form-data`), and error-handling paradigms for when network timeouts or invalid documents are uploaded.

Let's make sure this frontend reads like an enterprise-grade SPA that handles asynchronous state transitions flawlessly.

```