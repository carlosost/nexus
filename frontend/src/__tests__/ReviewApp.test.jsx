/**
 * Integration tests for ReviewApp — migrated from Jest to Vitest.
 * Tests fetch behaviour, error states, and successful submission flow.
 */
import { vi, describe, test, beforeEach, expect } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ReviewApp from '../components/ReviewApp.jsx';

vi.mock('../api/client.js', () => ({
  fetchScore:   vi.fn(),
  submitReview: vi.fn(),
}));
import { fetchScore, submitReview } from '../api/client.js';

const SCORE_DATA = {
  application_id: 'app-001',
  final_score: 0.82,
  confidence: 1.0,
  gate_passed: true,
  gate_outcome: 'pass',
  semantic_score: 0.79,
  rubric_score: 0.84,
  rubric_breakdown: {
    core_skills: 4.5,
    relevant_experience: 4.2,
    scope_impact: 4.0,
    domain_alignment: 3.8,
    education_certs: 3.5,
  },
};

describe('ReviewApp', () => {
  beforeEach(() => {
    fetchScore.mockReset();
    submitReview.mockReset();
  });

  // ── Loading state ─────────────────────────────────────────────────────────
  test('shows loading message while fetching', () => {
    fetchScore.mockReturnValue(new Promise(() => {})); // never resolves
    render(<ReviewApp applicationId="app-001" />);
    expect(screen.getByTestId('loading-message')).toBeInTheDocument();
  });

  // ── Success state ─────────────────────────────────────────────────────────
  test('renders score card after successful fetch', async () => {
    fetchScore.mockResolvedValue(SCORE_DATA);
    render(<ReviewApp applicationId="app-001" />);
    await waitFor(() => expect(screen.getByTestId('final-score')).toBeInTheDocument());
    expect(screen.getByTestId('final-score')).toHaveTextContent('82%');
  });

  test('renders rubric breakdown after fetch', async () => {
    fetchScore.mockResolvedValue(SCORE_DATA);
    render(<ReviewApp applicationId="app-001" />);
    await waitFor(() =>
      expect(screen.getByTestId('criterion-score-core_skills')).toBeInTheDocument()
    );
  });

  test('renders override panel after fetch', async () => {
    fetchScore.mockResolvedValue(SCORE_DATA);
    render(<ReviewApp applicationId="app-001" />);
    await waitFor(() =>
      expect(screen.getByTestId('review-form')).toBeInTheDocument()
    );
  });

  // ── 404 error state ───────────────────────────────────────────────────────
  test('shows pipeline-not-run message on 404', async () => {
    const err = Object.assign(new Error('HTTP 404'), { status: 404 });
    fetchScore.mockRejectedValue(err);
    render(<ReviewApp applicationId="app-999" />);
    await waitFor(() =>
      expect(screen.getByTestId('error-message')).toHaveTextContent('No score available yet')
    );
  });

  test('shows generic error on non-404 failure', async () => {
    const err = Object.assign(new Error('HTTP 500'), { status: 500 });
    fetchScore.mockRejectedValue(err);
    render(<ReviewApp applicationId="app-001" />);
    await waitFor(() =>
      expect(screen.getByTestId('error-message')).toBeInTheDocument()
    );
  });

  // ── Successful submission ────────────────────────────────────────────────
  test('shows success message after approve submission', async () => {
    fetchScore.mockResolvedValue(SCORE_DATA);
    submitReview.mockResolvedValue({ id: 'rev-1', decision: 'approve' });

    render(<ReviewApp applicationId="app-001" />);
    await waitFor(() => screen.getByTestId('review-form'));

    await userEvent.type(screen.getByTestId('reviewer-email'), 'alice@co.com');
    fireEvent.click(screen.getByTestId('submit-button'));

    await waitFor(() =>
      expect(screen.getByTestId('success-message')).toBeInTheDocument()
    );
    expect(screen.queryByTestId('review-form')).not.toBeInTheDocument();
  });

  // ── Submit error ──────────────────────────────────────────────────────────
  test('shows "Submission failed" on API error', async () => {
    fetchScore.mockResolvedValue(SCORE_DATA);
    const apiErr = Object.assign(new Error('HTTP 500'), { status: 500 });
    submitReview.mockRejectedValue(apiErr);

    render(<ReviewApp applicationId="app-001" />);
    await waitFor(() => screen.getByTestId('review-form'));

    await userEvent.type(screen.getByTestId('reviewer-email'), 'alice@co.com');
    fireEvent.click(screen.getByTestId('submit-button'));

    await waitFor(() =>
      expect(screen.getByTestId('submit-error-message')).toHaveTextContent('Submission failed')
    );
    expect(screen.getByTestId('review-form')).toBeInTheDocument();
  });

  test('fetches score using the provided applicationId', async () => {
    fetchScore.mockResolvedValue(SCORE_DATA);
    render(<ReviewApp applicationId="app-001" />);
    await waitFor(() => expect(fetchScore).toHaveBeenCalledWith('app-001'));
  });

  test('shows error when applicationId is null', async () => {
    render(<ReviewApp applicationId={null} />);
    await waitFor(() =>
      expect(screen.getByTestId('error-message')).toBeInTheDocument()
    );
  });
});
