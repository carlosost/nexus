# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: settings_flow.spec.js >> Full flow: create job → create application → dashboard row appears
- Location: e2e/settings_flow.spec.js:201:1

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.fill: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByLabel(/Title/i)

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]:
      - link "Back to Dashboard" [ref=e6] [cursor=pointer]:
        - /url: /
        - text: ← Dashboard
      - generic [ref=e7]: "|"
      - generic [ref=e8]: Settings
  - tablist "Settings sections" [ref=e9]:
    - tab "Jobs" [selected] [ref=e10] [cursor=pointer]
    - tab "Candidates" [ref=e11] [cursor=pointer]
    - tab "Applications" [ref=e12] [cursor=pointer]
  - tabpanel "Jobs" [ref=e13]:
    - generic [ref=e14]:
      - generic [ref=e15]:
        - heading "Jobs" [level=2] [ref=e16]
        - button "+ Add Job" [ref=e17] [cursor=pointer]
      - table [ref=e18]:
        - rowgroup [ref=e19]:
          - row "Title Created Updated Actions" [ref=e20]:
            - columnheader "Title" [ref=e21]
            - columnheader "Created" [ref=e22]
            - columnheader "Updated" [ref=e23]
            - columnheader "Actions" [ref=e24]
        - rowgroup [ref=e25]:
          - row "▸ Staff ML Engineer 1/9/2024 1/9/2024 Delete" [ref=e26]:
            - cell "▸ Staff ML Engineer" [ref=e27]:
              - button "▸ Staff ML Engineer" [ref=e28] [cursor=pointer]:
                - generic [ref=e29]: ▸
                - text: Staff ML Engineer
            - cell "1/9/2024" [ref=e30]
            - cell "1/9/2024" [ref=e31]
            - cell "Delete" [ref=e32]:
              - button "Delete" [ref=e33] [cursor=pointer]
      - dialog "Add New Job" [active] [ref=e34]:
        - generic [ref=e35]:
          - heading "Add New Job" [level=2] [ref=e36]
          - button "Close modal" [ref=e37] [cursor=pointer]: ✕
        - generic [ref=e39]:
          - paragraph [ref=e40]:
            - text: Paste the full job description in
            - strong [ref=e41]: Markdown format
            - text: . The title, description, requirements, and hard-gate criteria are extracted automatically from the document structure.
          - group [ref=e42]:
            - generic "Show expected format" [ref=e43]
          - generic [ref=e44]:
            - generic [ref=e45]: Markdown Job Description *
            - textbox "Markdown Job Description" [ref=e46]:
              - /placeholder: "# Job Title\n\n## Description\n…"
          - generic [ref=e47]:
            - button "Cancel" [ref=e48] [cursor=pointer]
            - button "Create Job" [ref=e49] [cursor=pointer]
```

# Test source

```ts
  123 | const APPLICATION = {
  124 |   id:                       'app-fixture-1',
  125 |   // FK ids used by ApplicationCenter.jsx to look up names from local state
  126 |   // after a successful POST (success banner: candidates.find(c => c.id === ...) )
  127 |   candidate_id:             'cand-fixture-1',
  128 |   job_id:                   'job-fixture-1',
  129 |   // Denormalised fields used by ApplicationTable on the Dashboard
  130 |   candidate_name:           'Alice Chen',
  131 |   candidate_email:          'alice@example.com',
  132 |   job_title:                'Senior Data Engineer',
  133 |   status:                   'pending',
  134 |   final_score:              null,
  135 |   is_evaluated_via_fallback: false,
  136 |   created_at:               '2024-01-12T00:00:00Z',
  137 |   updated_at:               '2024-01-12T00:00:00Z',
  138 | };
  139 | 
  140 | /** Wire all collection endpoints to return fixture data. */
  141 | async function mockApiCollections(page, overrides = {}) {
  142 |   const jobs         = overrides.jobs         ?? [JOB];
  143 |   const candidates   = overrides.candidates   ?? [CANDIDATE];
  144 |   const applications = overrides.applications ?? [];
  145 | 
  146 |   await page.route('**/api/jobs/',         (r) => r.fulfill({ json: jobs }));
  147 |   await page.route('**/api/candidates/',   (r) => r.fulfill({ json: candidates }));
  148 |   await page.route('**/api/applications/', (r) => r.fulfill({ json: applications }));
  149 | }
  150 | 
  151 | // ─────────────────────────────────────────────────────────────────────────────
  152 | // Scenario 1: Invalid file upload rejected client-side
  153 | // ─────────────────────────────────────────────────────────────────────────────
  154 | 
  155 | test('Given invalid file type, When uploaded as resume, Then client error appears without API call', async ({ page }) => {
  156 |   let createCandidateCalled = false;
  157 | 
  158 |   // mockApiCollections registers a GET handler for /api/candidates/ first.
  159 |   // The second route() call MUST discriminate by method so the GET (used by
  160 |   // useCandidates on mount) still returns a valid empty array, while only the
  161 |   // POST (the actual upload) sets createCandidateCalled.
  162 |   await mockApiCollections(page, { candidates: [] });
  163 |   await page.route('**/api/candidates/', async (route) => {
  164 |     if (route.request().method() === 'POST') {
  165 |       createCandidateCalled = true;
  166 |       await route.fulfill({ status: 201, json: CANDIDATE });
  167 |     } else {
  168 |       await route.fulfill({ json: [] });
  169 |     }
  170 |   });
  171 | 
  172 |   await page.goto('/settings');
  173 | 
  174 |   // Switch to Candidates tab
  175 |   await page.getByTestId('tab-candidates').click();
  176 |   await page.getByTestId('candidate-create-btn').click();
  177 | 
  178 |   // Upload a .txt file (invalid)
  179 |   const fileInput = page.locator('input[type="file"]');
  180 |   await fileInput.setInputFiles({
  181 |     name:     'resume.txt',
  182 |     mimeType: 'text/plain',
  183 |     buffer:   Buffer.from('not a pdf'),
  184 |   });
  185 | 
  186 |   // Fill required text fields
  187 |   await page.getByLabel(/Full Name/i).fill('Bob Smith');
  188 |   await page.getByLabel(/Email/i).fill('bob@example.com');
  189 | 
  190 |   await page.getByText('Upload Resume').click();
  191 | 
  192 |   // Client-side validation fires — API is NOT called
  193 |   await expect(page.getByRole('alert')).toContainText(/Only PDF files/i);
  194 |   expect(createCandidateCalled).toBe(false);
  195 | });
  196 | 
  197 | // ─────────────────────────────────────────────────────────────────────────────
  198 | // Scenario 2: Full cross-page happy-path
  199 | // ─────────────────────────────────────────────────────────────────────────────
  200 | 
  201 | test('Full flow: create job → create application → dashboard row appears', async ({ page }) => {
  202 |   const newJob = { ...JOB, id: 'job-new', title: 'Staff ML Engineer' };
  203 | 
  204 |   // Start with no jobs so we can create one
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
> 223 |   await page.getByLabel(/Title/i).fill('Staff ML Engineer');
      |                                   ^ Error: locator.fill: Test timeout of 30000ms exceeded.
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
  305 |   await page.getByTestId(`job-edit-${JOB.id}`).click();
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
```