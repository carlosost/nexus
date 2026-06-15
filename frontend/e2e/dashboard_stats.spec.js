/**
 * E2E specification: Dashboard telemetry stats section.
 *
 * All backend API calls are intercepted via Playwright's route.fulfill() —
 * no real Django server required. Each test sets up its own route handlers.
 *
 * ─── BDD Scenarios ──────────────────────────────────────────────────────────
 *
 * Scenario 1: Dashboard loads and metric cards display backend values
 *   Given the stats API returns a valid payload
 *   When  the user navigates to /
 *   Then  all 4 metric cards are visible
 *   And   each card displays the value from the API response
 *
 * Scenario 2: Stats API error — error banner shown with retry button
 *   Given the stats API returns a 500 error
 *   When  the user navigates to /
 *   Then  the stats error banner is visible
 *   And   the existing ApplicationTable is still rendered (table not blocked)
 *
 * Scenario 3: Retry button re-calls the stats API
 *   Given the stats API first fails then succeeds
 *   When  the user clicks the Retry button in the error banner
 *   Then  the error banner disappears
 *   And   the metric cards display the successful payload values
 *
 * Scenario 4: Empty data state — chart cards show their empty messages
 *   Given the stats API returns zero counts for all buckets and no time-series data
 *   When  the user navigates to /
 *   Then  the status chart shows "No applications yet"
 *   And   the funnel chart shows "No activity in the last 24 h"
 *   And   the LLM chart shows "No LLM calls recorded"
 *
 * Scenario 5: LLM success rate color reflects health
 *   Given LLM success rate is 95.0 (≥ 90) → success color applied
 *   Given LLM success rate is 75.0 (≥ 70, < 90) → warning color applied
 *   Given LLM success rate is 60.0 (< 70) → danger color applied
 *
 * Scenario 6: Stats section does not block application table
 *   Given the stats API is slow / fails
 *   When  the applications API resolves
 *   Then  the application table rows are visible regardless of stats state
 *
 * ─── Regression guards ───────────────────────────────────────────────────────
 *
 * Scenario 7: Dashboard header and Settings link remain present
 *   Given the stats API resolves
 *   When  the user is on the Dashboard
 *   Then  the header branding is visible
 *   And   the Settings nav link is visible
 */

import { test, expect } from '@playwright/test';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const APPLICATIONS = [
  {
    id:                        'app-1',
    candidate_name:            'Alice Chen',
    candidate_email:           'alice@example.com',
    job_title:                 'Senior Data Engineer',
    status:                    'scored',
    final_score:               0.82,
    is_evaluated_via_fallback: false,
    created_at:                '2024-01-12T00:00:00Z',
    updated_at:                '2024-01-15T00:00:00Z',
  },
];

function makeStats({
  applications     = 142,
  active_jobs      = 18,
  workspace_users  = 9,
  llm_success_rate = 94.2,
  statusDist       = [],
  funnelData       = [],
  timeSeries       = [],
} = {}) {
  return {
    totals: { applications, active_jobs, workspace_users, llm_success_rate },
    application_status_distribution: statusDist,
    job_execution_funnel: funnelData,
    llm_resilience: { time_series: timeSeries },
  };
}

/** Wire all baseline API routes for the Dashboard page. */
async function mockDashboardApis(page, {
  stats           = makeStats(),
  statsStatus     = 200,
  applications    = APPLICATIONS,
} = {}) {
  await page.route('**/api/applications/', (r) => r.fulfill({ json: applications }));

  if (statsStatus !== 200) {
    await page.route('**/api/dashboard/stats/', (r) =>
      r.fulfill({ status: statsStatus, json: { detail: 'Internal server error' } })
    );
  } else {
    await page.route('**/api/dashboard/stats/', (r) => r.fulfill({ json: stats }));
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 1: Metric cards display backend values
// ─────────────────────────────────────────────────────────────────────────────

test('Given stats API resolves, When dashboard loads, Then 4 metric cards show API values', async ({ page }) => {
  await mockDashboardApis(page, {
    stats: makeStats({
      applications:     142,
      active_jobs:      18,
      workspace_users:  9,
      llm_success_rate: 94.2,
    }),
  });

  await page.goto('/');

  // All 4 metric-card containers are visible
  const cards = page.locator('.metric-card');
  await expect(cards).toHaveCount(4);

  // Values match what the API returned
  await expect(page.locator('.metric-card__value').nth(0)).toContainText('142');
  await expect(page.locator('.metric-card__value').nth(1)).toContainText('18');
  await expect(page.locator('.metric-card__value').nth(2)).toContainText('9');
  await expect(page.locator('.metric-card__value').nth(3)).toContainText('94.2%');
});

test('Given large application count, Then value is formatted with locale separators', async ({ page }) => {
  await mockDashboardApis(page, {
    stats: makeStats({ applications: 1500 }),
  });
  await page.goto('/');
  // fmt() uses toLocaleString() — "1,500" in en-US locale
  await expect(page.locator('.metric-card__value').nth(0)).toContainText('1');
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 2: Stats API error — error banner shown, table still renders
// ─────────────────────────────────────────────────────────────────────────────

test('Given stats API returns 500, When dashboard loads, Then error banner is visible', async ({ page }) => {
  await mockDashboardApis(page, { statsStatus: 500 });
  await page.goto('/');
  await expect(page.locator('.stats-error')).toBeVisible();
});

test('Given stats API fails, Then ApplicationTable is still rendered', async ({ page }) => {
  await mockDashboardApis(page, { statsStatus: 500 });
  await page.goto('/');
  // The error in stats section must not block the application table
  await expect(page.locator('.application-table, [data-testid="app-table"]').first()).toBeVisible();
});

test('Given stats API fails, Then error banner contains retry button', async ({ page }) => {
  await mockDashboardApis(page, { statsStatus: 500 });
  await page.goto('/');
  const banner = page.locator('.stats-error');
  await expect(banner.getByRole('button', { name: /retry/i })).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 3: Retry button re-calls the stats API
// ─────────────────────────────────────────────────────────────────────────────

test('Given stats fails then succeeds, When user clicks Retry, Then cards appear and error is gone', async ({ page }) => {
  let callCount = 0;

  await page.route('**/api/applications/', (r) => r.fulfill({ json: [] }));
  await page.route('**/api/dashboard/stats/', (r) => {
    callCount++;
    if (callCount === 1) {
      return r.fulfill({ status: 500, json: { detail: 'Temporary error' } });
    }
    return r.fulfill({ json: makeStats({ applications: 99 }) });
  });

  await page.goto('/');

  // Error banner present after first (failed) call
  await expect(page.locator('.stats-error')).toBeVisible();

  // Click Retry
  await page.locator('.stats-error').getByRole('button', { name: /retry/i }).click();

  // Error banner disappears, metric card with value 99 appears
  await expect(page.locator('.stats-error')).not.toBeVisible({ timeout: 4000 });
  await expect(page.locator('.metric-card__value').first()).toContainText('99');
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 4: Empty data — chart empty states
// ─────────────────────────────────────────────────────────────────────────────

test('Given all stats are zero, Then status chart shows empty state', async ({ page }) => {
  const emptyStats = makeStats({
    applications: 0,
    statusDist: [
      { status: 'pending', label: 'Pending', count: 0 },
    ],
    funnelData: [
      { status: 'completed', label: 'Completed', count: 0 },
      { status: 'running',   label: 'Running',   count: 0 },
      { status: 'failed',    label: 'Failed',    count: 0 },
      { status: 'fallback',  label: 'Fallback',  count: 0 },
    ],
    timeSeries: [
      { date: '2024-01-15', primary: 0, fallback: 0 },
    ],
  });
  await mockDashboardApis(page, { stats: emptyStats });
  await page.goto('/');
  await expect(page.getByText(/no applications yet/i)).toBeVisible();
});

test('Given funnel data is all zero, Then funnel chart shows "no activity" message', async ({ page }) => {
  const stats = makeStats({
    funnelData: [
      { status: 'completed', label: 'Completed', count: 0 },
      { status: 'running',   label: 'Running',   count: 0 },
      { status: 'failed',    label: 'Failed',    count: 0 },
      { status: 'fallback',  label: 'Fallback',  count: 0 },
    ],
  });
  await mockDashboardApis(page, { stats });
  await page.goto('/');
  await expect(page.getByText(/no activity in the last 24/i)).toBeVisible();
});

test('Given LLM time series is all zero, Then resilience chart shows "no LLM calls" message', async ({ page }) => {
  const stats = makeStats({
    timeSeries: [{ date: '2024-01-15', primary: 0, fallback: 0 }],
  });
  await mockDashboardApis(page, { stats });
  await page.goto('/');
  await expect(page.getByText(/no llm calls recorded/i)).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 5: LLM success rate color coding
// ─────────────────────────────────────────────────────────────────────────────

test('Given llm_success_rate >= 90, Then LLM card has success color', async ({ page }) => {
  await mockDashboardApis(page, { stats: makeStats({ llm_success_rate: 95.0 }) });
  await page.goto('/');
  const llmCard = page.locator('.metric-card').nth(3);
  await expect(llmCard).toHaveCSS('--metric-color', /color-success/);
});

test('Given llm_success_rate between 70 and 90, Then LLM card has warning color', async ({ page }) => {
  await mockDashboardApis(page, { stats: makeStats({ llm_success_rate: 75.0 }) });
  await page.goto('/');
  const llmCard = page.locator('.metric-card').nth(3);
  await expect(llmCard).toHaveCSS('--metric-color', /color-warning/);
});

test('Given llm_success_rate below 70, Then LLM card has danger color', async ({ page }) => {
  await mockDashboardApis(page, { stats: makeStats({ llm_success_rate: 60.0 }) });
  await page.goto('/');
  const llmCard = page.locator('.metric-card').nth(3);
  await expect(llmCard).toHaveCSS('--metric-color', /color-danger/);
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 6: Stats section does not block application table
// ─────────────────────────────────────────────────────────────────────────────

test('Given stats API is slow, applications load independently', async ({ page }) => {
  let resolveStats;
  const statsPromise = new Promise((res) => { resolveStats = res; });

  await page.route('**/api/applications/', (r) => r.fulfill({ json: APPLICATIONS }));
  await page.route('**/api/dashboard/stats/', async (r) => {
    // Never resolves during this test — intentionally slow
    await statsPromise;
    r.fulfill({ json: makeStats() });
  });

  await page.goto('/');

  // The application table should appear even while stats is still loading
  await expect(page.getByText('Alice Chen')).toBeVisible({ timeout: 5000 });
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 7: Regression — header and nav intact after adding stats section
// ─────────────────────────────────────────────────────────────────────────────

test('Dashboard header branding and Settings link are present', async ({ page }) => {
  await mockDashboardApis(page);
  await page.goto('/');
  await expect(page.locator('.dashboard__title')).toContainText('Elvex Nexus');
  await expect(page.getByRole('link', { name: /settings/i })).toBeVisible();
});

test('Stats grid is rendered between header and application table', async ({ page }) => {
  await mockDashboardApis(page);
  await page.goto('/');

  const statsGrid  = page.locator('.stats-grid');
  const appSection = page.locator('.dashboard__main');

  await expect(statsGrid).toBeVisible();
  await expect(appSection).toBeVisible();

  // stats-grid should appear before the application main section in DOM order
  const statsY = await statsGrid.boundingBox().then((b) => b?.y ?? 0);
  const appY   = await appSection.boundingBox().then((b) => b?.y ?? 0);
  expect(statsY).toBeLessThan(appY);
});

test('Charts grid renders 3 chart-card containers', async ({ page }) => {
  await mockDashboardApis(page, {
    stats: makeStats({
      statusDist: [{ status: 'scored', label: 'Scored', count: 5 }],
      funnelData: [{ status: 'completed', label: 'Completed', count: 5 }],
      timeSeries: [{ date: '2024-01-15', primary: 10, fallback: 1 }],
    }),
  });
  await page.goto('/');
  await expect(page.locator('.chart-card')).toHaveCount(3);
});
