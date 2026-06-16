/**
 * useApplications — manages the application list with async pipeline execution.
 *
 * State shape:
 *   applications  ApplicationRow[]   — current list, mutated optimistically
 *   loading       boolean            — true during initial fetch
 *   error         Error | null       — fetch error (null on success)
 *   pollingIds    Set<string>        — IDs whose pipeline run is in flight
 *   selected      Set<string>        — IDs checked in the table
 *
 * Async execution model:
 *   1. runSelected() immediately flips each selected row's status to the
 *      local sentinel "processing" and fires POST /run/ for all IDs
 *      concurrently via Promise.allSettled.
 *   2. A setInterval poll fires every POLL_INTERVAL_MS while pollingIds is
 *      non-empty.  On each tick it calls GET /score/ for each polled ID;
 *      a 200 response means the pipeline completed — the row is updated and
 *      the ID is removed from the polling set.  A 404 means still running.
 *      Any other error clears the ID from polling to avoid infinite loops.
 *   3. Because POST /run/ is synchronous on the backend, it will usually
 *      resolve before the first poll fires.  The poll is a safety net for
 *      future async migration (Celery) and for tab-regained-focus refresh.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { listApplications, runPipeline, fetchScore } from '../api/client.js';

const POLL_INTERVAL_MS   = 3_000;
const REFRESH_INTERVAL_MS = 20_000;

export function useApplications() {
  const [applications, setApplications] = useState([]);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState(null);
  const [pollingIds, setPollingIds]     = useState(new Set());
  const [selected, setSelected]         = useState(new Set());
  const [runErrors, setRunErrors]       = useState(new Map());

  // Stable ref to pollingIds so the interval callback never sees stale state
  const pollingRef = useRef(pollingIds);
  useEffect(() => { pollingRef.current = pollingIds; }, [pollingIds]);

  // ── Initial fetch ─────────────────────────────────────────────────────────

  const refetch = useCallback(() => {
    setLoading(true);
    listApplications()
      .then((data) => { setApplications(data); setError(null); })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refetch(); }, [refetch]);

  // ── Silent background refresh ─────────────────────────────────────────────
  // Rows whose pipeline is in-flight keep their optimistic state; all others
  // are replaced with fresh server data.
  useEffect(() => {
    const id = setInterval(() => {
      listApplications().then((fresh) => {
        setApplications((prev) => {
          const inFlight = pollingRef.current;
          return fresh.map((serverRow) => {
            if (inFlight.has(serverRow.id)) {
              return prev.find((r) => r.id === serverRow.id) ?? serverRow;
            }
            return serverRow;
          });
        });
      }).catch(() => { /* silent — keep showing stale data on network error */ });
    }, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  // ── Polling ───────────────────────────────────────────────────────────────

  useEffect(() => {
    if (pollingIds.size === 0) return;

    const interval = setInterval(async () => {
      const current = pollingRef.current;
      if (current.size === 0) return;

      const resolved = new Set();

      await Promise.allSettled(
        [...current].map(async (id) => {
          try {
            const score = await fetchScore(id);
            // Pipeline completed — patch the row with real data
            setApplications((prev) =>
              prev.map((app) =>
                app.id === id
                  ? {
                      ...app,
                      status: 'scored',
                      final_score: score.final_score,
                      is_evaluated_via_fallback: score.is_evaluated_via_fallback ?? false,
                    }
                  : app
              )
            );
            resolved.add(id);
          } catch (err) {
            if (err.status === 404) {
              // Still running — keep polling
            } else {
              // Unexpected error — stop polling this ID to avoid infinite loop
              setApplications((prev) =>
                prev.map((app) =>
                  app.id === id ? { ...app, status: 'pending' } : app
                )
              );
              resolved.add(id);
            }
          }
        })
      );

      if (resolved.size > 0) {
        setPollingIds((prev) => {
          const next = new Set(prev);
          resolved.forEach((id) => next.delete(id));
          return next;
        });
      }
    }, POLL_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [pollingIds]);

  // ── Selection helpers ─────────────────────────────────────────────────────

  const toggleSelect = useCallback((id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelected((prev) =>
      prev.size === applications.length
        ? new Set()
        : new Set(applications.map((a) => a.id))
    );
  }, [applications]);

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  // ── Pipeline trigger ──────────────────────────────────────────────────────

  const runSelected = useCallback(() => {
    const ids = [...selected];
    if (ids.length === 0) return;

    // Clear previous errors for these IDs
    setRunErrors((prev) => {
      const m = new Map(prev);
      ids.forEach((id) => m.delete(id));
      return m;
    });

    // 1. Optimistic update: flip all selected rows to "processing"
    setApplications((prev) =>
      prev.map((app) =>
        ids.includes(app.id) ? { ...app, status: 'processing' } : app
      )
    );
    setPollingIds((prev) => new Set([...prev, ...ids]));
    clearSelection();

    // 2. Fire all pipeline runs concurrently
    Promise.allSettled(ids.map((id) => runPipeline(id))).then((results) => {
      results.forEach((result, i) => {
        const id = ids[i];
        if (result.status === 'fulfilled') {
          // Run completed synchronously — remove from polling, patch row
          setApplications((prev) =>
            prev.map((app) =>
              app.id === id
                ? {
                    ...app,
                    status: result.value?.status ?? 'scored',
                    final_score: result.value?.final_score ?? null,
                  }
                : app
            )
          );
          setPollingIds((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          });
        } else {
          // Run failed — revert status and surface error
          setApplications((prev) =>
            prev.map((app) => (app.id === id ? { ...app, status: 'pending' } : app))
          );
          setPollingIds((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          });
          const err = result.reason;
          const msg = err?.body?.detail ?? err?.message ?? 'Pipeline run failed';
          setRunErrors((prev) => new Map([...prev, [id, msg]]));
        }
      });
    });
  }, [selected, clearSelection]);

  const runSingle = useCallback((id) => {
    setRunErrors((prev) => { const m = new Map(prev); m.delete(id); return m; });
    setApplications((prev) =>
      prev.map((app) => (app.id === id ? { ...app, status: 'processing' } : app))
    );
    setPollingIds((prev) => new Set([...prev, id]));

    runPipeline(id)
      .then((result) => {
        setApplications((prev) =>
          prev.map((app) =>
            app.id === id
              ? { ...app, status: result?.status ?? 'scored', final_score: result?.final_score ?? null }
              : app
          )
        );
        setPollingIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      })
      .catch((err) => {
        setApplications((prev) =>
          prev.map((app) => (app.id === id ? { ...app, status: 'pending' } : app))
        );
        setPollingIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
        const msg = err?.body?.detail ?? err?.message ?? 'Pipeline run failed';
        setRunErrors((prev) => new Map([...prev, [id, msg]]));
      });
  }, []);

  // ── Row append (after create) ──────────────────────────────────────────────

  const addApplication = useCallback((app) => {
    setApplications((prev) => [app, ...prev]);
  }, []);

  return {
    applications,
    loading,
    error,
    pollingIds,
    runErrors,
    selected,
    toggleSelect,
    toggleSelectAll,
    clearSelection,
    runSelected,
    runSingle,
    refetch,
    addApplication,
  };
}
