/**
 * useDashboardStats — fetches aggregated telemetry from GET /api/dashboard/stats/
 *
 * Returns:
 *   stats   — DashboardStats payload (null while loading or on error)
 *   loading — true on the first fetch and on any manual refetch
 *   error   — Error instance if the last fetch failed, otherwise null
 *   refetch — imperative trigger to re-run the fetch (e.g. on a Refresh button)
 *
 * Background polling: silently re-fetches every REFRESH_INTERVAL_MS without
 * touching the loading state, so the UI does not flash on each tick.
 */

import { useState, useEffect, useCallback } from 'react';
import { fetchDashboardStats } from '../api/client.js';

const REFRESH_INTERVAL_MS = 20_000;

export function useDashboardStats() {
  const [stats,   setStats]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  const refetch = useCallback(() => {
    setLoading(true);
    fetchDashboardStats()
      .then((data) => { setStats(data); setError(null); })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refetch(); }, [refetch]);

  // Silent background refresh — no loading state change so UI stays stable.
  useEffect(() => {
    const id = setInterval(() => {
      fetchDashboardStats()
        .then((data) => { setStats(data); setError(null); })
        .catch(setError);
    }, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  return { stats, loading, error, refetch };
}
