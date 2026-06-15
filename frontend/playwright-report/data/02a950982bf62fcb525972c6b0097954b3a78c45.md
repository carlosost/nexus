# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: settings_flow.spec.js >> Given a job exists, When user edits title and saves, Then updated title appears
- Location: e2e/settings_flow.spec.js:293:1

# Error details

```
Error: locator.click: Test ended.
Call log:
  - waiting for getByTestId('job-edit-job-fixture-1')

```

# Test source

```ts
  205 |   await mockApiCollections(page, { jobs: [], applications: [] });
  206 | 
  207 |   // POST /api/jobs/ returns the new job
  208 |   await page.route('**/api/jobs/', async (route) => {
  209 |     if (route.request().method() === 'POST') {
  210 |       await route.fulfill({ status: 201, json: newJob });
  211 |     } else {
  212 |       // GET after creation — return the created job in the list
  213 |       await route.fulfill({ json: [newJob] });
  214 |     }
  215 |   });
  216 | 
  217 |   await page.goto('/settings');
  218 | 
  219 |   // ── Step 1: create a job ──────────────────────────────────────────────────
  220 |   await page.getByTestId('tab-jobs').click();
  221 |   await page.getByTestId('job-create-btn').click();
  222 | 
  223 |   await page.getByLabel(/Title/i).fill('Staff ML Engineer');
  224 |   await page.getByLabel(/Description/i).fill('Train models at scale.');
  225 |   await page.getByText('Create Job').click();
  226 | 
  227 |   // Scope to job-table: the hidden Applications panel also renders 'Staff ML Engineer'
  228 |   // as an <option> in the job select, so a global getByText() matches multiple elements.
  229 |   await expect(page.getByTestId('job-table').getByText('Staff ML Engineer')).toBeVisible();
  230 | 
  231 |   // ── Step 2: create an application (Association Center) ───────────────────
  232 |   // Now expose the created job and a candidate via the Applications tab
  233 |   await page.route('**/api/jobs/',       (r) => r.fulfill({ json: [newJob]    }));
  234 |   await page.route('**/api/candidates/', (r) => r.fulfill({ json: [CANDIDATE] }));
  235 |   await page.route('**/api/applications/', async (route) => {
  236 |     if (route.request().method() === 'POST') {
  237 |       await route.fulfill({ status: 201, json: APPLICATION });
  238 |     } else {
  239 |       await route.fulfill({ json: [APPLICATION] });
  240 |     }
  241 |   });
  242 | 
  243 |   await page.getByTestId('tab-applications').click();
  244 |   await page.getByTestId('assoc-job-select').selectOption(newJob.id);
  245 |   await page.getByTestId('assoc-candidate-select').selectOption(CANDIDATE.id);
  246 |   await page.getByTestId('assoc-submit-btn').click();
  247 | 
  248 |   await expect(page.getByTestId('assoc-success')).toBeVisible();
  249 | 
  250 |   // ── Step 3: navigate to Dashboard and verify the row ─────────────────────
  251 |   await page.goto('/');
  252 |   await expect(page.getByText('Alice Chen')).toBeVisible();
  253 |   await expect(page.getByText('Senior Data Engineer')).toBeVisible();
  254 | 
  255 |   // ── Step 4: the row can be selected for pipeline evaluation ───────────────
  256 |   const checkbox = page.getByRole('checkbox', { name: /Alice Chen/i }).first();
  257 |   await checkbox.check();
  258 |   await expect(page.getByTestId('bulk-run-bar')).toBeVisible();
  259 | });
  260 | 
  261 | // ─────────────────────────────────────────────────────────────────────────────
  262 | // Scenario 3: Delete job with cascade warning → row disappears
  263 | // ─────────────────────────────────────────────────────────────────────────────
  264 | 
  265 | test('Given a job exists, When user confirms delete, Then job row is removed', async ({ page }) => {
  266 |   let deleteCalled = false;
  267 | 
  268 |   await mockApiCollections(page);
  269 |   await page.route(`**/api/jobs/${JOB.id}/`, async (route) => {
  270 |     if (route.request().method() === 'DELETE') {
  271 |       deleteCalled = true;
  272 |       await route.fulfill({ status: 204, body: '' });
  273 |     }
  274 |   });
  275 | 
  276 |   await page.goto('/settings');
  277 | 
  278 |   // ── See the cascade warning in the confirm modal ──────────────────────────
  279 |   await page.getByTestId(`job-delete-${JOB.id}`).click();
  280 |   await expect(page.getByTestId('delete-confirm-warning')).toContainText('Applications');
  281 | 
  282 |   // ── Confirm ───────────────────────────────────────────────────────────────
  283 |   await page.getByTestId('delete-confirm-btn').click();
  284 | 
  285 |   await expect(page.getByTestId(`job-row-${JOB.id}`)).not.toBeVisible({ timeout: 3000 });
  286 |   expect(deleteCalled).toBe(true);
  287 | });
  288 | 
  289 | // ─────────────────────────────────────────────────────────────────────────────
  290 | // Scenario 4: Edit job title updates list in-place
  291 | // ─────────────────────────────────────────────────────────────────────────────
  292 | 
  293 | test('Given a job exists, When user edits title and saves, Then updated title appears', async ({ page }) => {
  294 |   const updatedJob = { ...JOB, title: 'Principal Data Engineer', updated_at: '2024-02-01T00:00:00Z' };
  295 | 
  296 |   await mockApiCollections(page);
  297 |   await page.route(`**/api/jobs/${JOB.id}/`, async (route) => {
  298 |     if (route.request().method() === 'PATCH') {
  299 |       await route.fulfill({ json: updatedJob });
  300 |     }
  301 |   });
  302 | 
  303 |   await page.goto('/settings');
  304 | 
> 305 |   await page.getByTestId(`job-edit-${JOB.id}`).click();
      |                                                ^ Error: locator.click: Test ended.
  306 | 
  307 |   // Clear the title field and type the new title
  308 |   const titleInput = page.getByTestId('edit-job-title');
  309 |   await titleInput.clear();
  310 |   await titleInput.fill('Principal Data Engineer');
  311 | 
  312 |   await page.getByTestId('edit-job-submit').click();
  313 | 
  314 |   // Modal closes; updated title appears in the list.
  315 |   // Scope to job-table: the hidden Applications panel renders job titles as
  316 |   // <option> elements too, causing strict-mode violations on global text match.
  317 |   await expect(page.getByTestId('job-table').getByText('Principal Data Engineer')).toBeVisible();
  318 |   await expect(page.getByTestId('job-table').getByText('Senior Data Engineer')).not.toBeVisible();
  319 | });
  320 | 
  321 | // ─────────────────────────────────────────────────────────────────────────────
  322 | // Scenario 5: Settings → Dashboard nav link
  323 | // ─────────────────────────────────────────────────────────────────────────────
  324 | 
  325 | test('Settings header contains a working "← Dashboard" back link', async ({ page }) => {
  326 |   await mockApiCollections(page);
  327 |   await page.goto('/settings');
  328 | 
  329 |   await page.getByText('← Dashboard').click();
  330 |   await expect(page).toHaveURL('/');
  331 | });
  332 | 
  333 | // =============================================================================
  334 | //  Job CRUD Scenarios
  335 | // =============================================================================
  336 | 
  337 | // ─────────────────────────────────────────────────────────────────────────────
  338 | // Scenario 10: Add new Job in isolation → row appears in list
  339 | // ─────────────────────────────────────────────────────────────────────────────
  340 | 
  341 | test('Given Jobs tab is empty, When user creates a job, Then job row appears in list', async ({ page }) => {
  342 |   await mockApiCollections(page, { jobs: [] });
  343 | 
  344 |   // Method-discriminate so GET still returns [] while modal is open,
  345 |   // and POST returns the new job for addJob() to render the row.
  346 |   await page.route('**/api/jobs/', async (route) => {
  347 |     if (route.request().method() === 'POST') {
  348 |       await route.fulfill({ status: 201, json: JOB });
  349 |     } else {
  350 |       await route.fulfill({ json: [] });
  351 |     }
  352 |   });
  353 | 
  354 |   await page.goto('/settings');
  355 |   // Jobs tab is active by default — verify empty state first.
  356 |   await expect(page.getByTestId('job-board-empty')).toBeVisible();
  357 | 
  358 |   // ── Open modal ────────────────────────────────────────────────────────────
  359 |   await page.getByTestId('job-create-btn').click();
  360 | 
  361 |   // JobIngestionModal has no data-testids on inputs — locate by element id.
  362 |   await page.locator('#job-title').fill('Senior Data Engineer');
  363 |   await page.locator('#job-description').fill('Build and maintain data pipelines at scale.');
  364 | 
  365 |   // Submit button identified by visible text (no testid on the button either).
  366 |   await page.getByRole('button', { name: 'Create Job' }).click();
  367 | 
  368 |   // ── Assertions ────────────────────────────────────────────────────────────
  369 |   // onSuccess calls addJob() → local state updates → row renders, modal closes.
  370 |   await expect(page.getByTestId(`job-row-${JOB.id}`)).toBeVisible();
  371 |   await expect(page.getByTestId('job-table').getByText('Senior Data Engineer')).toBeVisible();
  372 | });
  373 | 
  374 | // ─────────────────────────────────────────────────────────────────────────────
  375 | // Scenario 11: Expand job row → description and must_haves visible
  376 | // ─────────────────────────────────────────────────────────────────────────────
  377 | 
  378 | test('Given a job with description and criteria, When user expands the row, Then detail panel appears', async ({ page }) => {
  379 |   // Use a fixture with non-empty must_haves so both detail sections render.
  380 |   // The must_haves section is conditional: only shown when Object.keys().length > 0.
  381 |   const richJob = {
  382 |     ...JOB,
  383 |     description: 'Build and maintain data pipelines at scale.',
  384 |     must_haves:  { min_years_experience: 5, required_keywords: ['Python', 'SQL'] },
  385 |   };
  386 | 
  387 |   await mockApiCollections(page, { jobs: [richJob] });
  388 |   await page.goto('/settings');
  389 | 
  390 |   await expect(page.getByTestId(`job-row-${JOB.id}`)).toBeVisible();
  391 | 
  392 |   // ── Expand ────────────────────────────────────────────────────────────────
  393 |   await page.getByTestId(`job-expand-${JOB.id}`).click();
  394 | 
  395 |   const detail = page.getByTestId(`job-detail-${JOB.id}`);
  396 |   await expect(detail).toBeVisible();
  397 |   await expect(detail).toContainText('Build and maintain data pipelines at scale.');
  398 |   // must_haves renders as pretty-printed JSON inside a <pre> block.
  399 |   await expect(detail).toContainText('min_years_experience');
  400 |   await expect(detail).toContainText('Python');
  401 | 
  402 |   // ── Collapse closes the detail panel ─────────────────────────────────────
  403 |   await page.getByTestId(`job-expand-${JOB.id}`).click();
  404 |   await expect(detail).not.toBeVisible();
  405 | });
```