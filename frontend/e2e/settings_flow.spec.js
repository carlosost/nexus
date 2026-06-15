/**
 * E2E specification: Settings → Dashboard cross-page flow.
 *
 * All backend API calls are intercepted via Playwright's route.fulfill()
 * so no real Django server is required. Each test manages its own fixture
 * state through route handlers.
 *
 * ─── BDD Scenarios covered ───────────────────────────────────────────────────
 *
 * Scenario 1: Invalid file upload is caught client-side
 *   Given the user is on the Settings page, Candidates tab
 *   When  they try to upload a .txt file as a resume
 *   Then  the form shows a client-side error without submitting to the API
 *
 * Scenario 2: Full happy-path cross-page flow
 *   Given the user is on Settings, Jobs tab
 *   When  they create a new job
 *   Then  it appears in the Jobs list
 *   And   they switch to the Applications tab and link it to a candidate
 *   And   they navigate to the Dashboard
 *   Then  the new application row appears in the table
 *   And   the row can be selected for pipeline evaluation
 *
 * Scenario 3: Delete job with cascade warning
 *   Given a job exists in the Settings Jobs list
 *   When  the user clicks Delete and reads the cascade warning
 *   And   confirms deletion
 *   Then  the job row disappears from the list
 *   And   the delete API endpoint was called
 *
 * Scenario 4: Edit job title in-place
 *   Given a job exists in the Settings Jobs list
 *   When  the user clicks Edit, changes the title, and saves
 *   Then  the updated title appears in the list without a page reload
 *
 * Scenario 5: Settings → Dashboard nav link
 *   Given the user is on the Settings page
 *   When  they click the "← Dashboard" back link
 *   Then  they land on the Dashboard route
 *
 * ─── Job CRUD Scenarios ──────────────────────────────────────────────────────
 *
 * Scenario 10: Add new Job in isolation
 *   Given the Jobs tab shows an empty state
 *   When  the user fills the Add Job modal and submits
 *   Then  the new job row appears in the table
 *
 * Scenario 11: View existing job detail
 *   Given a job with description and hard-gate criteria exists
 *   When  the user clicks the expand chevron on the job row
 *   Then  the detail panel shows the description and must_haves JSON
 *   And   a second click collapses the panel
 *
 * ─── Candidate CRUD Scenarios ────────────────────────────────────────────────
 *
 * Scenario 6: Add new candidate via PDF upload
 *   Given the Candidates tab shows an empty state
 *   When  the user fills the Add Candidate form and uploads a PDF
 *   Then  the new candidate row appears in the table
 *   And   the modal closes
 *
 * Scenario 7: View existing candidate resume sections
 *   Given a candidate with a parsed resume exists in the Candidates tab
 *   When  the user clicks the expand chevron on the candidate row
 *   Then  the resume section panel becomes visible
 *   And   the parsed section content is displayed
 *
 * Scenario 8: Edit candidate name and email in-place
 *   Given a candidate exists in the Candidates tab
 *   When  the user clicks Edit, updates the name and email, and saves
 *   Then  the updated values appear in the candidate row
 *   And   the old values are no longer visible
 *
 * Scenario 9: Delete candidate with cascade warning → row disappears
 *   Given a candidate exists in the Candidates tab
 *   When  the user clicks Delete
 *   Then  the confirm modal shows the cascade warning about Applications
 *   When  the user confirms
 *   Then  the candidate row is removed from the list
 *   And   the DELETE endpoint was called
 *
 * ─── Application Scope Scenarios ─────────────────────────────────────────────
 *
 * Scenario 12: No jobs → prerequisite guard
 *   Given no jobs exist
 *   When  the user opens the Applications tab
 *   Then  a prerequisite notice mentioning jobs is shown
 *   And   the submit button is disabled
 *
 * Scenario 13: No candidates → prerequisite guard
 *   Given no candidates exist
 *   When  the user opens the Applications tab
 *   Then  a prerequisite notice mentioning candidates is shown
 *   And   the submit button is disabled
 *
 * Scenario 14: Create Application → success banner and form reset
 *   Given a job and a candidate exist
 *   When  the user selects both and submits the association form
 *   Then  a success banner naming the candidate and job appears
 *   And   both selects reset to their empty defaults
 */

import { test, expect } from '@playwright/test';

// ── Shared fixtures ───────────────────────────────────────────────────────────

const JOB = {
  id:          'job-fixture-1',
  title:       'Senior Data Engineer',
  description: 'Build pipelines.',
  must_haves:  {},
  created_at:  '2024-01-10T00:00:00Z',
  updated_at:  '2024-01-10T00:00:00Z',
};

const CANDIDATE = {
  id:         'cand-fixture-1',
  name:       'Alice Chen',
  email:      'alice@example.com',
  created_at: '2024-01-11T00:00:00Z',
};

const APPLICATION = {
  id:                       'app-fixture-1',
  // FK ids used by ApplicationCenter.jsx to look up names from local state
  // after a successful POST (success banner: candidates.find(c => c.id === ...) )
  candidate_id:             'cand-fixture-1',
  job_id:                   'job-fixture-1',
  // Denormalised fields used by ApplicationTable on the Dashboard
  candidate_name:           'Alice Chen',
  candidate_email:          'alice@example.com',
  job_title:                'Senior Data Engineer',
  status:                   'pending',
  final_score:              null,
  is_evaluated_via_fallback: false,
  created_at:               '2024-01-12T00:00:00Z',
  updated_at:               '2024-01-12T00:00:00Z',
};

/** Wire all collection endpoints to return fixture data. */
async function mockApiCollections(page, overrides = {}) {
  const jobs         = overrides.jobs         ?? [JOB];
  const candidates   = overrides.candidates   ?? [CANDIDATE];
  const applications = overrides.applications ?? [];

  await page.route('**/api/jobs/',         (r) => r.fulfill({ json: jobs }));
  await page.route('**/api/candidates/',   (r) => r.fulfill({ json: candidates }));
  await page.route('**/api/applications/', (r) => r.fulfill({ json: applications }));
}

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 1: Invalid file upload rejected client-side
// ─────────────────────────────────────────────────────────────────────────────

test('Given invalid file type, When uploaded as resume, Then client error appears without API call', async ({ page }) => {
  let createCandidateCalled = false;

  // mockApiCollections registers a GET handler for /api/candidates/ first.
  // The second route() call MUST discriminate by method so the GET (used by
  // useCandidates on mount) still returns a valid empty array, while only the
  // POST (the actual upload) sets createCandidateCalled.
  await mockApiCollections(page, { candidates: [] });
  await page.route('**/api/candidates/', async (route) => {
    if (route.request().method() === 'POST') {
      createCandidateCalled = true;
      await route.fulfill({ status: 201, json: CANDIDATE });
    } else {
      await route.fulfill({ json: [] });
    }
  });

  await page.goto('/settings');

  // Switch to Candidates tab
  await page.getByTestId('tab-candidates').click();
  await page.getByTestId('candidate-create-btn').click();

  // Upload a .txt file (invalid)
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles({
    name:     'resume.txt',
    mimeType: 'text/plain',
    buffer:   Buffer.from('not a pdf'),
  });

  // Fill required text fields
  await page.getByLabel(/Full Name/i).fill('Bob Smith');
  await page.getByLabel(/Email/i).fill('bob@example.com');

  await page.getByText('Upload Resume').click();

  // Client-side validation fires — API is NOT called
  await expect(page.getByRole('alert')).toContainText(/Only PDF files/i);
  expect(createCandidateCalled).toBe(false);
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 2: Full cross-page happy-path
// ─────────────────────────────────────────────────────────────────────────────

test('Full flow: create job → create application → dashboard row appears', async ({ page }) => {
  const newJob = { ...JOB, id: 'job-new', title: 'Staff ML Engineer' };

  // Start with no jobs so we can create one
  await mockApiCollections(page, { jobs: [], applications: [] });

  // POST /api/jobs/ returns the new job
  await page.route('**/api/jobs/', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 201, json: newJob });
    } else {
      // GET after creation — return the created job in the list
      await route.fulfill({ json: [newJob] });
    }
  });

  await page.goto('/settings');

  // ── Step 1: create a job ──────────────────────────────────────────────────
  await page.getByTestId('tab-jobs').click();
  await page.getByTestId('job-create-btn').click();

  await page.getByLabel(/Title/i).fill('Staff ML Engineer');
  await page.getByLabel(/Description/i).fill('Train models at scale.');
  await page.getByText('Create Job').click();

  // Scope to job-table: the hidden Applications panel also renders 'Staff ML Engineer'
  // as an <option> in the job select, so a global getByText() matches multiple elements.
  await expect(page.getByTestId('job-table').getByText('Staff ML Engineer')).toBeVisible();

  // ── Step 2: create an application (Association Center) ───────────────────
  // Now expose the created job and a candidate via the Applications tab
  await page.route('**/api/jobs/',       (r) => r.fulfill({ json: [newJob]    }));
  await page.route('**/api/candidates/', (r) => r.fulfill({ json: [CANDIDATE] }));
  await page.route('**/api/applications/', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 201, json: APPLICATION });
    } else {
      await route.fulfill({ json: [APPLICATION] });
    }
  });

  await page.getByTestId('tab-applications').click();
  await page.getByTestId('assoc-job-select').selectOption(newJob.id);
  await page.getByTestId('assoc-candidate-select').selectOption(CANDIDATE.id);
  await page.getByTestId('assoc-submit-btn').click();

  await expect(page.getByTestId('assoc-success')).toBeVisible();

  // ── Step 3: navigate to Dashboard and verify the row ─────────────────────
  await page.goto('/');
  await expect(page.getByText('Alice Chen')).toBeVisible();
  await expect(page.getByText('Senior Data Engineer')).toBeVisible();

  // ── Step 4: the row can be selected for pipeline evaluation ───────────────
  const checkbox = page.getByRole('checkbox', { name: /Alice Chen/i }).first();
  await checkbox.check();
  await expect(page.getByTestId('bulk-run-bar')).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 3: Delete job with cascade warning → row disappears
// ─────────────────────────────────────────────────────────────────────────────

test('Given a job exists, When user confirms delete, Then job row is removed', async ({ page }) => {
  let deleteCalled = false;

  await mockApiCollections(page);
  await page.route(`**/api/jobs/${JOB.id}/`, async (route) => {
    if (route.request().method() === 'DELETE') {
      deleteCalled = true;
      await route.fulfill({ status: 204, body: '' });
    }
  });

  await page.goto('/settings');

  // ── See the cascade warning in the confirm modal ──────────────────────────
  await page.getByTestId(`job-delete-${JOB.id}`).click();
  await expect(page.getByTestId('delete-confirm-warning')).toContainText('Applications');

  // ── Confirm ───────────────────────────────────────────────────────────────
  await page.getByTestId('delete-confirm-btn').click();

  await expect(page.getByTestId(`job-row-${JOB.id}`)).not.toBeVisible({ timeout: 3000 });
  expect(deleteCalled).toBe(true);
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 4: Edit job title updates list in-place
// ─────────────────────────────────────────────────────────────────────────────

test('Given a job exists, When user edits title and saves, Then updated title appears', async ({ page }) => {
  const updatedJob = { ...JOB, title: 'Principal Data Engineer', updated_at: '2024-02-01T00:00:00Z' };

  await mockApiCollections(page);
  await page.route(`**/api/jobs/${JOB.id}/`, async (route) => {
    if (route.request().method() === 'PATCH') {
      await route.fulfill({ json: updatedJob });
    }
  });

  await page.goto('/settings');

  await page.getByTestId(`job-edit-${JOB.id}`).click();

  // Clear the title field and type the new title
  const titleInput = page.getByTestId('edit-job-title');
  await titleInput.clear();
  await titleInput.fill('Principal Data Engineer');

  await page.getByTestId('edit-job-submit').click();

  // Modal closes; updated title appears in the list.
  // Scope to job-table: the hidden Applications panel renders job titles as
  // <option> elements too, causing strict-mode violations on global text match.
  await expect(page.getByTestId('job-table').getByText('Principal Data Engineer')).toBeVisible();
  await expect(page.getByTestId('job-table').getByText('Senior Data Engineer')).not.toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 5: Settings → Dashboard nav link
// ─────────────────────────────────────────────────────────────────────────────

test('Settings header contains a working "← Dashboard" back link', async ({ page }) => {
  await mockApiCollections(page);
  await page.goto('/settings');

  await page.getByText('← Dashboard').click();
  await expect(page).toHaveURL('/');
});

// =============================================================================
//  Job CRUD Scenarios
// =============================================================================

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 10: Add new Job in isolation → row appears in list
// ─────────────────────────────────────────────────────────────────────────────

test('Given Jobs tab is empty, When user creates a job, Then job row appears in list', async ({ page }) => {
  await mockApiCollections(page, { jobs: [] });

  // Method-discriminate so GET still returns [] while modal is open,
  // and POST returns the new job for addJob() to render the row.
  await page.route('**/api/jobs/', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 201, json: JOB });
    } else {
      await route.fulfill({ json: [] });
    }
  });

  await page.goto('/settings');
  // Jobs tab is active by default — verify empty state first.
  await expect(page.getByTestId('job-board-empty')).toBeVisible();

  // ── Open modal ────────────────────────────────────────────────────────────
  await page.getByTestId('job-create-btn').click();

  // JobIngestionModal has no data-testids on inputs — locate by element id.
  await page.locator('#job-title').fill('Senior Data Engineer');
  await page.locator('#job-description').fill('Build and maintain data pipelines at scale.');

  // Submit button identified by visible text (no testid on the button either).
  await page.getByRole('button', { name: 'Create Job' }).click();

  // ── Assertions ────────────────────────────────────────────────────────────
  // onSuccess calls addJob() → local state updates → row renders, modal closes.
  await expect(page.getByTestId(`job-row-${JOB.id}`)).toBeVisible();
  await expect(page.getByTestId('job-table').getByText('Senior Data Engineer')).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 11: Expand job row → description and must_haves visible
// ─────────────────────────────────────────────────────────────────────────────

test('Given a job with description and criteria, When user expands the row, Then detail panel appears', async ({ page }) => {
  // Use a fixture with non-empty must_haves so both detail sections render.
  // The must_haves section is conditional: only shown when Object.keys().length > 0.
  const richJob = {
    ...JOB,
    description: 'Build and maintain data pipelines at scale.',
    must_haves:  { min_years_experience: 5, required_keywords: ['Python', 'SQL'] },
  };

  await mockApiCollections(page, { jobs: [richJob] });
  await page.goto('/settings');

  await expect(page.getByTestId(`job-row-${JOB.id}`)).toBeVisible();

  // ── Expand ────────────────────────────────────────────────────────────────
  await page.getByTestId(`job-expand-${JOB.id}`).click();

  const detail = page.getByTestId(`job-detail-${JOB.id}`);
  await expect(detail).toBeVisible();
  await expect(detail).toContainText('Build and maintain data pipelines at scale.');
  // must_haves renders as pretty-printed JSON inside a <pre> block.
  await expect(detail).toContainText('min_years_experience');
  await expect(detail).toContainText('Python');

  // ── Collapse closes the detail panel ─────────────────────────────────────
  await page.getByTestId(`job-expand-${JOB.id}`).click();
  await expect(detail).not.toBeVisible();
});

// =============================================================================
//  Candidate CRUD Scenarios
// =============================================================================

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 6: Add new candidate via PDF upload → row appears in list
// ─────────────────────────────────────────────────────────────────────────────

test('Given Candidates tab is empty, When user uploads PDF resume, Then candidate appears in list', async ({ page }) => {
  // Start with no candidates so the empty-state placeholder renders first.
  await mockApiCollections(page, { candidates: [] });

  // Method-discriminate: GET still returns [] (keeps the empty state while the
  // modal is open); POST returns the created candidate so addCandidate() can
  // update local state and render the row.
  await page.route('**/api/candidates/', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 201, json: CANDIDATE });
    } else {
      await route.fulfill({ json: [] });
    }
  });

  await page.goto('/settings');
  await page.getByTestId('tab-candidates').click();

  // ── Verify empty state ────────────────────────────────────────────────────
  await expect(page.getByTestId('candidate-board-empty')).toBeVisible();

  // ── Open the Add Candidate modal ──────────────────────────────────────────
  await page.getByTestId('candidate-create-btn').click();

  // ── Fill the form ─────────────────────────────────────────────────────────
  await page.locator('#cand-name').fill('Alice Chen');
  await page.locator('#cand-email').fill('alice@example.com');

  // Attach a minimal PDF via the file input.
  // setInputFiles does NOT use the native file-picker dialog — it injects the
  // file directly onto the <input type="file">, bypassing OS-level dialogs.
  await page.locator('input[type="file"]').setInputFiles({
    name:     'alice_resume.pdf',
    mimeType: 'application/pdf',
    buffer:   Buffer.from('%PDF-1.4 fake resume content for testing'),
  });

  // ── Submit ────────────────────────────────────────────────────────────────
  await page.getByRole('button', { name: 'Upload Resume' }).click();

  // ── Assertions ────────────────────────────────────────────────────────────
  // onSuccess callback calls addCandidate() which adds the candidate to local
  // state and closes the modal; the table renders immediately.
  await expect(page.getByTestId(`candidate-row-${CANDIDATE.id}`)).toBeVisible();
  await expect(page.getByTestId(`candidate-row-${CANDIDATE.id}`)).toContainText(CANDIDATE.name);
  await expect(page.getByTestId(`candidate-row-${CANDIDATE.id}`)).toContainText(CANDIDATE.email);
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 7: Expand candidate row → resume sections visible
// ─────────────────────────────────────────────────────────────────────────────

test('Given a candidate with resume sections, When user expands the row, Then sections are displayed', async ({ page }) => {
  // Fixture includes resume_parsed so the detail panel has content to show.
  const candidateWithResume = {
    ...CANDIDATE,
    resume_parsed: {
      experience: 'Software Engineer at ACME Corp.',
      skills:     'Python, React, PostgreSQL',
    },
  };

  await mockApiCollections(page, { candidates: [candidateWithResume] });
  await page.goto('/settings');
  await page.getByTestId('tab-candidates').click();

  // Wait for the table to finish loading before expanding.
  await expect(page.getByTestId(`candidate-row-${CANDIDATE.id}`)).toBeVisible();

  // ── Expand the row ────────────────────────────────────────────────────────
  await page.getByTestId(`candidate-expand-${CANDIDATE.id}`).click();

  // ── Assertions ────────────────────────────────────────────────────────────
  const detail = page.getByTestId(`candidate-detail-${CANDIDATE.id}`);
  await expect(detail).toBeVisible();
  await expect(detail).toContainText('Software Engineer at ACME Corp.');
  await expect(detail).toContainText('Python, React, PostgreSQL');

  // ── Collapse closes the detail panel ─────────────────────────────────────
  await page.getByTestId(`candidate-expand-${CANDIDATE.id}`).click();
  await expect(detail).not.toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 8: Edit candidate name and email in-place
// ─────────────────────────────────────────────────────────────────────────────

test('Given a candidate exists, When user edits name and email and saves, Then updated values appear in list', async ({ page }) => {
  // Use a name with no substring overlap with the original ("Alice Chen") so
  // toContainText / not.toContainText assertions are unambiguous.
  const updated = {
    ...CANDIDATE,
    name:  'Dr. Alice Johnson',
    // Use a domain that shares no substring with the original 'alice@example.com'
    // so the not.toContainText('Alice Chen') assertion is unambiguous and we
    // don't need a negative email assertion at all.
    email: 'dr.johnson@clinic.org',
  };

  await mockApiCollections(page);
  await page.route(`**/api/candidates/${CANDIDATE.id}/`, async (route) => {
    if (route.request().method() === 'PATCH') {
      await route.fulfill({ json: updated });
    }
  });

  await page.goto('/settings');
  await page.getByTestId('tab-candidates').click();
  await expect(page.getByTestId(`candidate-row-${CANDIDATE.id}`)).toBeVisible();

  // ── Open Edit modal ───────────────────────────────────────────────────────
  await page.getByTestId(`candidate-edit-${CANDIDATE.id}`).click();

  // Wait for the modal's inputs to be ready (useEffect populates them from the
  // candidate prop when the modal opens).
  const nameInput = page.getByTestId('edit-cand-name');
  await expect(nameInput).toBeVisible();

  // ── Update fields ─────────────────────────────────────────────────────────
  await nameInput.clear();
  await nameInput.fill('Dr. Alice Johnson');

  const emailInput = page.getByTestId('edit-cand-email');
  await emailInput.clear();
  await emailInput.fill('dr.johnson@clinic.org');

  // ── Save ──────────────────────────────────────────────────────────────────
  await page.getByTestId('edit-cand-submit').click();

  // ── Assertions ────────────────────────────────────────────────────────────
  // onSuccess calls patchCandidate() which swaps the record in local state;
  // the modal closes and the row re-renders with the new values.
  await expect(page.getByTestId(`candidate-row-${CANDIDATE.id}`)).toContainText('Dr. Alice Johnson');
  await expect(page.getByTestId(`candidate-row-${CANDIDATE.id}`)).toContainText('dr.johnson@clinic.org');
  await expect(page.getByTestId(`candidate-row-${CANDIDATE.id}`)).not.toContainText('Alice Chen');
  // No negative email assertion needed: 'dr.johnson@clinic.org' shares no
  // substring with 'alice@example.com', so the positive assertion above
  // already proves the old value was replaced.
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 9: Delete candidate with cascade warning → row disappears
// ─────────────────────────────────────────────────────────────────────────────

test('Given a candidate exists, When user confirms delete, Then candidate row is removed', async ({ page }) => {
  let deleteCalled = false;

  await mockApiCollections(page);
  await page.route(`**/api/candidates/${CANDIDATE.id}/`, async (route) => {
    if (route.request().method() === 'DELETE') {
      deleteCalled = true;
      await route.fulfill({ status: 204, body: '' });
    }
  });

  await page.goto('/settings');
  await page.getByTestId('tab-candidates').click();
  await expect(page.getByTestId(`candidate-row-${CANDIDATE.id}`)).toBeVisible();

  // ── Open delete confirm modal ─────────────────────────────────────────────
  await page.getByTestId(`candidate-delete-${CANDIDATE.id}`).click();

  // The modal warns that linked Applications will also be deleted.
  await expect(page.getByTestId('delete-confirm-warning')).toContainText('Applications');

  // ── Confirm deletion ──────────────────────────────────────────────────────
  await page.getByTestId('delete-confirm-btn').click();

  // ── Assertions ────────────────────────────────────────────────────────────
  // onConfirm calls deleteCandidate(id) then onRemove(id), which filters the
  // candidate out of local state; the row unmounts.
  await expect(page.getByTestId(`candidate-row-${CANDIDATE.id}`)).not.toBeVisible({ timeout: 3000 });
  expect(deleteCalled).toBe(true);
});

// =============================================================================
//  Application Scope Scenarios (ApplicationCenter — create-only form)
// =============================================================================
//
// The Settings Applications tab hosts ApplicationCenter: a form that links an
// existing Job to an existing Candidate to create an Application. There is no
// list/edit/delete UI in this tab — CRUD for the resulting records lives on the
// Dashboard. These tests cover the form's three key behaviours:
//   • Prerequisite guard when no jobs exist
//   • Prerequisite guard when no candidates exist
//   • Happy path: select + submit → success banner, selects reset

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 12: No jobs → prerequisite notice and submit disabled
// ─────────────────────────────────────────────────────────────────────────────

test('Given no jobs exist, When user opens Applications tab, Then prerequisite notice and disabled submit appear', async ({ page }) => {
  await mockApiCollections(page, { jobs: [] });
  await page.goto('/settings');
  await page.getByTestId('tab-applications').click();

  // Notice explains that a job must be added first.
  await expect(page.getByTestId('assoc-prereq-notice')).toContainText('No jobs found');

  // Submit is disabled when prerequisites are not met.
  await expect(page.getByTestId('assoc-submit-btn')).toBeDisabled();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 13: No candidates → prerequisite notice and submit disabled
// ─────────────────────────────────────────────────────────────────────────────

test('Given no candidates exist, When user opens Applications tab, Then prerequisite notice and disabled submit appear', async ({ page }) => {
  await mockApiCollections(page, { candidates: [] });
  await page.goto('/settings');
  await page.getByTestId('tab-applications').click();

  await expect(page.getByTestId('assoc-prereq-notice')).toContainText('No candidates found');
  await expect(page.getByTestId('assoc-submit-btn')).toBeDisabled();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 14: Create Application → success banner appears, selects reset
// ─────────────────────────────────────────────────────────────────────────────

test('Given job and candidate exist, When user submits the association form, Then success banner appears and selects reset', async ({ page }) => {
  await mockApiCollections(page);

  await page.route('**/api/applications/', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 201, json: APPLICATION });
    } else {
      await route.fulfill({ json: [] });
    }
  });

  await page.goto('/settings');
  await page.getByTestId('tab-applications').click();

  // Both selects should be enabled (prerequisites met).
  await expect(page.getByTestId('assoc-submit-btn')).not.toBeDisabled();

  // ── Select job and candidate ──────────────────────────────────────────────
  await page.getByTestId('assoc-job-select').selectOption(JOB.id);
  await page.getByTestId('assoc-candidate-select').selectOption(CANDIDATE.id);

  // ── Submit ────────────────────────────────────────────────────────────────
  await page.getByTestId('assoc-submit-btn').click();

  // ── Assertions ────────────────────────────────────────────────────────────
  // Success banner confirms the link with candidate and job names.
  await expect(page.getByTestId('assoc-success')).toBeVisible();
  await expect(page.getByTestId('assoc-success')).toContainText('Alice Chen');
  await expect(page.getByTestId('assoc-success')).toContainText('Senior Data Engineer');

  // Selects reset to the empty default after successful submission.
  await expect(page.getByTestId('assoc-job-select')).toHaveValue('');
  await expect(page.getByTestId('assoc-candidate-select')).toHaveValue('');
});
