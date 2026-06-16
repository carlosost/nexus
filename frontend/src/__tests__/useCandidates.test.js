/**
 * Unit tests for useCandidates hook.
 *
 * BDD scenarios:
 *   Given the hook mounts → loading is true initially
 *   When the API resolves → loading=false, candidates populated, error=null
 *   When the API rejects → loading=false, error set, candidates empty
 *   When refetch is called → API called again
 *   addCandidate(c) prepends to the list
 *   removeCandidate(id) filters the candidate out
 */

import { vi, describe, test, beforeEach, expect } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useCandidates } from '../hooks/useCandidates.js';

vi.mock('../api/client.js', () => ({
  listCandidates: vi.fn(),
}));
import { listCandidates } from '../api/client.js';

const CANDIDATES = [
  { id: 'c1', name: 'Alice Chen',  email: 'alice@test.com', created_at: '2024-01-10T00:00:00Z' },
  { id: 'c2', name: 'Bob Johnson', email: 'bob@test.com',   created_at: '2024-01-12T00:00:00Z' },
];

describe('useCandidates', () => {
  beforeEach(() => {
    listCandidates.mockReset();
  });

  test('initial state has loading=true, candidates=[], error=null', () => {
    listCandidates.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCandidates());
    expect(result.current.loading).toBe(true);
    expect(result.current.candidates).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  test('when API resolves → loading=false and candidates are set', async () => {
    listCandidates.mockResolvedValue(CANDIDATES);
    const { result } = renderHook(() => useCandidates());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.candidates).toEqual(CANDIDATES);
    expect(result.current.error).toBeNull();
  });

  test('when API rejects → loading=false, error set, candidates empty', async () => {
    const err = new Error('Network error');
    listCandidates.mockRejectedValue(err);
    const { result } = renderHook(() => useCandidates());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe(err);
    expect(result.current.candidates).toEqual([]);
  });

  test('refetch calls listCandidates a second time', async () => {
    listCandidates.mockResolvedValue(CANDIDATES);
    const { result } = renderHook(() => useCandidates());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.refetch(); });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(listCandidates).toHaveBeenCalledTimes(2);
  });

  test('addCandidate prepends a new candidate to the list', async () => {
    listCandidates.mockResolvedValue(CANDIDATES);
    const { result } = renderHook(() => useCandidates());
    await waitFor(() => expect(result.current.loading).toBe(false));
    const newC = { id: 'c3', name: 'Carol Smith', email: 'carol@test.com', created_at: '2024-02-01T00:00:00Z' };
    act(() => { result.current.addCandidate(newC); });
    expect(result.current.candidates[0]).toEqual(newC);
    expect(result.current.candidates).toHaveLength(3);
  });

  test('removeCandidate removes the candidate with the given id', async () => {
    listCandidates.mockResolvedValue(CANDIDATES);
    const { result } = renderHook(() => useCandidates());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.removeCandidate('c1'); });
    expect(result.current.candidates).toHaveLength(1);
    expect(result.current.candidates[0].id).toBe('c2');
  });

  test('removeCandidate with unknown id leaves list unchanged', async () => {
    listCandidates.mockResolvedValue(CANDIDATES);
    const { result } = renderHook(() => useCandidates());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.removeCandidate('does-not-exist'); });
    expect(result.current.candidates).toHaveLength(2);
  });

  test('refetch after error clears it on success', async () => {
    listCandidates
      .mockRejectedValueOnce(new Error('Temporary'))
      .mockResolvedValueOnce(CANDIDATES);
    const { result } = renderHook(() => useCandidates());
    await waitFor(() => expect(result.current.error).not.toBeNull());
    act(() => { result.current.refetch(); });
    await waitFor(() => expect(result.current.candidates.length).toBeGreaterThan(0));
    expect(result.current.error).toBeNull();
  });
});
