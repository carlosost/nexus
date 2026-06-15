Good — I have the full picture. Let me now build everything systematically.Key architectural decisions from the audit:

- **Router**: manual path-split in `main.jsx` — add `/settings` branch
- **Test runner**: currently Jest + Babel; migrating to **Vitest** (native ESM, shared Vite config, no separate Babel transform)
- **E2E**: Cypress exists for backend BDD; adding **Playwright** in `frontend/e2e/` for cross-page Settings→Dashboard flows
- **Backend gaps**: no detail/PATCH/DELETE endpoints for Jobs, Candidates, or Applications — need to add them before frontend can wire delete/edit
- **Hook gaps**: `useJobs` and `useCandidates` only expose `addX`; need `removeX` and `patchX`

---

## Phase 1 — Backend: add detail endpoints

**Backend additions needed:** `JobDetailSerializer`, `CandidateDetailSerializer`, three new views, three new URL patterns.Good — `Job` has `updated_at`, `Candidate` does not. Now I'll write everything.### Backend — serializers, views, urlsNow add the three detail views to `views.py`:Wire the new views into `urls.py`:Also need to update the `urls.py` comment at the top and fix the existing per-application routes since we now have a new `applications/<uuid:pk>/` detail pattern above them — need to check there's no conflict. The existing routes are `applications/<uuid:pk>/run/`, `applications/<uuid:pk>/score/`, and `applications/<uuid:pk>/reviews/` — Django's URL resolver matches the most specific pattern first, so `applications/<uuid>/run/` wins over `applications/<uuid>/`. These are fine — no conflict.### Phase 2 — Frontend: API client additions### Phase 3 — Hook upgrades### Phase 4 — Dashboard simplification### Phase 5 — Settings page ecosystem### Phase 6 — Router update### Phase 7 — Settings CSS### Phase 8 — Test infrastructure: Jest → Vitest + PlaywrightNow update `package.json` — replace Jest with Vitest, add Playwright:Update `setupTests.js` for Vitest compatibility:### Phase 9 — Migrate existing tests to Vitest + write new testsNow the new Settings component tests:### Phase 10 — Playwright config + E2E specNow verify the complete file tree before presenting:All clean. Dashboard has only 3 imports. Let me also verify the `BulkRunBar` has the `data-testid` the E2E spec references:Everything checks out. Here is the complete structured deliverable.

---

## 1 — Route Blueprint & Component Movement Map

```
Before                          After
──────────────────────────────  ──────────────────────────────────────────
/  →  Dashboard                 /          →  Dashboard  (read-only)
      ├── + Add Job btn               ⚙ Settings nav link only
      ├── + Add Candidate btn
      ├── + New Application btn  /settings  →  Settings
      ├── JobIngestionModal             ├── Tab: Jobs
      ├── CandidateIngestionModal       │   └── JobBoard
      └── AssociationModal             │       ├── JobIngestionModal (reused)
                                       │       ├── EditJobModal (new)
/review/:id  →  ReviewApp             │       └── DeleteConfirmModal (new)
                                       ├── Tab: Candidates
                                       │   └── CandidateBoard
                                       │       ├── CandidateIngestionModal (reused)
                                       │       ├── EditCandidateModal (new)
                                       │       └── DeleteConfirmModal (shared)
                                       └── Tab: Applications
                                           └── ApplicationCenter (inline form)

/review/:id  →  ReviewApp  (unchanged)
```

**Hook ownership shift:**

| Hook | Before | After |
|---|---|---|
| `useApplications` | Dashboard | Dashboard (unchanged) |
| `useJobs` | Dashboard (dropdown only) | Settings (full CRUD owner) |
| `useCandidates` | Dashboard (dropdown only) | Settings (full CRUD owner) |

New hook exports added: `patchJob`, `removeJob`, `patchCandidate`, `removeCandidate`.

---

## 2 — Chronological Implementation Strategy

**Phase 1 — Backend detail endpoints** *(done — no frontend breakage at this stage)*
Add `JobDetailSerializer`, `CandidateDetailSerializer` to `serializers.py`. Add `JobDetailView`, `CandidateDetailView`, `ApplicationDetailView` to `views.py`. Wire `GET/PATCH/DELETE /api/jobs/<uuid>/`, `GET/PATCH/DELETE /api/candidates/<uuid>/`, `DELETE /api/applications/<uuid>/` into `urls.py`. The existing Dashboard is untouched; the new routes are purely additive.

**Phase 2 — API client additions** *(done — additive, zero breakage)*
Add `_patch()` and `_delete()` internal helpers. Export `getJob`, `updateJob`, `deleteJob`, `getCandidate`, `updateCandidate`, `deleteCandidate`, `deleteApplication`. All existing exports are unchanged.

**Phase 3 — Hook upgrades** *(done — additive, backward-compatible)*
`useJobs` gains `patchJob` and `removeJob` in its return value. `useCandidates` gains `patchCandidate` and `removeCandidate`. Both remain drop-in replacements for any existing consumer.

**Phase 4 — Build Settings ecosystem** *(done — new files, no existing file touched)*
Create `settings/` directory. Write `DeleteConfirmModal`, `EditJobModal`, `EditCandidateModal`, `JobBoard`, `CandidateBoard`, `ApplicationCenter`. Write root `Settings.jsx` with aria tab panel structure. Write `styles/settings.css`.

**Phase 5 — Dashboard simplification** *(done — safe because Settings now owns admin)*
Remove `useJobs`, `useCandidates`, three modal imports, three `useState` modal flags, and three header buttons. Replace with a single `⚙ Settings` `<a>` link. The application list + pipeline trigger remain.

**Phase 6 — Router** *(done)*
Add `/settings` branch to `main.jsx`'s `Router()` function. Import `Settings`. No library required.

**Phase 7 — Test infrastructure migration** *(done)*
Remove `jest`, `babel-jest`, `@babel/...` from `package.json`. Add `vitest`, `@vitest/coverage-v8`, `@vitest/ui`, `@playwright/test`, `jsdom`. Add `test:` config block to `vite.config.js` (`globals: true`, `environment: 'jsdom'`). Update `setupTests.js`. Migrate existing `ReviewApp.test.jsx` and `OverridePanel.test.jsx` from `jest.*` → `vi.*`.

**Phase 8 — New tests** *(done)*
Write `DeleteConfirmModal.test.jsx`, `JobBoard.test.jsx`, `ApplicationCenter.test.jsx` using Vitest + RTL. Write `e2e/settings_flow.spec.js` using Playwright with `route.fulfill()` API interception. Write `playwright.config.js`.

---

## 3 — Testing Matrix

### BDD Scenarios (expressed as Given/When/Then)

| # | Layer | Scenario |
|---|---|---|
| 1 | E2E | **Given** user on Settings/Candidates, **When** they upload a `.txt` file, **Then** client error fires, API not called |
| 2 | E2E | **Given** user creates job on Settings, **When** they link it to candidate on Applications tab and navigate to `/`, **Then** application row appears selectable on Dashboard |
| 3 | E2E | **Given** job exists, **When** user clicks Delete + reads cascade warning + confirms, **Then** row removed, DELETE endpoint called |
| 4 | E2E | **Given** job exists, **When** user edits title and saves, **Then** updated title appears in list without page reload |
| 5 | Unit | **Given** `DeleteConfirmModal` open, **When** Cancel clicked, **Then** `onClose` fires, `onConfirm` never called |
| 6 | Unit | **Given** `DeleteConfirmModal` open, **When** `onConfirm` rejects, **Then** error banner shown, modal stays open, button re-enabled |
| 7 | Unit | **Given** `JobBoard` with no jobs, **When** rendered, **Then** empty-state message shown (not error, not table) |
| 8 | Unit | **Given** `JobBoard` with jobs, **When** user clicks expand, **Then** description + must_haves JSON rendered inline |
| 9 | Unit | **Given** `ApplicationCenter` with empty jobs list, **When** rendered, **Then** prerequisite notice shown and submit disabled |
| 10 | Unit | **Given** `ApplicationCenter` with both collections, **When** user selects + submits, **Then** `createApplication` called with correct payload, success banner shown, form resets |

### Vitest unit test — `DeleteConfirmModal.test.jsx` (full boilerplate, already written)

Key patterns to note:
```js
// 1. Mock the API at vi.mock level (auto-hoisted by Vitest)
vi.mock('../api/client.js', () => ({ deleteJob: vi.fn() }));

// 2. Test the async loading state without timers
const onConfirm = vi.fn(() => new Promise((r) => { resolve = r; }));
await userEvent.click(screen.getByTestId('delete-confirm-btn'));
expect(screen.getByTestId('delete-confirm-btn')).toHaveTextContent('Deleting…');
resolve(); // unblock

// 3. Test error path — modal stays open, error shown
onConfirm.mockRejectedValue(new Error('Server error'));
await waitFor(() => expect(screen.getByTestId('delete-confirm-error')).toBeInTheDocument());
expect(onClose).not.toHaveBeenCalled(); // still open for retry
```

### Playwright E2E — `settings_flow.spec.js` (full boilerplate, already written)

Key patterns:
```js
// 1. Intercept all API calls — no live backend needed
await page.route('**/api/jobs/', (r) => r.fulfill({ json: [JOB] }));

// 2. Method-discriminated route handlers for POST vs GET
await page.route('**/api/jobs/', async (route) => {
  if (route.request().method() === 'POST') {
    await route.fulfill({ status: 201, json: newJob });
  } else {
    await route.fulfill({ json: [newJob] });
  }
});

// 3. File upload interception (Playwright native)
await fileInput.setInputFiles({
  name: 'resume.txt', mimeType: 'text/plain', buffer: Buffer.from('not a pdf'),
});

// 4. Cross-page navigation assertion
await page.goto('/');
await expect(page.getByText('Alice Chen')).toBeVisible();
```

---

## Complete File Inventory

**Backend (modified):** `serializers.py` · `views.py` · `urls.py`

**Frontend (modified):** `api/client.js` · `hooks/useJobs.js` · `hooks/useCandidates.js` · `components/Dashboard.jsx` · `components/BulkRunBar.jsx` · `main.jsx` · `vite.config.js` · `package.json` · `src/setupTests.js` · `__tests__/ReviewApp.test.jsx` · `__tests__/OverridePanel.test.jsx`

**Frontend (new):** `components/Settings.jsx` · `components/settings/JobBoard.jsx` · `components/settings/CandidateBoard.jsx` · `components/settings/ApplicationCenter.jsx` · `components/settings/EditJobModal.jsx` · `components/settings/EditCandidateModal.jsx` · `components/settings/DeleteConfirmModal.jsx` · `styles/settings.css` · `__tests__/DeleteConfirmModal.test.jsx` · `__tests__/JobBoard.test.jsx` · `__tests__/ApplicationCenter.test.jsx` · `e2e/settings_flow.spec.js` · `playwright.config.js`

**Run the new test suites:**
```bash
cd frontend
npm install          # picks up vitest + @playwright/test
npx vitest run       # unit tests (Vitest)
npx playwright install chromium
npx playwright test  # E2E (Playwright, spins up Vite automatically)
```