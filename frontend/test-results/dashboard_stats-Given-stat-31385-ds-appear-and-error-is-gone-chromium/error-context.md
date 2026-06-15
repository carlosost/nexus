# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: dashboard_stats.spec.js >> Given stats fails then succeeds, When user clicks Retry, Then cards appear and error is gone
- Location: e2e/dashboard_stats.spec.js:169:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('.stats-error')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('.stats-error')

```

```yaml
- banner:
  - text: ⬡ Elvex Nexus Candidate Screening
  - navigation:
    - link "⚙ Settings":
      - /url: /settings
- text: Total Applications 99 Active In Pipeline 18 pending / gate-passed / gate-unknown Workspace Users 9 LLM Success Rate 94.2% primary backend calls Application Status No applications yet Job Execution Last 24 hours No activity in the last 24 h LLM Resilience Primary vs fallback — last 7 days No LLM calls recorded in the last 7 days
- main:
  - heading "Applications" [level=2]
  - paragraph: No applications yet.
  - paragraph: Add a Job and a Candidate, then create an Application to get started.
```

# Test source

```ts
  84  |     llm_resilience: { time_series: timeSeries },
  85  |   };
  86  | }
  87  | 
  88  | /** Wire all baseline API routes for the Dashboard page. */
  89  | async function mockDashboardApis(page, {
  90  |   stats           = makeStats(),
  91  |   statsStatus     = 200,
  92  |   applications    = APPLICATIONS,
  93  | } = {}) {
  94  |   await page.route('**/api/applications/', (r) => r.fulfill({ json: applications }));
  95  | 
  96  |   if (statsStatus !== 200) {
  97  |     await page.route('**/api/dashboard/stats/', (r) =>
  98  |       r.fulfill({ status: statsStatus, json: { detail: 'Internal server error' } })
  99  |     );
  100 |   } else {
  101 |     await page.route('**/api/dashboard/stats/', (r) => r.fulfill({ json: stats }));
  102 |   }
  103 | }
  104 | 
  105 | // ─────────────────────────────────────────────────────────────────────────────
  106 | // Scenario 1: Metric cards display backend values
  107 | // ─────────────────────────────────────────────────────────────────────────────
  108 | 
  109 | test('Given stats API resolves, When dashboard loads, Then 4 metric cards show API values', async ({ page }) => {
  110 |   await mockDashboardApis(page, {
  111 |     stats: makeStats({
  112 |       applications:     142,
  113 |       active_jobs:      18,
  114 |       workspace_users:  9,
  115 |       llm_success_rate: 94.2,
  116 |     }),
  117 |   });
  118 | 
  119 |   await page.goto('/');
  120 | 
  121 |   // All 4 metric-card containers are visible
  122 |   const cards = page.locator('.metric-card');
  123 |   await expect(cards).toHaveCount(4);
  124 | 
  125 |   // Values match what the API returned
  126 |   await expect(page.locator('.metric-card__value').nth(0)).toContainText('142');
  127 |   await expect(page.locator('.metric-card__value').nth(1)).toContainText('18');
  128 |   await expect(page.locator('.metric-card__value').nth(2)).toContainText('9');
  129 |   await expect(page.locator('.metric-card__value').nth(3)).toContainText('94.2%');
  130 | });
  131 | 
  132 | test('Given large application count, Then value is formatted with locale separators', async ({ page }) => {
  133 |   await mockDashboardApis(page, {
  134 |     stats: makeStats({ applications: 1500 }),
  135 |   });
  136 |   await page.goto('/');
  137 |   // fmt() uses toLocaleString() — "1,500" in en-US locale
  138 |   await expect(page.locator('.metric-card__value').nth(0)).toContainText('1');
  139 | });
  140 | 
  141 | // ─────────────────────────────────────────────────────────────────────────────
  142 | // Scenario 2: Stats API error — error banner shown, table still renders
  143 | // ─────────────────────────────────────────────────────────────────────────────
  144 | 
  145 | test('Given stats API returns 500, When dashboard loads, Then error banner is visible', async ({ page }) => {
  146 |   await mockDashboardApis(page, { statsStatus: 500 });
  147 |   await page.goto('/');
  148 |   await expect(page.locator('.stats-error')).toBeVisible();
  149 | });
  150 | 
  151 | test('Given stats API fails, Then ApplicationTable is still rendered', async ({ page }) => {
  152 |   await mockDashboardApis(page, { statsStatus: 500 });
  153 |   await page.goto('/');
  154 |   // The error in stats section must not block the application table
  155 |   await expect(page.locator('.application-table, [data-testid="app-table"]').first()).toBeVisible();
  156 | });
  157 | 
  158 | test('Given stats API fails, Then error banner contains retry button', async ({ page }) => {
  159 |   await mockDashboardApis(page, { statsStatus: 500 });
  160 |   await page.goto('/');
  161 |   const banner = page.locator('.stats-error');
  162 |   await expect(banner.getByRole('button', { name: /retry/i })).toBeVisible();
  163 | });
  164 | 
  165 | // ─────────────────────────────────────────────────────────────────────────────
  166 | // Scenario 3: Retry button re-calls the stats API
  167 | // ─────────────────────────────────────────────────────────────────────────────
  168 | 
  169 | test('Given stats fails then succeeds, When user clicks Retry, Then cards appear and error is gone', async ({ page }) => {
  170 |   let callCount = 0;
  171 | 
  172 |   await page.route('**/api/applications/', (r) => r.fulfill({ json: [] }));
  173 |   await page.route('**/api/dashboard/stats/', (r) => {
  174 |     callCount++;
  175 |     if (callCount === 1) {
  176 |       return r.fulfill({ status: 500, json: { detail: 'Temporary error' } });
  177 |     }
  178 |     return r.fulfill({ json: makeStats({ applications: 99 }) });
  179 |   });
  180 | 
  181 |   await page.goto('/');
  182 | 
  183 |   // Error banner present after first (failed) call
> 184 |   await expect(page.locator('.stats-error')).toBeVisible();
      |                                              ^ Error: expect(locator).toBeVisible() failed
  185 | 
  186 |   // Click Retry
  187 |   await page.locator('.stats-error').getByRole('button', { name: /retry/i }).click();
  188 | 
  189 |   // Error banner disappears, metric card with value 99 appears
  190 |   await expect(page.locator('.stats-error')).not.toBeVisible({ timeout: 4000 });
  191 |   await expect(page.locator('.metric-card__value').first()).toContainText('99');
  192 | });
  193 | 
  194 | // ─────────────────────────────────────────────────────────────────────────────
  195 | // Scenario 4: Empty data — chart empty states
  196 | // ─────────────────────────────────────────────────────────────────────────────
  197 | 
  198 | test('Given all stats are zero, Then status chart shows empty state', async ({ page }) => {
  199 |   const emptyStats = makeStats({
  200 |     applications: 0,
  201 |     statusDist: [
  202 |       { status: 'pending', label: 'Pending', count: 0 },
  203 |     ],
  204 |     funnelData: [
  205 |       { status: 'completed', label: 'Completed', count: 0 },
  206 |       { status: 'running',   label: 'Running',   count: 0 },
  207 |       { status: 'failed',    label: 'Failed',    count: 0 },
  208 |       { status: 'fallback',  label: 'Fallback',  count: 0 },
  209 |     ],
  210 |     timeSeries: [
  211 |       { date: '2024-01-15', primary: 0, fallback: 0 },
  212 |     ],
  213 |   });
  214 |   await mockDashboardApis(page, { stats: emptyStats });
  215 |   await page.goto('/');
  216 |   await expect(page.getByText(/no applications yet/i)).toBeVisible();
  217 | });
  218 | 
  219 | test('Given funnel data is all zero, Then funnel chart shows "no activity" message', async ({ page }) => {
  220 |   const stats = makeStats({
  221 |     funnelData: [
  222 |       { status: 'completed', label: 'Completed', count: 0 },
  223 |       { status: 'running',   label: 'Running',   count: 0 },
  224 |       { status: 'failed',    label: 'Failed',    count: 0 },
  225 |       { status: 'fallback',  label: 'Fallback',  count: 0 },
  226 |     ],
  227 |   });
  228 |   await mockDashboardApis(page, { stats });
  229 |   await page.goto('/');
  230 |   await expect(page.getByText(/no activity in the last 24/i)).toBeVisible();
  231 | });
  232 | 
  233 | test('Given LLM time series is all zero, Then resilience chart shows "no LLM calls" message', async ({ page }) => {
  234 |   const stats = makeStats({
  235 |     timeSeries: [{ date: '2024-01-15', primary: 0, fallback: 0 }],
  236 |   });
  237 |   await mockDashboardApis(page, { stats });
  238 |   await page.goto('/');
  239 |   await expect(page.getByText(/no llm calls recorded/i)).toBeVisible();
  240 | });
  241 | 
  242 | // ─────────────────────────────────────────────────────────────────────────────
  243 | // Scenario 5: LLM success rate color coding
  244 | // ─────────────────────────────────────────────────────────────────────────────
  245 | 
  246 | test('Given llm_success_rate >= 90, Then LLM card has success color', async ({ page }) => {
  247 |   await mockDashboardApis(page, { stats: makeStats({ llm_success_rate: 95.0 }) });
  248 |   await page.goto('/');
  249 |   const llmCard = page.locator('.metric-card').nth(3);
  250 |   await expect(llmCard).toHaveCSS('--metric-color', /color-success/);
  251 | });
  252 | 
  253 | test('Given llm_success_rate between 70 and 90, Then LLM card has warning color', async ({ page }) => {
  254 |   await mockDashboardApis(page, { stats: makeStats({ llm_success_rate: 75.0 }) });
  255 |   await page.goto('/');
  256 |   const llmCard = page.locator('.metric-card').nth(3);
  257 |   await expect(llmCard).toHaveCSS('--metric-color', /color-warning/);
  258 | });
  259 | 
  260 | test('Given llm_success_rate below 70, Then LLM card has danger color', async ({ page }) => {
  261 |   await mockDashboardApis(page, { stats: makeStats({ llm_success_rate: 60.0 }) });
  262 |   await page.goto('/');
  263 |   const llmCard = page.locator('.metric-card').nth(3);
  264 |   await expect(llmCard).toHaveCSS('--metric-color', /color-danger/);
  265 | });
  266 | 
  267 | // ─────────────────────────────────────────────────────────────────────────────
  268 | // Scenario 6: Stats section does not block application table
  269 | // ─────────────────────────────────────────────────────────────────────────────
  270 | 
  271 | test('Given stats API is slow, applications load independently', async ({ page }) => {
  272 |   let resolveStats;
  273 |   const statsPromise = new Promise((res) => { resolveStats = res; });
  274 | 
  275 |   await page.route('**/api/applications/', (r) => r.fulfill({ json: APPLICATIONS }));
  276 |   await page.route('**/api/dashboard/stats/', async (r) => {
  277 |     // Never resolves during this test — intentionally slow
  278 |     await statsPromise;
  279 |     r.fulfill({ json: makeStats() });
  280 |   });
  281 | 
  282 |   await page.goto('/');
  283 | 
  284 |   // The application table should appear even while stats is still loading
```