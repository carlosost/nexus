/**
 * API client for the Elvex Nexus resume pipeline backend.
 *
 * All paths are relative so the Vite dev proxy (/api → http://localhost:8000)
 * and Cypress cy.intercept() both work without additional configuration.
 *
 * Error contract:
 *   Every function throws an Error with `.status` (HTTP status code) and
 *   optionally `.body` (parsed JSON error payload) on non-2xx responses.
 *   Callers should catch and inspect these properties for UX error handling.
 */

const BASE = '/api';

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

async function _json(res) {
  if (res.ok) return res.json();
  const body = await res.json().catch(() => ({}));
  const err = new Error(`HTTP ${res.status}`);
  err.status = res.status;
  err.body = body;
  throw err;
}

async function _get(path) {
  return _json(await fetch(`${BASE}${path}`));
}

async function _post(path, payload, contentType = 'json') {
  const opts = { method: 'POST' };
  if (contentType === 'json') {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(payload);
  } else {
    // multipart/form-data — let the browser set the boundary automatically
    opts.body = payload; // FormData instance
  }
  return _json(await fetch(`${BASE}${path}`, opts));
}

async function _delete(path) {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' });
  if (res.status === 204) return null; // no content — success
  // Unexpected non-2xx
  const body = await res.json().catch(() => ({}));
  const err = new Error(`HTTP ${res.status}`);
  err.status = res.status;
  err.body = body;
  throw err;
}


// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

/**
 * GET /api/jobs/
 * @returns {Promise<Array<{id: string, title: string, created_at: string}>>}
 */
export function listJobs() {
  return _get('/jobs/');
}

/**
 * GET /api/jobs/:id/
 * @returns {Promise<{id, title, description, must_haves, created_at, updated_at}>}
 */
export function getJob(id) {
  return _get(`/jobs/${id}/`);
}

/**
 * POST /api/jobs/
 * @param {{ raw_markdown: string }} data
 * @returns {Promise<{id: string, title: string, created_at: string}>}
 */
export function createJob(data) {
  return _post('/jobs/', data, 'json');
}

/**
 * DELETE /api/jobs/:id/
 * Cascades to all Applications linked to this Job.
 */
export function deleteJob(id) {
  return _delete(`/jobs/${id}/`);
}


// ---------------------------------------------------------------------------
// Candidates
// ---------------------------------------------------------------------------

/**
 * GET /api/candidates/
 * @returns {Promise<Array<{id: string, name: string, email: string, created_at: string}>>}
 */
export function listCandidates() {
  return _get('/candidates/');
}

/**
 * GET /api/candidates/:id/
 * @returns {Promise<{id, name, email, resume_parsed, created_at}>}
 */
export function getCandidate(id) {
  return _get(`/candidates/${id}/`);
}

/**
 * POST /api/candidates/  (multipart/form-data)
 * @param {{ name: string, email: string, resume_pdf: File }} data
 * @returns {Promise<{id: string, name: string, email: string, created_at: string}>}
 */
export function createCandidate({ name, email, resume_pdf }) {
  const form = new FormData();
  form.append('name', name);
  form.append('email', email);
  form.append('resume_pdf', resume_pdf);
  return _post('/candidates/', form, 'multipart');
}


/**
 * DELETE /api/candidates/:id/
 * Cascades to all Applications linked to this Candidate.
 */
export function deleteCandidate(id) {
  return _delete(`/candidates/${id}/`);
}


// ---------------------------------------------------------------------------
// Applications
// ---------------------------------------------------------------------------

/**
 * GET /api/applications/
 * @returns {Promise<Array<ApplicationRow>>}
 *
 * ApplicationRow shape:
 *   id                        string (UUID)
 *   candidate_name            string
 *   candidate_email           string
 *   job_title                 string
 *   status                    string  — Application.Status enum value
 *   final_score               number | null
 *   is_evaluated_via_fallback boolean
 *   created_at                string (ISO 8601)
 *   updated_at                string (ISO 8601)
 */
export function listApplications() {
  return _get('/applications/');
}

/**
 * POST /api/applications/
 * @param {{ job_id: string, candidate_id: string }} data
 * @returns {Promise<{ data: ApplicationRow, created: boolean }>}
 *   created=true  → HTTP 201 — new application
 *   created=false → HTTP 200 — pair already existed (idempotent)
 */
export async function createApplication(data) {
  const res = await fetch(`${BASE}/applications/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return { data: await res.json(), created: res.status === 201 };
}

/**
 * DELETE /api/applications/:id/
 * Removes the Application and all pipeline stage records; Job + Candidate untouched.
 */
export function deleteApplication(id) {
  return _delete(`/applications/${id}/`);
}

/**
 * POST /api/applications/{id}/run/
 *
 * Triggers the 4-stage pipeline synchronously.  The UI treats this as a
 * long-running background request: optimistically flip the row to "processing"
 * before calling, then update with the resolved result.
 *
 * @param {string} applicationId
 * @returns {Promise<object>} pipeline result payload
 */
export function runPipeline(applicationId) {
  return _post(`/applications/${applicationId}/run/`, {}, 'json');
}

/**
 * GET /api/applications/{id}/score/
 *
 * Returns 404 while the pipeline has not yet completed.  The polling hook
 * uses this to detect when an in-flight run finishes.
 *
 * @param {string} applicationId
 * @returns {Promise<ScoreCard>}
 */
export function fetchScore(applicationId) {
  return _get(`/applications/${applicationId}/score/`);
}

/**
 * POST /api/applications/{id}/reviews/
 * @param {string} applicationId
 * @param {{ reviewer_email: string, decision: string, override_reason?: string }} payload
 * @returns {Promise<object>}
 */
export function submitReview(applicationId, payload) {
  return _post(`/applications/${applicationId}/reviews/`, payload, 'json');
}


// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

/**
 * GET /api/dashboard/stats/
 *
 * Returns aggregated telemetry for the Dashboard stats section.
 *
 * Shape:
 *   totals: { applications, candidates, jobs, active_jobs, llm_success_rate }
 *   application_status_distribution: [{ status, label, count }]
 *   job_execution_funnel:            [{ status, label, count }]
 *   llm_resilience: { time_series: [{ date, primary, fallback }] }
 *
 * @returns {Promise<DashboardStats>}
 */
export function fetchDashboardStats() {
  return _get('/dashboard/stats/');
}
