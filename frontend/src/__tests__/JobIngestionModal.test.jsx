/**
 * Unit tests for the Job Markdown Ingestion modal.
 *
 * BDD coverage:
 *   Given the modal is open → textarea is visible and empty
 *   When user submits empty form → inline validation error shown
 *   When user submits valid Markdown → loading state shown, API called
 *   When API returns 201 → modal closes, onSuccess callback fires
 *   When API returns 422 with field errors → inline field errors rendered
 *   When API returns 500 → generic error banner rendered
 *
 * Tools: Vitest · @testing-library/react · vi.mock
 */

import { vi, describe, test, beforeEach, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import JobIngestionModal from '../components/JobIngestionModal.jsx';
import * as client from '../api/client.js';

vi.mock('../api/client.js', () => ({
  createJob: vi.fn(),
}));

// ── Fixtures ──────────────────────────────────────────────────────────────

const VALID_JOB_RESPONSE = {
  id:         'job-uuid-001',
  title:      'Senior Backend Engineer',
  created_at: '2024-01-15T12:00:00Z',
};

const VALID_MARKDOWN = `# Senior Backend Engineer

## Description
Deep Python and Django experience required.

## Requirements
### Required Skills
- Python
- Django
`;

function apiError(body, message = 'HTTP error') {
  const err = new Error(message);
  err.body = body;
  return err;
}

function renderModal(props = {}) {
  const defaults = {
    open:      true,
    onClose:   vi.fn(),
    onSuccess: vi.fn(),
  };
  return render(<JobIngestionModal {...defaults} {...props} />);
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe('JobIngestionModal', () => {

  beforeEach(() => {
    client.createJob.mockReset();
  });

  // ── Rendering ───────────────────────────────────────────────────────────

  test('renders the Markdown textarea when open', () => {
    renderModal();
    expect(screen.getByTestId('job-raw-markdown')).toBeInTheDocument();
  });

  test('textarea is empty on open', () => {
    renderModal();
    expect(screen.getByTestId('job-raw-markdown')).toHaveValue('');
  });

  test('submit button is present', () => {
    renderModal();
    expect(screen.getByRole('button', { name: /create job/i })).toBeInTheDocument();
  });

  test('modal is not rendered when open=false', () => {
    renderModal({ open: false });
    expect(screen.queryByTestId('job-raw-markdown')).not.toBeInTheDocument();
  });

  test('shows format hint text', () => {
    renderModal();
    expect(screen.getByText(/markdown format/i)).toBeInTheDocument();
  });

  // ── Textarea interaction ─────────────────────────────────────────────────

  test('user can type Markdown into the textarea', () => {
    renderModal();
    const ta = screen.getByTestId('job-raw-markdown');
    fireEvent.change(ta, { target: { value: VALID_MARKDOWN } });
    expect(ta).toHaveValue(VALID_MARKDOWN);
  });

  // ── Validation ───────────────────────────────────────────────────────────

  test('inline error shown when submitted with empty textarea', async () => {
    renderModal();
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toBeInTheDocument()
    );
    expect(client.createJob).not.toHaveBeenCalled();
  });

  // ── Loading state ────────────────────────────────────────────────────────

  test('textarea is disabled during submission', async () => {
    client.createJob.mockReturnValue(new Promise(() => {})); // never resolves
    renderModal();
    fireEvent.change(
      screen.getByTestId('job-raw-markdown'),
      { target: { value: VALID_MARKDOWN } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    expect(screen.getByTestId('job-raw-markdown')).toBeDisabled();
  });

  test('submit button shows loading label during submission', async () => {
    client.createJob.mockReturnValue(new Promise(() => {}));
    renderModal();
    fireEvent.change(
      screen.getByTestId('job-raw-markdown'),
      { target: { value: VALID_MARKDOWN } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    expect(screen.getByRole('button', { name: /creating/i })).toBeInTheDocument();
  });

  // ── Success path ─────────────────────────────────────────────────────────

  test('onSuccess called with job data on 201', async () => {
    const onSuccess = vi.fn();
    client.createJob.mockResolvedValue(VALID_JOB_RESPONSE);
    renderModal({ onSuccess });
    fireEvent.change(
      screen.getByTestId('job-raw-markdown'),
      { target: { value: VALID_MARKDOWN } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(VALID_JOB_RESPONSE));
  });

  test('onClose called after successful submission', async () => {
    const onClose = vi.fn();
    client.createJob.mockResolvedValue(VALID_JOB_RESPONSE);
    renderModal({ onClose });
    fireEvent.change(
      screen.getByTestId('job-raw-markdown'),
      { target: { value: VALID_MARKDOWN } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  test('createJob called with raw_markdown payload', async () => {
    client.createJob.mockResolvedValue(VALID_JOB_RESPONSE);
    renderModal();
    fireEvent.change(
      screen.getByTestId('job-raw-markdown'),
      { target: { value: VALID_MARKDOWN } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() =>
      expect(client.createJob).toHaveBeenCalledWith({ raw_markdown: VALID_MARKDOWN.trim() })
    );
  });

  // ── Validation errors (422) ───────────────────────────────────────────────

  test('inline error shown when API returns field error for "title"', async () => {
    client.createJob.mockRejectedValue(
      apiError({ title: ['Missing H1 heading.'] })
    );
    renderModal();
    fireEvent.change(
      screen.getByTestId('job-raw-markdown'),
      { target: { value: '## No H1 Here' } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() =>
      expect(screen.getByText(/missing h1 heading/i)).toBeInTheDocument()
    );
  });

  test('inline error shown when API returns field error for "description"', async () => {
    client.createJob.mockRejectedValue(
      apiError({ description: ['Description section is required.'] })
    );
    renderModal();
    fireEvent.change(
      screen.getByTestId('job-raw-markdown'),
      { target: { value: '# Title only' } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() =>
      expect(screen.getByText(/description section is required/i)).toBeInTheDocument()
    );
  });

  // ── Generic errors ────────────────────────────────────────────────────────

  test('error banner shown when API returns non-field error', async () => {
    client.createJob.mockRejectedValue(new Error('Failed to create job. Please try again.'));
    renderModal();
    fireEvent.change(
      screen.getByTestId('job-raw-markdown'),
      { target: { value: VALID_MARKDOWN } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toBeInTheDocument()
    );
  });

  test('textarea re-enabled after error — user can edit and retry', async () => {
    client.createJob.mockRejectedValue(new Error('Server error'));
    renderModal();
    const ta = screen.getByTestId('job-raw-markdown');
    fireEvent.change(ta, { target: { value: VALID_MARKDOWN } });
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() => expect(ta).not.toBeDisabled());
  });

  // ── Duplicate detection ───────────────────────────────────────────────────

  test('409 response shows "already exists" message', async () => {
    client.createJob.mockRejectedValue(
      apiError({ detail: 'A job with this title already exists.' })
    );
    renderModal();
    fireEvent.change(
      screen.getByTestId('job-raw-markdown'),
      { target: { value: VALID_MARKDOWN } }
    );
    fireEvent.click(screen.getByRole('button', { name: /create job/i }));
    await waitFor(() =>
      expect(screen.getByText(/already exists/i)).toBeInTheDocument()
    );
  });
});
