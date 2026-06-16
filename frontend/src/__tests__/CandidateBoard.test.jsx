/**
 * Unit tests for CandidateBoard settings panel.
 *
 * Mirrors the JobBoard test suite structure.
 * Covers: list rendering, empty/loading/error states, expand/collapse,
 * delete confirmation (cascade warning), and Add Candidate button.
 */

import { vi, describe, test, beforeEach, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CandidateBoard from '../components/settings/CandidateBoard.jsx';

vi.mock('../api/client.js', () => ({
  deleteCandidate: vi.fn(),
  getCandidate:    vi.fn(),
}));
import { deleteCandidate, getCandidate } from '../api/client.js';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const CANDIDATES = [
  { id: 'c1', name: 'Alice Chen',  email: 'alice@test.com', created_at: '2024-01-10T00:00:00Z' },
  { id: 'c2', name: 'Bob Johnson', email: 'bob@test.com',   created_at: '2024-01-12T00:00:00Z' },
];

const CANDIDATE_WITH_RESUME = {
  id:            'c3',
  name:          'Carol Smith',
  email:         'carol@test.com',
  created_at:    '2024-02-01T00:00:00Z',
  resume_parsed: {
    experience: 'Led backend development at Acme Corp.',
    skills:     'Python, Django, PostgreSQL',
  },
};

function renderBoard(overrides = {}) {
  const props = {
    candidates: CANDIDATES,
    loading:    false,
    error:      null,
    onAdd:      vi.fn(),
    onRemove:   vi.fn(),
    ...overrides,
  };
  return render(<CandidateBoard {...props} />);
}

describe('CandidateBoard', () => {
  beforeEach(() => {
    deleteCandidate.mockReset();
    getCandidate.mockReset();
    // Default: return the candidate with resume data
    getCandidate.mockResolvedValue(CANDIDATE_WITH_RESUME);
  });

  // ── List rendering ───────────────────────────────────────────────────────────

  test('renders a row for each candidate', () => {
    renderBoard();
    expect(screen.getByText('Alice Chen')).toBeInTheDocument();
    expect(screen.getByText('Bob Johnson')).toBeInTheDocument();
  });

  test('shows email for each candidate', () => {
    renderBoard();
    expect(screen.getByText('alice@test.com')).toBeInTheDocument();
  });

  // ── States ───────────────────────────────────────────────────────────────────

  test('shows loading indicator when loading=true', () => {
    renderBoard({ loading: true, candidates: [] });
    expect(screen.getByTestId('candidate-board-loading')).toBeInTheDocument();
  });

  test('shows error state when error is set', () => {
    renderBoard({ error: new Error('Network fail'), candidates: [] });
    expect(screen.getByTestId('candidate-board-error')).toBeInTheDocument();
    expect(screen.getByText(/failed to load candidates/i)).toBeInTheDocument();
  });

  test('shows empty state when candidates list is empty', () => {
    renderBoard({ candidates: [] });
    expect(screen.getByTestId('candidate-board-empty')).toBeInTheDocument();
  });

  test('hides table when loading', () => {
    renderBoard({ loading: true, candidates: [] });
    expect(screen.queryByTestId('candidate-table')).not.toBeInTheDocument();
  });

  // ── Add Candidate button ─────────────────────────────────────────────────────

  test('clicking + Add Candidate opens the ingestion modal', () => {
    renderBoard();
    fireEvent.click(screen.getByTestId('candidate-create-btn'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  // ── Expand / collapse ────────────────────────────────────────────────────────

  test('clicking expand button shows the detail panel', async () => {
    renderBoard({ candidates: [CANDIDATE_WITH_RESUME] });
    fireEvent.click(screen.getByTestId(`candidate-expand-${CANDIDATE_WITH_RESUME.id}`));
    await waitFor(() =>
      expect(screen.getByTestId(`candidate-detail-${CANDIDATE_WITH_RESUME.id}`)).toBeInTheDocument()
    );
  });

  test('clicking expand button again collapses the detail panel', async () => {
    renderBoard({ candidates: [CANDIDATE_WITH_RESUME] });
    const btn = screen.getByTestId(`candidate-expand-${CANDIDATE_WITH_RESUME.id}`);
    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.getByTestId(`candidate-detail-${CANDIDATE_WITH_RESUME.id}`)).toBeInTheDocument()
    );
    fireEvent.click(btn);
    expect(screen.queryByTestId(`candidate-detail-${CANDIDATE_WITH_RESUME.id}`)).not.toBeInTheDocument();
  });

  test('detail panel renders parsed resume sections', async () => {
    renderBoard({ candidates: [CANDIDATE_WITH_RESUME] });
    fireEvent.click(screen.getByTestId(`candidate-expand-${CANDIDATE_WITH_RESUME.id}`));
    expect(getCandidate).toHaveBeenCalledWith(CANDIDATE_WITH_RESUME.id);
    await waitFor(() => expect(screen.getByText(/led backend development/i)).toBeInTheDocument());
    expect(screen.getByText(/Python, Django/)).toBeInTheDocument();
  });

  test('detail panel shows fallback text when resume_parsed is empty', async () => {
    const noResume = { ...CANDIDATES[0] };
    getCandidate.mockResolvedValue({ ...noResume, resume_parsed: {} });
    renderBoard({ candidates: [noResume] });
    fireEvent.click(screen.getByTestId(`candidate-expand-${noResume.id}`));
    await waitFor(() => expect(screen.getByText(/no parsed sections/i)).toBeInTheDocument());
  });

  // ── Delete flow ──────────────────────────────────────────────────────────────

  test('clicking Delete opens the confirmation modal', () => {
    renderBoard();
    fireEvent.click(screen.getByTestId('candidate-delete-c1'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  test('confirmation modal shows cascade warning', () => {
    renderBoard();
    fireEvent.click(screen.getByTestId('candidate-delete-c1'));
    expect(screen.getByText(/applications linked to this candidate/i)).toBeInTheDocument();
  });

  test('cancelling delete closes the modal without calling onRemove', () => {
    const onRemove = vi.fn();
    renderBoard({ onRemove });
    fireEvent.click(screen.getByTestId('candidate-delete-c1'));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(onRemove).not.toHaveBeenCalled();
  });

  test('confirming delete calls deleteCandidate and onRemove', async () => {
    deleteCandidate.mockResolvedValue(null);
    const onRemove = vi.fn();
    renderBoard({ onRemove });
    fireEvent.click(screen.getByTestId('candidate-delete-c1'));
    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    await waitFor(() => expect(onRemove).toHaveBeenCalledWith('c1'));
    expect(deleteCandidate).toHaveBeenCalledWith('c1');
  });
});
