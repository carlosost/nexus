/**
 * useJobs — fetches the jobs list and exposes an append helper.
 *
 * Used by:
 *   - AssociationModal  (dropdown options)
 *   - JobIngestionModal (refetch after create)
 */

import { useState, useEffect, useCallback } from 'react';
import { listJobs } from '../api/client.js';

export function useJobs() {
  const [jobs, setJobs]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const refetch = useCallback(() => {
    setLoading(true);
    listJobs()
      .then((data) => { setJobs(data); setError(null); })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refetch(); }, [refetch]);

  /** Prepend a freshly-created job to the list (Settings: after create). */
  const addJob = useCallback((job) => {
    setJobs((prev) => [job, ...prev]);
  }, []);

  /** Remove a job by id (Settings: after DELETE). */
  const removeJob = useCallback((id) => {
    setJobs((prev) => prev.filter((j) => j.id !== id));
  }, []);

  return { jobs, loading, error, refetch, addJob, removeJob };
}
