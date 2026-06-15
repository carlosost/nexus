/**
 * TDD unit tests for ApplicationCenter.
 *
 * BDD scenarios:
 *   Given no jobs exist → prerequisite notice shown, submit disabled
 *   Given no candidates exist → prerequisite notice shown, submit disabled
 *   Given both collections are populated:
 *     When user selects job + candidate and submits → createApplication called
 *     When API returns created=true (201) → success banner appears
 *     When API returns created=false (200) → duplicate notice with Dashboard link
 *   Given user submits without selecting job → field-level validation fires
 */
import { vi, describe, test, beforeEach, expect } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ApplicationCenter from '../components/settings/ApplicationCenter.jsx';

vi.mock('../api/client.js', () => ({
  createApplication: vi.fn(),
}));
import { createApplication } from '../api/client.js';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const JOBS = [
  { id: 'job-1', title: 'Senior Engineer' },
  { id: 'job-2', title: 'Product Manager' },
];

const CANDIDATES = [
  { id: 'cand-1', name: 'Alice Chen',  email: 'alice@example.com' },
  { id: 'cand-2', name: 'Bob Smith',   email: 'bob@example.com'   },
];

const APP_RESPONSE = {
  id:            'app-abc',
  job_id:        'job-1',
  candidate_id:  'cand-1',
  status:        'pending',
};

function renderCenter({ jobs = JOBS, candidates = CANDIDATES, onSuccess = vi.fn() } = {}) {
  return render(
    <ApplicationCenter jobs={jobs} candidates={candidates} onSuccess={onSuccess} />
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ApplicationCenter', () => {
  beforeEach(() => createApplication.mockReset());

  // ── Pre-requisite guards ───────────────────────────────────────────────────
  test('Given no jobs → shows prerequisite notice', () => {
    renderCenter({ jobs: [] });
    expect(screen.getByTestId('assoc-prereq-notice')).toHaveTextContent('No jobs found');
  });

  test('Given no candidates → shows prerequisite notice', () => {
    renderCenter({ candidates: [] });
    expect(screen.getByTestId('assoc-prereq-notice')).toHaveTextContent('No candidates found');
  });

  test('Given no jobs → submit button is disabled', () => {
    renderCenter({ jobs: [] });
    expect(screen.getByTestId('assoc-submit-btn')).toBeDisabled();
  });

  test('Given no candidates → submit button is disabled', () => {
    renderCenter({ candidates: [] });
    expect(screen.getByTestId('assoc-submit-btn')).toBeDisabled();
  });

  test('Given both collections populated → no prerequisite notice', () => {
    renderCenter();
    expect(screen.queryByTestId('assoc-prereq-notice')).not.toBeInTheDocument();
  });

  // ── Happy-path submission (201 — new application) ─────────────────────────
  test('When user selects job + candidate and submits → createApplication called', async () => {
    createApplication.mockResolvedValue({ data: APP_RESPONSE, created: true });
    renderCenter();

    await userEvent.selectOptions(screen.getByTestId('assoc-job-select'),       'job-1');
    await userEvent.selectOptions(screen.getByTestId('assoc-candidate-select'), 'cand-1');
    await userEvent.click(screen.getByTestId('assoc-submit-btn'));

    await waitFor(() =>
      expect(createApplication).toHaveBeenCalledWith({ job_id: 'job-1', candidate_id: 'cand-1' })
    );
  });

  test('After 201 → success banner appears', async () => {
    createApplication.mockResolvedValue({ data: APP_RESPONSE, created: true });
    renderCenter();

    await userEvent.selectOptions(screen.getByTestId('assoc-job-select'),       'job-1');
    await userEvent.selectOptions(screen.getByTestId('assoc-candidate-select'), 'cand-1');
    await userEvent.click(screen.getByTestId('assoc-submit-btn'));

    await waitFor(() =>
      expect(screen.getByTestId('assoc-success')).toBeInTheDocument()
    );
    expect(screen.queryByTestId('assoc-duplicate')).not.toBeInTheDocument();
  });

  test('After 201 → onSuccess is called with the application', async () => {
    const onSuccess = vi.fn();
    createApplication.mockResolvedValue({ data: APP_RESPONSE, created: true });
    renderCenter({ onSuccess });

    await userEvent.selectOptions(screen.getByTestId('assoc-job-select'),       'job-1');
    await userEvent.selectOptions(screen.getByTestId('assoc-candidate-select'), 'cand-1');
    await userEvent.click(screen.getByTestId('assoc-submit-btn'));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(APP_RESPONSE));
  });

  test('After 201 → form resets to empty', async () => {
    createApplication.mockResolvedValue({ data: APP_RESPONSE, created: true });
    renderCenter();

    await userEvent.selectOptions(screen.getByTestId('assoc-job-select'),       'job-1');
    await userEvent.selectOptions(screen.getByTestId('assoc-candidate-select'), 'cand-1');
    await userEvent.click(screen.getByTestId('assoc-submit-btn'));

    await waitFor(() => screen.getByTestId('assoc-success'));
    expect(screen.getByTestId('assoc-job-select')).toHaveValue('');
    expect(screen.getByTestId('assoc-candidate-select')).toHaveValue('');
  });

  // ── Duplicate path (200 — application already exists) ─────────────────────
  test('After 200 → duplicate notice appears instead of success banner', async () => {
    createApplication.mockResolvedValue({ data: APP_RESPONSE, created: false });
    renderCenter();

    await userEvent.selectOptions(screen.getByTestId('assoc-job-select'),       'job-1');
    await userEvent.selectOptions(screen.getByTestId('assoc-candidate-select'), 'cand-1');
    await userEvent.click(screen.getByTestId('assoc-submit-btn'));

    await waitFor(() =>
      expect(screen.getByTestId('assoc-duplicate')).toBeInTheDocument()
    );
    expect(screen.queryByTestId('assoc-success')).not.toBeInTheDocument();
  });

  test('After 200 → duplicate notice contains "already exists"', async () => {
    createApplication.mockResolvedValue({ data: APP_RESPONSE, created: false });
    renderCenter();

    await userEvent.selectOptions(screen.getByTestId('assoc-job-select'),       'job-1');
    await userEvent.selectOptions(screen.getByTestId('assoc-candidate-select'), 'cand-1');
    await userEvent.click(screen.getByTestId('assoc-submit-btn'));

    await waitFor(() => screen.getByTestId('assoc-duplicate'));
    expect(screen.getByTestId('assoc-duplicate')).toHaveTextContent(/already exists/i);
  });

  test('After 200 → duplicate notice contains a Dashboard link', async () => {
    createApplication.mockResolvedValue({ data: APP_RESPONSE, created: false });
    renderCenter();

    await userEvent.selectOptions(screen.getByTestId('assoc-job-select'),       'job-1');
    await userEvent.selectOptions(screen.getByTestId('assoc-candidate-select'), 'cand-1');
    await userEvent.click(screen.getByTestId('assoc-submit-btn'));

    await waitFor(() => screen.getByTestId('assoc-duplicate'));
    expect(screen.getByTestId('assoc-duplicate').querySelector('a')).toHaveAttribute('href', '/');
  });

  test('After 200 → onSuccess is NOT called', async () => {
    const onSuccess = vi.fn();
    createApplication.mockResolvedValue({ data: APP_RESPONSE, created: false });
    renderCenter({ onSuccess });

    await userEvent.selectOptions(screen.getByTestId('assoc-job-select'),       'job-1');
    await userEvent.selectOptions(screen.getByTestId('assoc-candidate-select'), 'cand-1');
    await userEvent.click(screen.getByTestId('assoc-submit-btn'));

    await waitFor(() => screen.getByTestId('assoc-duplicate'));
    expect(onSuccess).not.toHaveBeenCalled();
  });

  // ── Client-side validation ─────────────────────────────────────────────────
  test('When submitted without selecting job → client error shown, API not called', async () => {
    renderCenter();
    await userEvent.click(screen.getByTestId('assoc-submit-btn'));
    expect(createApplication).not.toHaveBeenCalled();
  });

});
