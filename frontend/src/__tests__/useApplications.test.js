/**
 * Unit tests for useApplications hook.
 *
 * Covers: initial fetch, success, error, background refresh, polling lifecycle,
 * selection helpers, runSingle, runSelected, and addApplication.
 *
 * Fake timers are used to control polling and background-refresh intervals
 * without blocking real time.
 */

import { vi, describe, test, beforeEach, afterEach, expect } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useApplications } from '../hooks/useApplications.js';

vi.mock('../api/client.js', () => ({
  listApplications: vi.fn(),
  runPipeline:      vi.fn(),
  fetchScore:       vi.fn(),
}));
import { listApplications, runPipeline, fetchScore } from '../api/client.js';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const APP = {
  id:                        'app-1',
  candidate_name:            'Alice Chen',
  candidate_email:           'alice@test.com',
  job_title:                 'Senior Data Engineer',
  status:                    'pending',
  final_score:               null,
  is_evaluated_via_fallback: false,
  created_at:                '2024-01-12T00:00:00Z',
  updated_at:                '2024-01-15T00:00:00Z',
};

const APP_2 = { ...APP, id: 'app-2', candidate_name: 'Bob Johnson' };

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  // shouldAdvanceTime keeps the fake clock ticking in real time so waitFor()
  // (which uses setTimeout internally) still works, while vi.advanceTimersByTime()
  // can still fast-forward the clock in polling tests.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  listApplications.mockReset();
  runPipeline.mockReset();
  fetchScore.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

// ── Initial state and fetch ────────────────────────────────────────────────────

describe('Initial fetch', () => {
  test('loading is true before the API resolves', () => {
    listApplications.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useApplications());
    expect(result.current.loading).toBe(true);
    expect(result.current.applications).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  test('when API resolves → loading=false, applications populated', async () => {
    listApplications.mockResolvedValue([APP]);
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.applications).toEqual([APP]);
    expect(result.current.error).toBeNull();
  });

  test('when API rejects → loading=false, error set, applications empty', async () => {
    const err = new Error('Network error');
    listApplications.mockRejectedValue(err);
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe(err);
    expect(result.current.applications).toEqual([]);
  });

  test('refetch calls listApplications again', async () => {
    listApplications.mockResolvedValue([APP]);
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.refetch(); });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(listApplications).toHaveBeenCalledTimes(2);
  });
});

// ── addApplication ─────────────────────────────────────────────────────────────

describe('addApplication', () => {
  test('prepends new application to the list', async () => {
    listApplications.mockResolvedValue([APP]);
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    const newApp = { ...APP, id: 'app-new', candidate_name: 'Carol' };
    act(() => { result.current.addApplication(newApp); });
    expect(result.current.applications[0].id).toBe('app-new');
    expect(result.current.applications).toHaveLength(2);
  });
});

// ── Selection helpers ─────────────────────────────────────────────────────────

describe('Selection', () => {
  test('toggleSelect adds an id to selected', async () => {
    listApplications.mockResolvedValue([APP]);
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.toggleSelect('app-1'); });
    expect(result.current.selected.has('app-1')).toBe(true);
  });

  test('toggleSelect removes an already-selected id', async () => {
    listApplications.mockResolvedValue([APP]);
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.toggleSelect('app-1'); });
    act(() => { result.current.toggleSelect('app-1'); });
    expect(result.current.selected.has('app-1')).toBe(false);
  });

  test('toggleSelectAll selects all when none are selected', async () => {
    listApplications.mockResolvedValue([APP, APP_2]);
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.toggleSelectAll(); });
    expect(result.current.selected.size).toBe(2);
  });

  test('toggleSelectAll deselects all when all are selected', async () => {
    listApplications.mockResolvedValue([APP, APP_2]);
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.toggleSelectAll(); }); // select all
    act(() => { result.current.toggleSelectAll(); }); // deselect all
    expect(result.current.selected.size).toBe(0);
  });

  test('clearSelection empties the selection set', async () => {
    listApplications.mockResolvedValue([APP]);
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.toggleSelect('app-1'); });
    act(() => { result.current.clearSelection(); });
    expect(result.current.selected.size).toBe(0);
  });
});

// ── runSingle ─────────────────────────────────────────────────────────────────

describe('runSingle', () => {
  test('optimistically sets status to "processing"', async () => {
    listApplications.mockResolvedValue([APP]);
    runPipeline.mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.runSingle('app-1'); });
    expect(result.current.applications[0].status).toBe('processing');
  });

  test('adds id to pollingIds immediately', async () => {
    listApplications.mockResolvedValue([APP]);
    runPipeline.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.runSingle('app-1'); });
    expect(result.current.pollingIds.has('app-1')).toBe(true);
  });

  test('on success: patches row with result and removes from pollingIds', async () => {
    listApplications.mockResolvedValue([APP]);
    runPipeline.mockResolvedValue({ status: 'scored', final_score: 0.9 });
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.runSingle('app-1'); });
    await waitFor(() => expect(result.current.pollingIds.has('app-1')).toBe(false));
    expect(result.current.applications[0].status).toBe('scored');
    expect(result.current.applications[0].final_score).toBe(0.9);
  });

  test('on failure: reverts to "pending" and sets runError', async () => {
    listApplications.mockResolvedValue([APP]);
    const err = Object.assign(new Error('Run failed'), { body: { detail: 'Pipeline error' } });
    runPipeline.mockRejectedValue(err);
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.runSingle('app-1'); });
    await waitFor(() => expect(result.current.runErrors.has('app-1')).toBe(true));
    expect(result.current.applications[0].status).toBe('pending');
    expect(result.current.runErrors.get('app-1')).toBe('Pipeline error');
  });
});

// ── runSelected ──────────────────────────────────────────────────────────────

describe('runSelected', () => {
  test('does nothing when selection is empty', async () => {
    listApplications.mockResolvedValue([APP]);
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.runSelected(); });
    expect(runPipeline).not.toHaveBeenCalled();
  });

  test('fires runPipeline for each selected id', async () => {
    listApplications.mockResolvedValue([APP, APP_2]);
    runPipeline.mockResolvedValue({ status: 'scored', final_score: 0.8 });
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.toggleSelect('app-1'); });
    act(() => { result.current.toggleSelect('app-2'); });
    act(() => { result.current.runSelected(); });
    await waitFor(() => expect(runPipeline).toHaveBeenCalledTimes(2));
  });

  test('clears selection after run is triggered', async () => {
    listApplications.mockResolvedValue([APP]);
    runPipeline.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.toggleSelect('app-1'); });
    act(() => { result.current.runSelected(); });
    expect(result.current.selected.size).toBe(0);
  });

  test('on run failure: reverts status and stores error message', async () => {
    listApplications.mockResolvedValue([APP]);
    const err = new Error('Server error');
    runPipeline.mockRejectedValue(err);
    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.toggleSelect('app-1'); });
    act(() => { result.current.runSelected(); });
    await waitFor(() => expect(result.current.runErrors.has('app-1')).toBe(true));
    expect(result.current.applications[0].status).toBe('pending');
  });
});

// ── Polling ───────────────────────────────────────────────────────────────────

describe('Polling', () => {
  test('after 3 s tick: 200 from fetchScore patches row and removes from pollingIds', async () => {
    listApplications.mockResolvedValue([APP]);
    runPipeline.mockReturnValue(new Promise(() => {})); // never completes synchronously
    fetchScore.mockResolvedValue({ final_score: 0.77, is_evaluated_via_fallback: false });

    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));

    // Trigger polling by adding to pollingIds
    act(() => { result.current.runSingle('app-1'); });
    expect(result.current.pollingIds.has('app-1')).toBe(true);

    // Fire the polling interval and flush the async fetchScore chain
    await act(async () => { vi.advanceTimersByTime(3000); });
    await waitFor(() => expect(result.current.pollingIds.has('app-1')).toBe(false));
    expect(result.current.applications[0].status).toBe('scored');
    expect(result.current.applications[0].final_score).toBe(0.77);
  });

  test('404 from fetchScore keeps the id in pollingIds', async () => {
    listApplications.mockResolvedValue([APP]);
    runPipeline.mockReturnValue(new Promise(() => {}));
    const notFound = Object.assign(new Error('Not found'), { status: 404 });
    fetchScore.mockRejectedValue(notFound);

    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.runSingle('app-1'); });

    await act(async () => { vi.advanceTimersByTime(3000); });
    // 404 means still running — id must still be in the polling set
    await waitFor(() => expect(fetchScore).toHaveBeenCalled());
    expect(result.current.pollingIds.has('app-1')).toBe(true);
  });

  test('unexpected error from fetchScore removes id from pollingIds', async () => {
    listApplications.mockResolvedValue([APP]);
    runPipeline.mockReturnValue(new Promise(() => {}));
    const serverErr = Object.assign(new Error('Server error'), { status: 500 });
    fetchScore.mockRejectedValue(serverErr);

    const { result } = renderHook(() => useApplications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.runSingle('app-1'); });

    await act(async () => { vi.advanceTimersByTime(3000); });
    await waitFor(() => expect(result.current.pollingIds.has('app-1')).toBe(false));
    expect(result.current.applications[0].status).toBe('pending');
  });
});
