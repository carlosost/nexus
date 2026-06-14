/**
 * Unit tests for OverridePanel component.
 *
 * Critical contract: submit is disabled until override_reason is non-empty
 * when decision is override_pass or override_fail.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OverridePanel from '../components/OverridePanel.jsx';

// Mock the API client so no real fetch is made.
jest.mock('../api/client.js', () => ({
  submitReview: jest.fn(),
}));
import { submitReview } from '../api/client.js';

const APP_ID = 'app-001';

function renderPanel(props = {}) {
  const onSubmit = jest.fn();
  const onError = jest.fn();
  render(
    <OverridePanel
      applicationId={APP_ID}
      onSubmit={onSubmit}
      onError={onError}
      {...props}
    />
  );
  return { onSubmit, onError };
}

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------
describe('OverridePanel — initial state', () => {
  test('default decision is approve', () => {
    renderPanel();
    expect(screen.getByTestId('decision-select')).toHaveValue('approve');
  });

  test('reason textarea not visible for approve', () => {
    renderPanel();
    expect(screen.queryByTestId('override-reason')).not.toBeInTheDocument();
  });

  test('submit button is enabled for approve', () => {
    renderPanel();
    expect(screen.getByTestId('submit-button')).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Approve / Reject — no reason required
// ---------------------------------------------------------------------------
describe('OverridePanel — approve/reject decisions', () => {
  test('reason textarea not visible for reject', async () => {
    renderPanel();
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'reject');
    expect(screen.queryByTestId('override-reason')).not.toBeInTheDocument();
  });

  test('submit button enabled for reject', async () => {
    renderPanel();
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'reject');
    expect(screen.getByTestId('submit-button')).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Override decisions — reason required
// ---------------------------------------------------------------------------
describe('OverridePanel — override_pass', () => {
  test('reason textarea becomes visible', async () => {
    renderPanel();
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'override_pass');
    expect(screen.getByTestId('override-reason')).toBeInTheDocument();
  });

  test('submit is disabled when reason is empty', async () => {
    renderPanel();
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'override_pass');
    expect(screen.getByTestId('submit-button')).toBeDisabled();
  });

  test('submit is disabled when reason is whitespace only', async () => {
    renderPanel();
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'override_pass');
    await userEvent.type(screen.getByTestId('override-reason'), '   ');
    expect(screen.getByTestId('submit-button')).toBeDisabled();
  });

  test('submit becomes enabled once reason is typed', async () => {
    renderPanel();
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'override_pass');
    await userEvent.type(screen.getByTestId('override-reason'), 'Strong portfolio');
    expect(screen.getByTestId('submit-button')).not.toBeDisabled();
  });

  test('submit disabled again after clearing the reason', async () => {
    renderPanel();
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'override_pass');
    const textarea = screen.getByTestId('override-reason');
    await userEvent.type(textarea, 'Strong portfolio');
    await userEvent.clear(textarea);
    expect(screen.getByTestId('submit-button')).toBeDisabled();
  });
});

describe('OverridePanel — override_fail', () => {
  test('reason textarea becomes visible', async () => {
    renderPanel();
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'override_fail');
    expect(screen.getByTestId('override-reason')).toBeInTheDocument();
  });

  test('submit disabled without reason', async () => {
    renderPanel();
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'override_fail');
    expect(screen.getByTestId('submit-button')).toBeDisabled();
  });

  test('submit enabled once reason provided', async () => {
    renderPanel();
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'override_fail');
    await userEvent.type(screen.getByTestId('override-reason'), 'Did not meet bar');
    expect(screen.getByTestId('submit-button')).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Reason cleared when switching away from override
// ---------------------------------------------------------------------------
describe('OverridePanel — switching decisions', () => {
  test('reason textarea disappears when switching from override to approve', async () => {
    renderPanel();
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'override_pass');
    expect(screen.getByTestId('override-reason')).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'approve');
    expect(screen.queryByTestId('override-reason')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// API submission
// ---------------------------------------------------------------------------
describe('OverridePanel — submission', () => {
  beforeEach(() => submitReview.mockReset());

  test('calls submitReview with correct payload for approve', async () => {
    submitReview.mockResolvedValue({ id: '1', decision: 'approve' });
    const { onSubmit } = renderPanel();

    await userEvent.type(screen.getByTestId('reviewer-email'), 'alice@co.com');
    fireEvent.click(screen.getByTestId('submit-button'));

    await waitFor(() => expect(submitReview).toHaveBeenCalledWith(APP_ID, {
      reviewer_email: 'alice@co.com',
      decision: 'approve',
    }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  });

  test('calls submitReview with override_reason for override_pass', async () => {
    submitReview.mockResolvedValue({ id: '2', decision: 'override_pass' });
    const { onSubmit } = renderPanel();

    await userEvent.type(screen.getByTestId('reviewer-email'), 'alice@co.com');
    await userEvent.selectOptions(screen.getByTestId('decision-select'), 'override_pass');
    await userEvent.type(screen.getByTestId('override-reason'), 'Strong portfolio');
    fireEvent.click(screen.getByTestId('submit-button'));

    await waitFor(() => expect(submitReview).toHaveBeenCalledWith(APP_ID, {
      reviewer_email: 'alice@co.com',
      decision: 'override_pass',
      override_reason: 'Strong portfolio',
    }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  });

  test('calls onError when submitReview throws', async () => {
    const apiError = new Error('HTTP 500');
    submitReview.mockRejectedValue(apiError);
    const { onError } = renderPanel();

    await userEvent.type(screen.getByTestId('reviewer-email'), 'alice@co.com');
    fireEvent.click(screen.getByTestId('submit-button'));

    await waitFor(() => expect(onError).toHaveBeenCalledWith(apiError));
  });
});
