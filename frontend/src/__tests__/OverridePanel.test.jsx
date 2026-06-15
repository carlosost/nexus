/**
 * Unit tests for OverridePanel — migrated from Jest to Vitest.
 */
import { vi, describe, test, beforeEach, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OverridePanel from '../components/OverridePanel.jsx';

vi.mock('../api/client.js', () => ({
  submitReview: vi.fn(),
}));
import { submitReview } from '../api/client.js';

const APP_ID = 'app-001';

function renderPanel(props = {}) {
  const onSubmit = vi.fn();
  return {
    onSubmit,
    ...render(
      <OverridePanel
        applicationId={APP_ID}
        aiScore={0.82}
        onSubmit={onSubmit}
        {...props}
      />
    ),
  };
}

describe('OverridePanel', () => {
  beforeEach(() => {
    submitReview.mockReset();
  });

  test('renders the review form', () => {
    renderPanel();
    expect(screen.getByTestId('review-form')).toBeInTheDocument();
  });

  test('submit button is present', () => {
    renderPanel();
    expect(screen.getByTestId('submit-button')).toBeInTheDocument();
  });

  test('override_reason field is hidden when decision is approve', () => {
    renderPanel();
    expect(screen.queryByTestId('override-reason')).not.toBeInTheDocument();
  });

  test('override_reason field appears when decision is override_pass', async () => {
    renderPanel();
    const select = screen.getByTestId('decision-select');
    await userEvent.selectOptions(select, 'override_pass');
    expect(screen.getByTestId('override-reason')).toBeInTheDocument();
  });

  test('submit is disabled when override decision has no reason', async () => {
    renderPanel();
    const select = screen.getByTestId('decision-select');
    await userEvent.selectOptions(select, 'override_pass');
    await userEvent.type(screen.getByTestId('reviewer-email'), 'bob@co.com');
    expect(screen.getByTestId('submit-button')).toBeDisabled();
  });

  test('submit is enabled after filling override reason', async () => {
    renderPanel();
    const select = screen.getByTestId('decision-select');
    await userEvent.selectOptions(select, 'override_pass');
    await userEvent.type(screen.getByTestId('reviewer-email'), 'bob@co.com');
    await userEvent.type(screen.getByTestId('override-reason'), 'Strong portfolio');
    expect(screen.getByTestId('submit-button')).not.toBeDisabled();
  });
});
