/**
 * E2E specification: Word (.doc / .docx) resume ingestion via the Candidates
 * tab on the Settings page — M8.
 *
 * All backend API calls are intercepted via Playwright's route.fulfill().
 * No real Django server or LibreOffice binary is required: the browser only
 * ever sees the POST /api/candidates/ response, so these specs assert the
 * client-side contract (which file types are offered up, accepted, and
 * rejected) plus how the UI reacts to the server's conversion outcome.
 *
 * ─── BDD Scenarios covered ───────────────────────────────────────────────────
 *
 * Scenario 1: Upload a .docx resume → candidate row appears
 * Scenario 2: Upload a legacy .doc resume → candidate row appears
 * Scenario 3: Server-side conversion failure (400) → inline field error shown,
 *             no row added, modal stays open for retry
 * Scenario 4: Existing PDF upload path is unaffected by the Word feature
 * Scenario 5: File picker advertises .pdf, .doc, and .docx to the OS
 */

import { test, expect } from '@playwright/test';

// ── Fixtures ──────────────────────────────────────────────────────────────

const CANDIDATE_DOCX = {
  id:         'cand-word-docx-1',
  name:       'Priya Patel',
  email:      'priya.docx@example.com',
  created_at: '2026-06-01T00:00:00Z',
};

const CANDIDATE_DOC = {
  id:         'cand-word-doc-1',
  name:       'Marcus Webb',
  email:      'marcus.doc@example.com',
  created_at: '2026-06-01T00:00:00Z',
};

const CANDIDATE_PDF = {
  id:         'cand-pdf-1',
  name:       'Sofia Ruiz',
  email:      'sofia.pdf@example.com',
  created_at: '2026-06-01T00:00:00Z',
};

/** Wire the collection endpoints the Settings page loads on mount. */
async function mockBaseRoutes(page, { candidates = [] } = {}) {
  await page.route('**/api/jobs/', (r) => r.fulfill({ json: [] }));
  await page.route('**/api/applications/', (r) => r.fulfill({ json: [] }));
  await page.route('**/api/dashboard/stats/', (r) =>
    r.fulfill({
      json: {
        totals: {},
        application_status_distribution: [],
        job_execution_funnel: [],
        llm_resilience: { time_series: [] },
      },
    })
  );
  await page.route('**/api/candidates/', async (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ json: candidates });
    }
    return route.continue();
  });
}

async function openAddCandidateModal(page) {
  await page.goto('/settings');
  await page.getByTestId('tab-candidates').click();
  await page.getByTestId('candidate-create-btn').click();
}

async function fillNameAndEmail(page, name, email) {
  await page.locator('#cand-name').fill(name);
  await page.locator('#cand-email').fill(email);
}

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 1: Upload a .docx resume → candidate row appears
// ─────────────────────────────────────────────────────────────────────────────

test('Given a .docx resume, When uploaded, Then the candidate row appears', async ({ page }) => {
  await mockBaseRoutes(page);

  let postBody = null;
  await page.route('**/api/candidates/', async (route) => {
    if (route.request().method() === 'POST') {
      postBody = route.request().postData();
      return route.fulfill({ status: 201, json: CANDIDATE_DOCX });
    }
    return route.fulfill({ json: [] });
  });

  await openAddCandidateModal(page);
  await fillNameAndEmail(page, CANDIDATE_DOCX.name, CANDIDATE_DOCX.email);

  await page.locator('input[type="file"]').setInputFiles({
    name:     'priya_resume.docx',
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    buffer:   Buffer.from('PK\x03\x04 fake docx bytes for e2e'),
  });

  await page.getByRole('button', { name: 'Upload Resume' }).click();

  await expect(page.getByTestId(`candidate-row-${CANDIDATE_DOCX.id}`)).toBeVisible();
  await expect(page.getByTestId(`candidate-row-${CANDIDATE_DOCX.id}`)).toContainText(CANDIDATE_DOCX.name);
  expect(postBody).not.toBeNull();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 2: Upload a legacy .doc resume → candidate row appears
// ─────────────────────────────────────────────────────────────────────────────

test('Given a legacy .doc resume, When uploaded, Then the candidate row appears', async ({ page }) => {
  await mockBaseRoutes(page);

  await page.route('**/api/candidates/', async (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({ status: 201, json: CANDIDATE_DOC });
    }
    return route.fulfill({ json: [] });
  });

  await openAddCandidateModal(page);
  await fillNameAndEmail(page, CANDIDATE_DOC.name, CANDIDATE_DOC.email);

  await page.locator('input[type="file"]').setInputFiles({
    name:     'marcus_resume.doc',
    mimeType: 'application/msword',
    buffer:   Buffer.from('\xd0\xcf\x11\xe0 fake legacy doc bytes for e2e'),
  });

  await page.getByRole('button', { name: 'Upload Resume' }).click();

  await expect(page.getByTestId(`candidate-row-${CANDIDATE_DOC.id}`)).toBeVisible();
  await expect(page.getByTestId(`candidate-row-${CANDIDATE_DOC.id}`)).toContainText(CANDIDATE_DOC.email);
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 3: Server-side conversion failure → inline error, no row, modal stays open
// ─────────────────────────────────────────────────────────────────────────────

test('Given a .docx that LibreOffice cannot convert, When uploaded, Then an inline error is shown and no row is added', async ({ page }) => {
  await mockBaseRoutes(page);

  await page.route('**/api/candidates/', async (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 400,
        json: { resume_pdf: ['Conversion timed out after 30s.'] },
      });
    }
    return route.fulfill({ json: [] });
  });

  await openAddCandidateModal(page);
  await fillNameAndEmail(page, 'Dana Lee', 'dana.fail@example.com');

  await page.locator('input[type="file"]').setInputFiles({
    name:     'dana_resume.docx',
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    buffer:   Buffer.from('PK\x03\x04 corrupt docx bytes'),
  });

  await page.getByRole('button', { name: 'Upload Resume' }).click();

  await expect(page.getByText(/conversion timed out after 30s/i)).toBeVisible();
  // Modal stays open for retry — the file input is still present.
  await expect(page.locator('input[type="file"]')).toBeVisible();
  await expect(page.getByTestId('candidate-board-empty')).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 4: Existing PDF upload path is unaffected
// ─────────────────────────────────────────────────────────────────────────────

test('Given a PDF resume, When uploaded, Then the candidate row still appears as before', async ({ page }) => {
  await mockBaseRoutes(page);

  await page.route('**/api/candidates/', async (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({ status: 201, json: CANDIDATE_PDF });
    }
    return route.fulfill({ json: [] });
  });

  await openAddCandidateModal(page);
  await fillNameAndEmail(page, CANDIDATE_PDF.name, CANDIDATE_PDF.email);

  await page.locator('input[type="file"]').setInputFiles({
    name:     'sofia_resume.pdf',
    mimeType: 'application/pdf',
    buffer:   Buffer.from('%PDF-1.4 fake resume content for e2e'),
  });

  await page.getByRole('button', { name: 'Upload Resume' }).click();

  await expect(page.getByTestId(`candidate-row-${CANDIDATE_PDF.id}`)).toBeVisible();
  await expect(page.getByTestId(`candidate-row-${CANDIDATE_PDF.id}`)).toContainText(CANDIDATE_PDF.name);
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 5: File picker advertises PDF and Word extensions
// ─────────────────────────────────────────────────────────────────────────────

test('The resume file input accepts PDF, .doc, and .docx', async ({ page }) => {
  await mockBaseRoutes(page);
  await openAddCandidateModal(page);

  const accept = await page.locator('input[type="file"]').getAttribute('accept');
  expect(accept).toContain('.pdf');
  expect(accept).toContain('.doc');
  expect(accept).toContain('.docx');
});
