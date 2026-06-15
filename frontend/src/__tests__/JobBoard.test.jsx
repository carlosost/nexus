/**
 * Unit tests for the JobBoard settings panel.
 *
 * Covers: list rendering, empty state, delete confirmation modal,
 * detail panel expand/collapse, and field display.
 */

import { vi, describe, test, beforeEach, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import JobBoard from '../components/settings/JobBoard.jsx';

const JOBS = [
  {
    id:          'job-001',
    title:       'Senior Backend Engineer',
    created_at:  '2024-01-10T00:00:00Z',
  },
  {
    id:          'job-002',
    title:       'Principal Data Engineer',
    created_at:  '2024-01-12T00:00:00Z',
  },
];

const FULL_JOB = {
  id:               'job-001',
  title:            'Senior Backend Engineer',
  description:      'We need a strong backend engineer.',
  requirements_raw: { required_skills: ['Python', 'Django'] },
  must_haves:       { min_experience: { type: 'years_experience', minimum_years: 5 } },
};

function renderBoard(overrides = {}) {
  const props = {
    jobs:       JOBS,
    loading:    false,
    error:      null,
    onAdd:    vi.fn(),
    onRemove: vi.fn(),
    ...overrides,
  };
  return render(<JobBoard {...props} />);
}

describe('JobBoard', () => {

  test('renders a row for each job', () => {
    renderBoard();
    expect(screen.getByText('Senior Backend Engineer')).toBeInTheDocument();
    expect(screen.getByText('Principal Data Engineer')).toBeInTheDocument();
  });

  test('shows empty state when jobs list is empty', () => {
    renderBoard({ jobs: [] });
    expect(screen.getByText(/no jobs/i)).toBeInTheDocument();
  });

  test('loading skeleton shown when loading=true', () => {
    renderBoard({ loading: true });
    expect(screen.getByTestId('jobs-loading-skeleton')).toBeInTheDocument();
  });

  test('error banner shown when error is set', () => {
    renderBoard({ error: new Error('Network error') });
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  test('clicking Add Job opens the ingestion modal', () => {
    const onAdd = vi.fn();
    renderBoard({ onAdd });
    fireEvent.click(screen.getByRole('button', { name: /add job/i }));
    expect(onAdd).toHaveBeenCalled();
  });

  test('clicking Delete shows cascade confirmation modal', () => {
    renderBoard();
    const deleteButtons = screen.getAllByRole('button', { name: /delete/i });
    fireEvent.click(deleteButtons[0]);
    expect(screen.getByText(/this will also delete/i)).toBeInTheDocument();
  });

  test('confirming delete calls onRemove with the job id', async () => {
    const onRemove = vi.fn();
    renderBoard({ onRemove });
    fireEvent.click(screen.getAllByRole('button', { name: /delete/i })[0]);
    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    await waitFor(() => expect(onRemove).toHaveBeenCalledWith('job-001'));
  });

  test('cancelling delete does not call onRemove', () => {
    const onRemove = vi.fn();
    renderBoard({ onRemove });
    fireEvent.click(screen.getAllByRole('button', { name: /delete/i })[0]);
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onRemove).not.toHaveBeenCalled();
  });

  test('expanding a job row shows description', async () => {
    renderBoard({ jobs: [FULL_JOB] });
    fireEvent.click(screen.getByRole('button', { name: /expand/i }));
    await waitFor(() =>
      expect(screen.getByText(/strong backend engineer/i)).toBeInTheDocument()
    );
  });

  test('expanding shows must_haves JSON block', async () => {
    renderBoard({ jobs: [FULL_JOB] });
    fireEvent.click(screen.getByRole('button', { name: /expand/i }));
    await waitFor(() =>
      expect(screen.getByText(/years_experience/i)).toBeInTheDocument()
    );
  });

  test('second expand click collapses the detail panel', async () => {
    renderBoard({ jobs: [FULL_JOB] });
    const expandBtn = screen.getByRole('button', { name: /expand/i });
    fireEvent.click(expandBtn);
    await waitFor(() =>
      expect(screen.getByText(/strong backend engineer/i)).toBeInTheDocument()
    );
    fireEvent.click(expandBtn);
    await waitFor(() =>
      expect(screen.queryByText(/strong backend engineer/i)).not.toBeInTheDocument()
    );
  });
});
