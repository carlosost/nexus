/**
 * API client for the resume pipeline backend.
 *
 * All endpoints are relative to the base URL so the Vite dev proxy
 * (→ http://localhost:8000) and Cypress cy.intercept() both work
 * without any configuration changes.
 */

const BASE = '/api';

/**
 * Fetch the score card for an application.
 * GET /api/applications/{id}/score/
 *
 * @param {string} applicationId
 * @returns {Promise<object>} The score data.
 * @throws {Error} With status code on HTTP error.
 */
export async function fetchScore(applicationId) {
  const res = await fetch(`${BASE}/applications/${applicationId}/score/`);
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Submit a human review decision.
 * POST /api/applications/{id}/reviews/
 *
 * @param {string} applicationId
 * @param {{ reviewer_email: string, decision: string, override_reason?: string }} payload
 * @returns {Promise<object>} The created review.
 * @throws {Error} With status code and body on HTTP error.
 */
export async function submitReview(applicationId, payload) {
  const res = await fetch(`${BASE}/applications/${applicationId}/reviews/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return res.json();
}
