# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: job_lifecycle.spec.js >> Given Markdown with no H1, When submitted, Then inline "title" error is shown
- Location: e2e/job_lifecycle.spec.js:102:1

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.fill: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByRole('textbox', { name: /job specification/i })

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
          - row "▸ Principal Data Engineer 4/30/2024 — Delete" [ref=e26]:
            - cell "▸ Principal Data Engineer" [ref=e27]:
              - button "▸ Principal Data Engineer" [ref=e28] [cursor=pointer]:
                - generic [ref=e29]: ▸
                - text: Principal Data Engineer
            - cell "4/30/2024" [ref=e30]
            - cell "—" [ref=e31]
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
  11  | 
  12  | const VALID_MARKDOWN = `# Senior Backend Engineer
  13  | 
  14  | ## Description
  15  | We are looking for a Senior Backend Engineer with deep Python and Django
  16  | experience to lead backend development of our data platform.
  17  | 
  18  | ## Requirements
  19  | ### Required Skills
  20  | - Python
  21  | - Django
  22  | - PostgreSQL
  23  | - REST APIs
  24  | ### Preferred Skills
  25  | - Redis
  26  | - Docker
  27  | - Kubernetes
  28  | ### Minimum Experience
  29  | 5 years
  30  | 
  31  | ## Must Haves
  32  | ### min_experience
  33  | type: years_experience
  34  | minimum_years: 5
  35  | ### python_required
  36  | type: keyword_presence
  37  | keywords: Python
  38  | sections: skills, experience
  39  | `;
  40  | 
  41  | const CREATED_JOB = {
  42  |   id:         'job-uuid-e2e-001',
  43  |   title:      'Senior Backend Engineer',
  44  |   created_at: '2024-06-01T10:00:00Z',
  45  | };
  46  | 
  47  | const EXISTING_JOBS = [
  48  |   { id: 'job-uuid-001', title: 'Principal Data Engineer', created_at: '2024-05-01T00:00:00Z' },
  49  | ];
  50  | 
  51  | async function mockBaseRoutes(page, { jobs = EXISTING_JOBS } = {}) {
  52  |   await page.route('**/api/jobs/', (r) => {
  53  |     if (r.request().method() === 'GET') return r.fulfill({ json: jobs });
  54  |     return r.continue();
  55  |   });
  56  |   await page.route('**/api/candidates/', (r) => r.fulfill({ json: [] }));
  57  |   await page.route('**/api/applications/', (r) => r.fulfill({ json: [] }));
  58  |   await page.route('**/api/dashboard/stats/', (r) =>
  59  |     r.fulfill({ json: { totals: {}, application_status_distribution: [], job_execution_funnel: [], llm_resilience: { time_series: [] } } })
  60  |   );
  61  | }
  62  | 
  63  | // ─────────────────────────────────────────────────────────────────────────────
  64  | // Scenario 1: Happy path — submit valid Markdown, new row appears in list
  65  | // ─────────────────────────────────────────────────────────────────────────────
  66  | 
  67  | test('Given valid Markdown, When submitted, Then job row appears in the Settings list', async ({ page }) => {
  68  |   await mockBaseRoutes(page);
  69  | 
  70  |   const updatedJobs = [...EXISTING_JOBS, CREATED_JOB];
  71  |   let postHandled = false;
  72  | 
  73  |   await page.route('**/api/jobs/markdown/', (r) => {
  74  |     postHandled = true;
  75  |     return r.fulfill({ status: 201, json: CREATED_JOB });
  76  |   });
  77  |   await page.route('**/api/jobs/', async (r) => {
  78  |     if (r.request().method() === 'GET') {
  79  |       return r.fulfill({ json: postHandled ? updatedJobs : EXISTING_JOBS });
  80  |     }
  81  |     return r.continue();
  82  |   });
  83  | 
  84  |   await page.goto('/settings');
  85  |   await page.getByTestId('tab-jobs').click();
  86  |   await page.getByRole('button', { name: /add job/i }).click();
  87  | 
  88  |   const textarea = page.getByRole('textbox', { name: /job specification/i });
  89  |   await expect(textarea).toBeVisible();
  90  |   await textarea.fill(VALID_MARKDOWN);
  91  | 
  92  |   await page.getByRole('button', { name: /create job/i }).click();
  93  | 
  94  |   await expect(page.getByRole('textbox', { name: /job specification/i })).not.toBeVisible({ timeout: 4000 });
  95  |   await expect(page.getByText('Senior Backend Engineer')).toBeVisible();
  96  | });
  97  | 
  98  | // ─────────────────────────────────────────────────────────────────────────────
  99  | // Scenario 2: Parser 422 error — inline field error rendered
  100 | // ─────────────────────────────────────────────────────────────────────────────
  101 | 
  102 | test('Given Markdown with no H1, When submitted, Then inline "title" error is shown', async ({ page }) => {
  103 |   await mockBaseRoutes(page);
  104 |   await page.route('**/api/jobs/markdown/', (r) =>
  105 |     r.fulfill({ status: 422, json: { title: ['Markdown must begin with an H1 heading.'] } })
  106 |   );
  107 | 
  108 |   await page.goto('/settings');
  109 |   await page.getByTestId('tab-jobs').click();
  110 |   await page.getByRole('button', { name: /add job/i }).click();
> 111 |   await page.getByRole('textbox', { name: /job specification/i }).fill('## No H1 here');
      |                                                                   ^ Error: locator.fill: Test timeout of 30000ms exceeded.
  112 |   await page.getByRole('button', { name: /create job/i }).click();
  113 | 
  114 |   await expect(page.getByText(/must begin with an h1/i)).toBeVisible();
  115 |   await expect(page.getByRole('textbox', { name: /job specification/i })).toBeVisible();
  116 | });
  117 | 
  118 | // ─────────────────────────────────────────────────────────────────────────────
  119 | // Scenario 3: Server 500 — generic error banner with retry button
  120 | // ─────────────────────────────────────────────────────────────────────────────
  121 | 
  122 | test('Given a 500 error, When submitted, Then error banner with Retry is shown', async ({ page }) => {
  123 |   let callCount = 0;
  124 | 
  125 |   await mockBaseRoutes(page);
  126 |   await page.route('**/api/jobs/markdown/', (r) => {
  127 |     callCount++;
  128 |     if (callCount === 1) return r.fulfill({ status: 500, json: { detail: 'Internal server error' } });
  129 |     return r.fulfill({ status: 201, json: CREATED_JOB });
  130 |   });
  131 | 
  132 |   await page.goto('/settings');
  133 |   await page.getByTestId('tab-jobs').click();
  134 |   await page.getByRole('button', { name: /add job/i }).click();
  135 |   await page.getByRole('textbox', { name: /job specification/i }).fill(VALID_MARKDOWN);
  136 |   await page.getByRole('button', { name: /create job/i }).click();
  137 | 
  138 |   const errorBanner = page.getByRole('alert');
  139 |   await expect(errorBanner).toBeVisible();
  140 |   await expect(errorBanner.getByRole('button', { name: /retry/i })).toBeVisible();
  141 | 
  142 |   await errorBanner.getByRole('button', { name: /retry/i }).click();
  143 |   await expect(errorBanner).not.toBeVisible({ timeout: 4000 });
  144 | });
  145 | 
  146 | // ─────────────────────────────────────────────────────────────────────────────
  147 | // Scenario 4: Duplicate title (409)
  148 | // ─────────────────────────────────────────────────────────────────────────────
  149 | 
  150 | test('Given a duplicate title, When submitted, Then "already exists" message is shown', async ({ page }) => {
  151 |   await mockBaseRoutes(page);
  152 |   await page.route('**/api/jobs/markdown/', (r) =>
  153 |     r.fulfill({ status: 409, json: { detail: 'A job with this title already exists.' } })
  154 |   );
  155 | 
  156 |   await page.goto('/settings');
  157 |   await page.getByTestId('tab-jobs').click();
  158 |   await page.getByRole('button', { name: /add job/i }).click();
  159 |   await page.getByRole('textbox', { name: /job specification/i }).fill(VALID_MARKDOWN);
  160 |   await page.getByRole('button', { name: /create job/i }).click();
  161 | 
  162 |   await expect(page.getByText(/already exists/i)).toBeVisible();
  163 | });
  164 | 
  165 | // ─────────────────────────────────────────────────────────────────────────────
  166 | // Scenario 5: Job detail expand — description and must_haves rendered
  167 | // ─────────────────────────────────────────────────────────────────────────────
  168 | 
  169 | test('Given a job with full detail, When expanded, Then description and must_haves are visible', async ({ page }) => {
  170 |   const jobWithDetail = {
  171 |     ...EXISTING_JOBS[0],
  172 |     description:      'We need a strong backend engineer.',
  173 |     requirements_raw: { required_skills: ['Python', 'Django'] },
  174 |     must_haves:       { min_experience: { type: 'years_experience', minimum_years: 5 } },
  175 |   };
  176 |   await mockBaseRoutes(page, { jobs: [jobWithDetail] });
  177 |   await page.route(`**/api/jobs/${jobWithDetail.id}/`, (r) =>
  178 |     r.fulfill({ json: jobWithDetail })
  179 |   );
  180 | 
  181 |   await page.goto('/settings');
  182 |   await page.getByTestId('tab-jobs').click();
  183 |   await page.getByRole('button', { name: /expand/i }).first().click();
  184 | 
  185 |   await expect(page.getByText(/strong backend engineer/i)).toBeVisible();
  186 |   await expect(page.getByText(/years_experience/i)).toBeVisible();
  187 |   await expect(page.getByText(/minimum_years/i)).toBeVisible();
  188 | });
  189 | 
  190 | // ─────────────────────────────────────────────────────────────────────────────
  191 | // Scenario 6: Edit job title inline
  192 | // ─────────────────────────────────────────────────────────────────────────────
  193 | 
  194 | test('Given an existing job, When title is edited and saved, Then updated title appears in list', async ({ page }) => {
  195 |   const updatedJob = { ...EXISTING_JOBS[0], title: 'Staff Data Engineer' };
  196 | 
  197 |   await mockBaseRoutes(page);
  198 |   await page.route(`**/api/jobs/${EXISTING_JOBS[0].id}/`, async (r) => {
  199 |     if (r.request().method() === 'PATCH') return r.fulfill({ json: updatedJob });
  200 |     return r.fulfill({ json: EXISTING_JOBS[0] });
  201 |   });
  202 | 
  203 |   await page.goto('/settings');
  204 |   await page.getByTestId('tab-jobs').click();
  205 |   await page.getByRole('button', { name: /edit/i }).first().click();
  206 | 
  207 |   const titleInput = page.getByRole('textbox', { name: /title/i });
  208 |   await titleInput.fill('Staff Data Engineer');
  209 |   await page.getByRole('button', { name: /save/i }).click();
  210 | 
  211 |   await expect(page.getByText('Staff Data Engineer')).toBeVisible();
```