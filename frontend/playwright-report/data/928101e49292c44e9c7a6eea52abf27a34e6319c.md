# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: dashboard_stats.spec.js >> Given llm_success_rate >= 90, Then LLM card has success color
- Location: e2e/dashboard_stats.spec.js:246:1

# Error details

```
Error: expect(locator).toHaveCSS(expected) failed

Locator: locator('.metric-card').nth(3)
Expected pattern: /color-success/
Received string:  "#22c55e"
Timeout: 5000ms

Call log:
  - Expect "toHaveCSS" with timeout 5000ms
  - waiting for locator('.metric-card').nth(3)
    - locator resolved to <div class="metric-card">…</div>
    - unexpected value "#ef4444"
    13 × locator resolved to <div class="metric-card">…</div>
       - unexpected value "#22c55e"

```

```yaml
- text: LLM Success Rate 95% primary backend calls
```

# Test source

```ts
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
  184 |   await expect(page.locator('.stats-error')).toBeVisible();
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
> 250 |   await expect(llmCard).toHaveCSS('--metric-color', /color-success/);
      |                         ^ Error: expect(locator).toHaveCSS(expected) failed
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
  285 |   await expect(page.getByText('Alice Chen')).toBeVisible({ timeout: 5000 });
  286 | });
  287 | 
  288 | // ─────────────────────────────────────────────────────────────────────────────
  289 | // Scenario 7: Regression — header and nav intact after adding stats section
  290 | // ─────────────────────────────────────────────────────────────────────────────
  291 | 
  292 | test('Dashboard header branding and Settings link are present', async ({ page }) => {
  293 |   await mockDashboardApis(page);
  294 |   await page.goto('/');
  295 |   await expect(page.locator('.dashboard__title')).toContainText('Elvex Nexus');
  296 |   await expect(page.getByRole('link', { name: /settings/i })).toBeVisible();
  297 | });
  298 | 
  299 | test('Stats grid is rendered between header and application table', async ({ page }) => {
  300 |   await mockDashboardApis(page);
  301 |   await page.goto('/');
  302 | 
  303 |   const statsGrid  = page.locator('.stats-grid');
  304 |   const appSection = page.locator('.dashboard__main');
  305 | 
  306 |   await expect(statsGrid).toBeVisible();
  307 |   await expect(appSection).toBeVisible();
  308 | 
  309 |   // stats-grid should appear before the application main section in DOM order
  310 |   const statsY = await statsGrid.boundingBox().then((b) => b?.y ?? 0);
  311 |   const appY   = await appSection.boundingBox().then((b) => b?.y ?? 0);
  312 |   expect(statsY).toBeLessThan(appY);
  313 | });
  314 | 
  315 | test('Charts grid renders 3 chart-card containers', async ({ page }) => {
  316 |   await mockDashboardApis(page, {
  317 |     stats: makeStats({
  318 |       statusDist: [{ status: 'scored', label: 'Scored', count: 5 }],
  319 |       funnelData: [{ status: 'completed', label: 'Completed', count: 5 }],
  320 |       timeSeries: [{ date: '2024-01-15', primary: 10, fallback: 1 }],
  321 |     }),
  322 |   });
  323 |   await page.goto('/');
  324 |   await expect(page.locator('.chart-card')).toHaveCount(3);
  325 | });
  326 | 
```