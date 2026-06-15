/**
 * useCandidates — fetches the candidates list and exposes an append helper.
 *
 * Used by:
 *   - AssociationModal        (dropdown options)
 *   - CandidateIngestionModal (refetch after create)
 */

import { useState, useEffect, useCallback } from 'react';
import { listCandidates } from '../api/client.js';

export function useCandidates() {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);

  const refetch = useCallback(() => {
    setLoading(true);
    listCandidates()
      .then((data) => { setCandidates(data); setError(null); })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refetch(); }, [refetch]);

  /** Prepend a freshly-created candidate (Settings: after create). */
  const addCandidate = useCallback((candidate) => {
    setCandidates((prev) => [candidate, ...prev]);
  }, []);

  /** Remove a candidate by id (Settings: after DELETE). */
  const removeCandidate = useCallback((id) => {
    setCandidates((prev) => prev.filter((c) => c.id !== id));
  }, []);

  return { candidates, loading, error, refetch, addCandidate, removeCandidate };
}
