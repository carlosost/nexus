/**
 * Unit tests for ApplicationTable.
 *
 * Covers: loading, error, and empty states; row rendering; score/date
 * formatting; checkbox selection; run-error indicator; FallbackAlert;
 * and action button callbacks.
 */

import { vi, describe, test, beforeEach, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ApplicationTable from '../components/ApplicationTable.jsx';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const APP = {
  id:                        'app-1',
  candidate_name:            'Alice Chen',
  candidate_email:           'alice@example.com',
  job_title:                 'Senior Data Engineer',
  status:                    'scored',
  final_score:               0.82,
  is_evaluated_via_fallback: false,
  created_at:                '2024-01-12T00:00:00Z',
  updated_at:                '2024-01-15T00:00:00Z',
};

const APP_2 = {
  id:                        'app-2',
  candidate_name:            'Bob Johnson',
  candidate_email:           'bob@example.com',
  job_title:                 'ML Engineer',
  status:                    'pending',
  final_score:               null,
  is_evaluated_via_fallback: false,
  created_at:                '2024-02-01T00:00:00Z',
  updated_at:                '2024-02-01T00:00:00Z',
};

function renderTable(overrides = {}) {
  const props = {
    applications: [APP],
    selected:     new Set(),
    pollingIds:   new Set(),
    runErrors:    new Map(),
    onToggle:     vi.fn(),
    onToggleAll:  vi.fn(),
    onReview:     vi.fn(),
    onRun:        vi.fn(),
    loading:      false,
    error:        null,
    ...overrides,
  };
  return render(<ApplicationTable {...props} />);
}

describe('ApplicationTable', () => {

  // ── States ──────────────────────────────────────────────────────────────────

  test('shows loading spinner when loading=true', () => {
    renderTable({ loading: true, applications: [] });
    expect(screen.getByTestId('table-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('application-table')).not.toBeInTheDocument();
  });

  test('shows error message when error is set', () => {
    renderTable({ error: new Error('Network failure'), applications: [] });
    expect(screen.getByRole('alert')).toHaveTextContent('Network failure');
    expect(screen.queryByTestId('application-table')).not.toBeInTheDocument();
  });

  test('shows empty state when applications list is empty', () => {
    renderTable({ applications: [] });
    expect(screen.getByTestId('table-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('application-table')).not.toBeInTheDocument();
  });

  test('renders the table when applications are present', () => {
    renderTable();
    expect(screen.getByTestId('application-table')).toBeInTheDocument();
  });

  // ── Row rendering ───────────────────────────────────────────────────────────

  test('renders candidate name and email', () => {
    renderTable();
    expect(screen.getByText('Alice Chen')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
  });

  test('renders job title', () => {
    renderTable();
    expect(screen.getByText('Senior Data Engineer')).toBeInTheDocument();
  });

  test('renders final_score as percentage', () => {
    renderTable();
    expect(screen.getByText('82%')).toBeInTheDocument();
  });

  test('renders "—" when final_score is null', () => {
    renderTable({ applications: [APP_2] });
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  test('renders one row per application', () => {
    renderTable({ applications: [APP, APP_2] });
    expect(screen.getAllByTestId('app-row')).toHaveLength(2);
  });

  // ── Score and date formatting ────────────────────────────────────────────────

  test('score rounds to nearest integer percent', () => {
    renderTable({ applications: [{ ...APP, final_score: 0.756 }] });
    expect(screen.getByText('76%')).toBeInTheDocument();
  });

  test('created_at is formatted as a locale date string', () => {
    renderTable();
    // Just assert something date-like is present rather than pinning locale format
    expect(screen.getByTestId('app-row').textContent).toMatch(/\d{4}|\w+ \d+/);
  });

  // ── FallbackAlert ───────────────────────────────────────────────────────────

  test('FallbackAlert not shown when is_evaluated_via_fallback=false', () => {
    renderTable();
    expect(screen.queryByRole('img', { name: /backup model/i })).not.toBeInTheDocument();
  });

  test('FallbackAlert shown when is_evaluated_via_fallback=true', () => {
    renderTable({ applications: [{ ...APP, is_evaluated_via_fallback: true }] });
    expect(screen.getByRole('img', { name: /backup model/i })).toBeInTheDocument();
  });

  // ── Polling state ───────────────────────────────────────────────────────────

  test('row in pollingIds shows "processing" status badge', () => {
    renderTable({ pollingIds: new Set(['app-1']) });
    expect(screen.getByTestId('status-badge')).toHaveTextContent('Processing…');
  });

  test('Run button is disabled while row is polling', () => {
    renderTable({ pollingIds: new Set(['app-1']) });
    expect(screen.getByRole('button', { name: /run pipeline for alice chen/i })).toBeDisabled();
  });

  test('Run button is enabled when row is not polling', () => {
    renderTable();
    expect(screen.getByRole('button', { name: /run pipeline for alice chen/i })).not.toBeDisabled();
  });

  // ── Run error ───────────────────────────────────────────────────────────────

  test('run error message shown when runErrors has entry for the row', () => {
    renderTable({ runErrors: new Map([['app-1', 'Pipeline run failed']]) });
    expect(screen.getByText(/run failed/i)).toBeInTheDocument();
  });

  // ── Checkbox selection ───────────────────────────────────────────────────────

  test('row checkbox is checked when id is in selected set', () => {
    renderTable({ selected: new Set(['app-1']) });
    expect(screen.getByRole('checkbox', { name: /select alice chen/i })).toBeChecked();
  });

  test('row checkbox is unchecked by default', () => {
    renderTable();
    expect(screen.getByRole('checkbox', { name: /select alice chen/i })).not.toBeChecked();
  });

  test('clicking row checkbox calls onToggle with the application id', () => {
    const onToggle = vi.fn();
    renderTable({ onToggle });
    fireEvent.click(screen.getByRole('checkbox', { name: /select alice chen/i }));
    expect(onToggle).toHaveBeenCalledWith('app-1');
  });

  test('select-all checkbox is checked when all rows are selected', () => {
    renderTable({ selected: new Set(['app-1']) });
    expect(screen.getByRole('checkbox', { name: /select all/i })).toBeChecked();
  });

  // ── Action buttons ───────────────────────────────────────────────────────────

  test('clicking Run button calls onRun with the application id', () => {
    const onRun = vi.fn();
    renderTable({ onRun });
    fireEvent.click(screen.getByRole('button', { name: /run pipeline for alice chen/i }));
    expect(onRun).toHaveBeenCalledWith('app-1');
  });

  test('clicking Review button calls onReview with the application id', () => {
    const onReview = vi.fn();
    renderTable({ onReview });
    fireEvent.click(screen.getByRole('button', { name: /review alice chen/i }));
    expect(onReview).toHaveBeenCalledWith('app-1');
  });
});
