/**
 * Unit tests for useJobs hook.
 *
 * BDD scenarios:
 *   Given the hook mounts → loading is true initially
 *   When the API resolves → loading=false, jobs populated, error=null
 *   When the API rejects → loading=false, error set, jobs empty
 *   When refetch is called → API called again
 *   addJob(job) prepends to the list
 *   removeJob(id) filters the job out
 */

import { vi, describe, test, beforeEach, expect } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useJobs } from '../hooks/useJobs.js';

vi.mock('../api/client.js', () => ({
  listJobs: vi.fn(),
}));
import { listJobs } from '../api/client.js';

const JOBS = [
  { id: 'j1', title: 'Senior Engineer', created_at: '2024-01-10T00:00:00Z' },
  { id: 'j2', title: 'Data Analyst',    created_at: '2024-01-12T00:00:00Z' },
];

describe('useJobs', () => {
  beforeEach(() => {
    listJobs.mockReset();
  });

  test('initial state has loading=true, jobs=[], error=null', () => {
    listJobs.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useJobs());
    expect(result.current.loading).toBe(true);
    expect(result.current.jobs).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  test('when API resolves → loading becomes false and jobs are set', async () => {
    listJobs.mockResolvedValue(JOBS);
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.jobs).toEqual(JOBS);
    expect(result.current.error).toBeNull();
  });

  test('when API rejects → loading=false, error set, jobs empty', async () => {
    const err = new Error('Network error');
    listJobs.mockRejectedValue(err);
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe(err);
    expect(result.current.jobs).toEqual([]);
  });

  test('refetch calls listJobs a second time', async () => {
    listJobs.mockResolvedValue(JOBS);
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.refetch(); });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(listJobs).toHaveBeenCalledTimes(2);
  });

  test('addJob prepends a new job to the list', async () => {
    listJobs.mockResolvedValue(JOBS);
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.loading).toBe(false));
    const newJob = { id: 'j3', title: 'ML Engineer', created_at: '2024-02-01T00:00:00Z' };
    act(() => { result.current.addJob(newJob); });
    expect(result.current.jobs[0]).toEqual(newJob);
    expect(result.current.jobs).toHaveLength(3);
  });

  test('removeJob removes the job with the given id', async () => {
    listJobs.mockResolvedValue(JOBS);
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.removeJob('j1'); });
    expect(result.current.jobs).toHaveLength(1);
    expect(result.current.jobs[0].id).toBe('j2');
  });

  test('removeJob with unknown id leaves list unchanged', async () => {
    listJobs.mockResolvedValue(JOBS);
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.removeJob('does-not-exist'); });
    expect(result.current.jobs).toHaveLength(2);
  });

  test('refetch after error can clear it on success', async () => {
    listJobs
      .mockRejectedValueOnce(new Error('Temporary error'))
      .mockResolvedValueOnce(JOBS);
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.error).not.toBeNull());
    act(() => { result.current.refetch(); });
    await waitFor(() => expect(result.current.jobs.length).toBeGreaterThan(0));
    expect(result.current.error).toBeNull();
  });
});
