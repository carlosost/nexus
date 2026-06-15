// @ts-check
import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for Elvex Nexus E2E tests.
 *
 * Tests live in frontend/e2e/ and run against the running Vite dev server
 * (http://localhost:3000). API calls are intercepted via route.fulfill()
 * so no live Django backend is required for the E2E suite.
 *
 * Run:
 *   cd frontend && npx playwright test         # headless
 *   cd frontend && npx playwright test --ui    # interactive
 */
export default defineConfig({
  testDir: './e2e',

  // Retry once on CI to absorb transient timing flakiness.
  retries: process.env.CI ? 1 : 0,

  // Reporter: dot for CI, HTML for local.
  reporter: process.env.CI ? 'dot' : 'html',

  use: {
    baseURL:     'http://localhost:3000',
    trace:       'on-first-retry',
    screenshot:  'only-on-failure',
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],

  // Start the Vite dev server automatically before the test suite.
  webServer: {
    command:            'npm run dev',
    url:                'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout:            30_000,
  },
});
