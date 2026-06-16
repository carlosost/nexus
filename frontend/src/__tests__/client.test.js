/**
 * Unit tests for api/client.js.
 *
 * All tests mock `fetch` globally with vi.stubGlobal so no real network
 * calls are made.  Each function's contract (URL, method, headers, body,
 * return shape, and error behaviour) is verified in isolation.
 */

import { vi, describe, test, beforeEach, afterEach, expect } from 'vitest';
import {
  listJobs, getJob, createJob, deleteJob,
  listCandidates, getCandidate, createCandidate, deleteCandidate,
  listApplications, createApplication, deleteApplication,
  runPipeline, fetchScore, submitReview,
  fetchDashboardStats,
} from '../api/client.js';

// ── Helpers ────────────────────────────────────────────────────────────────────

function okFetch(status, body) {
  return vi.fn().mockResolvedValue({
    ok:     true,
    status,
    json:   vi.fn().mockResolvedValue(body),
  });
}

function errFetch(status, body) {
  return vi.fn().mockResolvedValue({
    ok:     false,
    status,
    json:   vi.fn().mockResolvedValue(body),
  });
}

function deleteFetch(status) {
  // _delete only reads res.status — no .ok or .json needed for 204 path
  return vi.fn().mockResolvedValue({
    status,
    json: vi.fn().mockResolvedValue({ detail: 'error' }),
  });
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});
afterEach(() => {
  vi.unstubAllGlobals();
});

// ── _json / error contract ─────────────────────────────────────────────────────

describe('HTTP error contract', () => {
  test('non-2xx throws Error with .status and .body', async () => {
    global.fetch = errFetch(422, { title: ['Required.'] });
    await expect(listJobs()).rejects.toMatchObject({
      status: 422,
      body:   { title: ['Required.'] },
    });
  });

  test('500 response throws with status=500', async () => {
    global.fetch = errFetch(500, { detail: 'Internal server error' });
    await expect(createJob({ raw_markdown: '' })).rejects.toMatchObject({ status: 500 });
  });

  test('error body falls back to {} when JSON parse fails', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false, status: 500,
      json: vi.fn().mockRejectedValue(new Error('Not JSON')),
    });
    await expect(listJobs()).rejects.toMatchObject({ status: 500, body: {} });
  });
});

// ── Jobs ──────────────────────────────────────────────────────────────────────

describe('Jobs', () => {
  test('listJobs GETs /api/jobs/ and returns JSON', async () => {
    const jobs = [{ id: 'j1', title: 'Eng' }];
    global.fetch = okFetch(200, jobs);
    const result = await listJobs();
    expect(result).toEqual(jobs);
    expect(global.fetch).toHaveBeenCalledWith('/api/jobs/');
  });

  test('getJob GETs /api/jobs/:id/', async () => {
    global.fetch = okFetch(200, { id: 'j1', title: 'Eng' });
    await getJob('j1');
    expect(global.fetch).toHaveBeenCalledWith('/api/jobs/j1/');
  });

  test('createJob POSTs JSON to /api/jobs/', async () => {
    global.fetch = okFetch(201, { id: 'new', title: 'New' });
    const result = await createJob({ raw_markdown: '# Title' });
    expect(result.id).toBe('new');
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/jobs/',
      expect.objectContaining({
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ raw_markdown: '# Title' }),
      })
    );
  });

  test('deleteJob sends DELETE to /api/jobs/:id/ and returns null on 204', async () => {
    global.fetch = deleteFetch(204);
    const result = await deleteJob('j1');
    expect(result).toBeNull();
    expect(global.fetch).toHaveBeenCalledWith('/api/jobs/j1/', { method: 'DELETE' });
  });

  test('deleteJob throws on non-204 response', async () => {
    global.fetch = deleteFetch(404);
    await expect(deleteJob('bad')).rejects.toMatchObject({ status: 404 });
  });
});

// ── Candidates ────────────────────────────────────────────────────────────────

describe('Candidates', () => {
  test('listCandidates GETs /api/candidates/', async () => {
    global.fetch = okFetch(200, []);
    await listCandidates();
    expect(global.fetch).toHaveBeenCalledWith('/api/candidates/');
  });

  test('getCandidate GETs /api/candidates/:id/', async () => {
    global.fetch = okFetch(200, { id: 'c1' });
    await getCandidate('c1');
    expect(global.fetch).toHaveBeenCalledWith('/api/candidates/c1/');
  });

  test('createCandidate sends multipart FormData to /api/candidates/', async () => {
    global.fetch = okFetch(201, { id: 'new-c' });
    const file = new File(['content'], 'cv.pdf', { type: 'application/pdf' });
    await createCandidate({ name: 'Alice', email: 'alice@test.com', resume_pdf: file });
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/candidates/');
    expect(opts.method).toBe('POST');
    expect(opts.body).toBeInstanceOf(FormData);
    // Content-Type must NOT be set — browser sets multipart boundary automatically
    expect(opts.headers).toBeUndefined();
  });

  test('deleteCandidate sends DELETE to /api/candidates/:id/', async () => {
    global.fetch = deleteFetch(204);
    await deleteCandidate('c1');
    expect(global.fetch).toHaveBeenCalledWith('/api/candidates/c1/', { method: 'DELETE' });
  });
});

// ── Applications ──────────────────────────────────────────────────────────────

describe('Applications', () => {
  test('listApplications GETs /api/applications/', async () => {
    global.fetch = okFetch(200, []);
    await listApplications();
    expect(global.fetch).toHaveBeenCalledWith('/api/applications/');
  });

  test('createApplication returns { data, created: true } on 201', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 201,
      json: vi.fn().mockResolvedValue({ id: 'app-1' }),
    });
    const result = await createApplication({ job_id: 'j1', candidate_id: 'c1' });
    expect(result.created).toBe(true);
    expect(result.data.id).toBe('app-1');
  });

  test('createApplication returns { data, created: false } on 200 (idempotent)', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: vi.fn().mockResolvedValue({ id: 'app-1' }),
    });
    const result = await createApplication({ job_id: 'j1', candidate_id: 'c1' });
    expect(result.created).toBe(false);
    expect(result.data.id).toBe('app-1');
  });

  test('createApplication throws on non-2xx', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false, status: 400,
      json: vi.fn().mockResolvedValue({ detail: 'Bad request' }),
    });
    await expect(createApplication({})).rejects.toMatchObject({ status: 400 });
  });

  test('deleteApplication sends DELETE to /api/applications/:id/', async () => {
    global.fetch = deleteFetch(204);
    await deleteApplication('app-1');
    expect(global.fetch).toHaveBeenCalledWith('/api/applications/app-1/', { method: 'DELETE' });
  });

  test('runPipeline POSTs to /api/applications/:id/run/', async () => {
    global.fetch = okFetch(200, { status: 'scored', final_score: 0.85 });
    const result = await runPipeline('app-1');
    expect(result.final_score).toBe(0.85);
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/applications/app-1/run/',
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('fetchScore GETs /api/applications/:id/score/', async () => {
    global.fetch = okFetch(200, { final_score: 0.9 });
    const result = await fetchScore('app-1');
    expect(result.final_score).toBe(0.9);
    expect(global.fetch).toHaveBeenCalledWith('/api/applications/app-1/score/');
  });

  test('fetchScore throws 404 when pipeline is still running', async () => {
    global.fetch = errFetch(404, { detail: 'Not found' });
    await expect(fetchScore('app-1')).rejects.toMatchObject({ status: 404 });
  });

  test('submitReview POSTs payload to /api/applications/:id/reviews/', async () => {
    global.fetch = okFetch(201, { id: 'rev-1' });
    const payload = { reviewer_email: 'hr@co.com', decision: 'approved' };
    await submitReview('app-1', payload);
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/applications/app-1/reviews/',
      expect.objectContaining({
        method: 'POST',
        body:   JSON.stringify(payload),
      })
    );
  });
});

// ── Dashboard ─────────────────────────────────────────────────────────────────

describe('Dashboard', () => {
  test('fetchDashboardStats GETs /api/dashboard/stats/', async () => {
    const stats = { totals: { applications: 10 } };
    global.fetch = okFetch(200, stats);
    const result = await fetchDashboardStats();
    expect(result).toEqual(stats);
    expect(global.fetch).toHaveBeenCalledWith('/api/dashboard/stats/');
  });
});
