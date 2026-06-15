/**
 * Unit tests for useDashboardStats hook.
 *
 * BDD scenarios:
 *   Given the hook mounts → loading is true initially
 *   When the API resolves → loading becomes false, stats is populated, error is null
 *   When the API rejects → loading becomes false, stats remains null, error is set
 *   When refetch is called → API is called again
 *   Given multiple rapid remounts → only one request in flight per render cycle
 */

import { vi, describe, test, beforeEach, expect } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useDashboardStats } from '../hooks/useDashboardStats.js';

vi.mock('../api/client.js', () => ({
  fetchDashboardStats: vi.fn(),
}));
import { fetchDashboardStats } from '../api/client.js';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const STATS_PAYLOAD = {
  totals: {
    applications:     142,
    candidates:       57,
    jobs:             12,
    active_jobs:      18,
    llm_success_rate: 94.2,
  },
  application_status_distribution: [
    { status: 'pending', label: 'Pending', count: 23 },
  ],
  job_execution_funnel: [
    { status: 'completed', label: 'Completed', count: 84 },
  ],
  llm_resilience: {
    time_series: [
      { date: '2024-01-15', primary: 99, fallback: 0 },
    ],
  },
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useDashboardStats', () => {
  beforeEach(() => {
    fetchDashboardStats.mockReset();
  });

  // ── Initial state ──────────────────────────────────────────────────────────
  test('Initial state has loading=true, stats=null, error=null', () => {
    fetchDashboardStats.mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useDashboardStats());
    expect(result.current.loading).toBe(true);
    expect(result.current.stats).toBeNull();
    expect(result.current.error).toBeNull();
  });

  test('refetch function is exposed from the start', () => {
    fetchDashboardStats.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useDashboardStats());
    expect(typeof result.current.refetch).toBe('function');
  });

  // ── Success path ──────────────────────────────────────────────────────────
  test('When API resolves → loading becomes false', async () => {
    fetchDashboardStats.mockResolvedValue(STATS_PAYLOAD);
    const { result } = renderHook(() => useDashboardStats());
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  test('When API resolves → stats is set to the payload', async () => {
    fetchDashboardStats.mockResolvedValue(STATS_PAYLOAD);
    const { result } = renderHook(() => useDashboardStats());
    await waitFor(() => expect(result.current.stats).not.toBeNull());
    expect(result.current.stats.totals.applications).toBe(142);
    expect(result.current.stats.totals.llm_success_rate).toBe(94.2);
  });

  test('When API resolves → error remains null', async () => {
    fetchDashboardStats.mockResolvedValue(STATS_PAYLOAD);
    const { result } = renderHook(() => useDashboardStats());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
  });

  // ── Error path ────────────────────────────────────────────────────────────
  test('When API rejects → loading becomes false', async () => {
    fetchDashboardStats.mockRejectedValue(new Error('Network error'));
    const { result } = renderHook(() => useDashboardStats());
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  test('When API rejects → error is set to the thrown error', async () => {
    const err = new Error('Service unavailable');
    fetchDashboardStats.mockRejectedValue(err);
    const { result } = renderHook(() => useDashboardStats());
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error.message).toBe('Service unavailable');
  });

  test('When API rejects → stats remains null', async () => {
    fetchDashboardStats.mockRejectedValue(new Error('500'));
    const { result } = renderHook(() => useDashboardStats());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.stats).toBeNull();
  });

  // ── refetch ───────────────────────────────────────────────────────────────
  test('When refetch is called → fetchDashboardStats is called a second time', async () => {
    fetchDashboardStats.mockResolvedValue(STATS_PAYLOAD);
    const { result } = renderHook(() => useDashboardStats());
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => { result.current.refetch(); });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(fetchDashboardStats).toHaveBeenCalledTimes(2);
  });

  test('When refetch is called → loading resets to true during the new request', async () => {
    let resolve1;
    fetchDashboardStats
      .mockResolvedValueOnce(STATS_PAYLOAD)
      .mockReturnValueOnce(new Promise((res) => { resolve1 = res; }));

    const { result } = renderHook(() => useDashboardStats());
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => { result.current.refetch(); });
    expect(result.current.loading).toBe(true);

    act(() => { resolve1(STATS_PAYLOAD); });
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  test('When refetch is called after an error → previous error is cleared on success', async () => {
    fetchDashboardStats
      .mockRejectedValueOnce(new Error('Transient error'))
      .mockResolvedValueOnce(STATS_PAYLOAD);

    const { result } = renderHook(() => useDashboardStats());
    await waitFor(() => expect(result.current.error).not.toBeNull());

    act(() => { result.current.refetch(); });
    await waitFor(() => expect(result.current.stats).not.toBeNull());

    expect(result.current.error).toBeNull();
  });

  // ── API is called on mount ────────────────────────────────────────────────
  test('fetchDashboardStats is called once on mount', async () => {
    fetchDashboardStats.mockResolvedValue(STATS_PAYLOAD);
    renderHook(() => useDashboardStats());
    await waitFor(() => expect(fetchDashboardStats).toHaveBeenCalledTimes(1));
  });
});
