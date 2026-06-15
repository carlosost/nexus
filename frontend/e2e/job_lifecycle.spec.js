/**
 * E2E specification: Job domain — Markdown ingestion, CRUD, and embedding lifecycle.
 *
 * All backend API calls are intercepted via Playwright's route.fulfill().
 * No real Django server or embedding service required.
 */

import { test, expect } from '@playwright/test';

// ── Fixtures ──────────────────────────────────────────────────────────────

const VALID_MARKDOWN = `# Senior Backend Engineer

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
`;

const CREATED_JOB = {
  id:         'job-uuid-e2e-001',
  title:      'Senior Backend Engineer',
  created_at: '2024-06-01T10:00:00Z',
};

const EXISTING_JOBS = [
  { id: 'job-uuid-001', title: 'Principal Data Engineer', created_at: '2024-05-01T00:00:00Z' },
];

async function mockBaseRoutes(page, { jobs = EXISTING_JOBS } = {}) {
  await page.route('**/api/jobs/', (r) => {
    if (r.request().method() === 'GET') return r.fulfill({ json: jobs });
    return r.continue();
  });
  await page.route('**/api/candidates/', (r) => r.fulfill({ json: [] }));
  await page.route('**/api/applications/', (r) => r.fulfill({ json: [] }));
  await page.route('**/api/dashboard/stats/', (r) =>
    r.fulfill({ json: { totals: {}, application_status_distribution: [], job_execution_funnel: [], llm_resilience: { time_series: [] } } })
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 1: Happy path — submit valid Markdown, new row appears in list
// ─────────────────────────────────────────────────────────────────────────────

test('Given valid Markdown, When submitted, Then job row appears in the Settings list', async ({ page }) => {
  await mockBaseRoutes(page);

  const updatedJobs = [...EXISTING_JOBS, CREATED_JOB];
  let postHandled = false;

  await page.route('**/api/jobs/markdown/', (r) => {
    postHandled = true;
    return r.fulfill({ status: 201, json: CREATED_JOB });
  });
  await page.route('**/api/jobs/', async (r) => {
    if (r.request().method() === 'GET') {
      return r.fulfill({ json: postHandled ? updatedJobs : EXISTING_JOBS });
    }
    return r.continue();
  });

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /add job/i }).click();

  const textarea = page.getByRole('textbox', { name: /job specification/i });
  await expect(textarea).toBeVisible();
  await textarea.fill(VALID_MARKDOWN);

  await page.getByRole('button', { name: /create job/i }).click();

  await expect(page.getByRole('textbox', { name: /job specification/i })).not.toBeVisible({ timeout: 4000 });
  await expect(page.getByText('Senior Backend Engineer')).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 2: Parser 422 error — inline field error rendered
// ─────────────────────────────────────────────────────────────────────────────

test('Given Markdown with no H1, When submitted, Then inline "title" error is shown', async ({ page }) => {
  await mockBaseRoutes(page);
  await page.route('**/api/jobs/markdown/', (r) =>
    r.fulfill({ status: 422, json: { title: ['Markdown must begin with an H1 heading.'] } })
  );

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /add job/i }).click();
  await page.getByRole('textbox', { name: /job specification/i }).fill('## No H1 here');
  await page.getByRole('button', { name: /create job/i }).click();

  await expect(page.getByText(/must begin with an h1/i)).toBeVisible();
  await expect(page.getByRole('textbox', { name: /job specification/i })).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 3: Server 500 — generic error banner with retry button
// ─────────────────────────────────────────────────────────────────────────────

test('Given a 500 error, When submitted, Then error banner with Retry is shown', async ({ page }) => {
  let callCount = 0;

  await mockBaseRoutes(page);
  await page.route('**/api/jobs/markdown/', (r) => {
    callCount++;
    if (callCount === 1) return r.fulfill({ status: 500, json: { detail: 'Internal server error' } });
    return r.fulfill({ status: 201, json: CREATED_JOB });
  });

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /add job/i }).click();
  await page.getByRole('textbox', { name: /job specification/i }).fill(VALID_MARKDOWN);
  await page.getByRole('button', { name: /create job/i }).click();

  const errorBanner = page.getByRole('alert');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner.getByRole('button', { name: /retry/i })).toBeVisible();

  await errorBanner.getByRole('button', { name: /retry/i }).click();
  await expect(errorBanner).not.toBeVisible({ timeout: 4000 });
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 4: Duplicate title (409)
// ─────────────────────────────────────────────────────────────────────────────

test('Given a duplicate title, When submitted, Then "already exists" message is shown', async ({ page }) => {
  await mockBaseRoutes(page);
  await page.route('**/api/jobs/markdown/', (r) =>
    r.fulfill({ status: 409, json: { detail: 'A job with this title already exists.' } })
  );

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /add job/i }).click();
  await page.getByRole('textbox', { name: /job specification/i }).fill(VALID_MARKDOWN);
  await page.getByRole('button', { name: /create job/i }).click();

  await expect(page.getByText(/already exists/i)).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 5: Job detail expand — description and must_haves rendered
// ─────────────────────────────────────────────────────────────────────────────

test('Given a job with full detail, When expanded, Then description and must_haves are visible', async ({ page }) => {
  const jobWithDetail = {
    ...EXISTING_JOBS[0],
    description:      'We need a strong backend engineer.',
    requirements_raw: { required_skills: ['Python', 'Django'] },
    must_haves:       { min_experience: { type: 'years_experience', minimum_years: 5 } },
  };
  await mockBaseRoutes(page, { jobs: [jobWithDetail] });
  await page.route(`**/api/jobs/${jobWithDetail.id}/`, (r) =>
    r.fulfill({ json: jobWithDetail })
  );

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /expand/i }).first().click();

  await expect(page.getByText(/strong backend engineer/i)).toBeVisible();
  await expect(page.getByText(/years_experience/i)).toBeVisible();
  await expect(page.getByText(/minimum_years/i)).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 6: Edit job title inline
// ─────────────────────────────────────────────────────────────────────────────

test('Given an existing job, When title is edited and saved, Then updated title appears in list', async ({ page }) => {
  const updatedJob = { ...EXISTING_JOBS[0], title: 'Staff Data Engineer' };

  await mockBaseRoutes(page);
  await page.route(`**/api/jobs/${EXISTING_JOBS[0].id}/`, async (r) => {
    if (r.request().method() === 'PATCH') return r.fulfill({ json: updatedJob });
    return r.fulfill({ json: EXISTING_JOBS[0] });
  });

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /edit/i }).first().click();

  const titleInput = page.getByRole('textbox', { name: /title/i });
  await titleInput.fill('Staff Data Engineer');
  await page.getByRole('button', { name: /save/i }).click();

  await expect(page.getByText('Staff Data Engineer')).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 7: Delete job — cascade warning, confirmation, row removed
// ─────────────────────────────────────────────────────────────────────────────

test('Given a job, When user confirms delete, Then job row is removed from list', async ({ page }) => {
  await mockBaseRoutes(page);
  await page.route(`**/api/jobs/${EXISTING_JOBS[0].id}/`, (r) => {
    if (r.request().method() === 'DELETE') return r.fulfill({ status: 204, body: '' });
    return r.continue();
  });

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /delete/i }).first().click();

  const modal = page.getByRole('dialog');
  await expect(modal).toBeVisible();
  await expect(modal.getByText(/also delete/i)).toBeVisible();

  await modal.getByRole('button', { name: /confirm/i }).click();

  await expect(page.getByText('Principal Data Engineer')).not.toBeVisible({ timeout: 3000 });
});

test('Given a job, When user cancels delete, Then job row remains', async ({ page }) => {
  await mockBaseRoutes(page);

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /delete/i }).first().click();
  await page.getByRole('button', { name: /cancel/i }).click();

  await expect(page.getByText('Principal Data Engineer')).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 8: Loading spinner visible during submission
// ─────────────────────────────────────────────────────────────────────────────

test('Given a slow API, Then loading spinner is shown while request is in flight', async ({ page }) => {
  let resolvePost;
  const postPromise = new Promise((res) => { resolvePost = res; });

  await mockBaseRoutes(page);
  await page.route('**/api/jobs/markdown/', async (r) => {
    await postPromise;
    return r.fulfill({ status: 201, json: CREATED_JOB });
  });

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /add job/i }).click();
  await page.getByRole('textbox', { name: /job specification/i }).fill(VALID_MARKDOWN);
  await page.getByRole('button', { name: /create job/i }).click();

  await expect(page.getByTestId('loading-spinner')).toBeVisible();

  resolvePost();

  await expect(page.getByTestId('loading-spinner')).not.toBeVisible({ timeout: 4000 });
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 9: Embedding latency — modal closes immediately on 201
// ─────────────────────────────────────────────────────────────────────────────

test('Modal closes on 201 regardless of embedding pipeline latency', async ({ page }) => {
  await mockBaseRoutes(page);
  await page.route('**/api/jobs/markdown/', (r) =>
    r.fulfill({ status: 201, json: CREATED_JOB })
  );

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /add job/i }).click();
  await page.getByRole('textbox', { name: /job specification/i }).fill(VALID_MARKDOWN);
  await page.getByRole('button', { name: /create job/i }).click();

  await expect(
    page.getByRole('textbox', { name: /job specification/i })
  ).not.toBeVisible({ timeout: 2000 });
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 10: Job detail panel displays all field sections
// ─────────────────────────────────────────────────────────────────────────────

test('Job detail panel displays title, requirements, and must_haves in distinct sections', async ({ page }) => {
  const job = {
    id:               'job-detail-001',
    title:            'Senior Backend Engineer',
    description:      'Lead backend development of our data platform.',
    requirements_raw: {
      required_skills:           ['Python', 'Django', 'PostgreSQL', 'REST APIs'],
      preferred_skills:          ['Redis', 'Docker', 'Kubernetes'],
      minimum_experience_years:  5,
    },
    must_haves: {
      min_experience:   { type: 'years_experience',  minimum_years: 5 },
      python_required:  { type: 'keyword_presence',  keywords: ['Python'],  sections: ['skills', 'experience'] },
      django_required:  { type: 'keyword_presence',  keywords: ['Django'],  sections: ['skills', 'experience'] },
    },
    created_at: '2024-06-01T00:00:00Z',
  };
  await mockBaseRoutes(page, { jobs: [job] });
  await page.route(`**/api/jobs/${job.id}/`, (r) => r.fulfill({ json: job }));

  await page.goto('/settings');
  await page.getByTestId('tab-jobs').click();
  await page.getByRole('button', { name: /expand/i }).click();

  await expect(page.getByText(/required skills/i)).toBeVisible();
  await expect(page.getByText(/preferred skills/i)).toBeVisible();
  await expect(page.getByText(/hard gate criteria/i)).toBeVisible();

  await expect(page.getByText('Python')).toBeVisible();
  await expect(page.getByText('Django')).toBeVisible();
  await expect(page.getByText('PostgreSQL')).toBeVisible();

  await expect(page.getByText(/years_experience/i)).toBeVisible();
  await expect(page.getByText(/keyword_presence/i)).toBeVisible();
});
