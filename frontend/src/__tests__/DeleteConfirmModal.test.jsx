/**
 * TDD unit tests for DeleteConfirmModal.
 *
 * BDD scenario coverage:
 *   Given the delete modal is open
 *   When the user clicks Cancel → modal closes, onConfirm NOT called
 *   When the user clicks Delete → onConfirm is awaited, then onClose is called
 *   When onConfirm rejects → error message appears, modal stays open
 *   Given the modal contains a cascade warning → warning text is visible
 */
import { vi, describe, test, beforeEach, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DeleteConfirmModal from '../components/settings/DeleteConfirmModal.jsx';

function renderModal({
  open      = true,
  onClose   = vi.fn(),
  onConfirm = vi.fn().mockResolvedValue(undefined),
  label     = '"Senior Engineer"',
  warning   = undefined,
} = {}) {
  return render(
    <DeleteConfirmModal
      open={open}
      onClose={onClose}
      onConfirm={onConfirm}
      entityLabel={label}
      warning={warning}
    />
  );
}

// ---------------------------------------------------------------------------

describe('DeleteConfirmModal', () => {
  // ── Visibility ─────────────────────────────────────────────────────────────
  test('renders body text with entity label', () => {
    renderModal();
    expect(screen.getByTestId('delete-confirm-body')).toHaveTextContent('"Senior Engineer"');
  });

  test('does not render when open=false', () => {
    renderModal({ open: false });
    expect(screen.queryByTestId('delete-confirm-body')).not.toBeInTheDocument();
  });

  // ── Warning ────────────────────────────────────────────────────────────────
  test('shows cascade warning when provided', () => {
    renderModal({ warning: 'All linked applications will be deleted.' });
    expect(screen.getByTestId('delete-confirm-warning')).toHaveTextContent('All linked applications');
  });

  test('does not render warning element when warning is omitted', () => {
    renderModal();
    expect(screen.queryByTestId('delete-confirm-warning')).not.toBeInTheDocument();
  });

  // ── Cancel ─────────────────────────────────────────────────────────────────
  test('calls onClose when Cancel is clicked', async () => {
    const onClose = vi.fn();
    renderModal({ onClose });
    await userEvent.click(screen.getByTestId('delete-cancel-btn'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  test('does NOT call onConfirm when Cancel is clicked', async () => {
    const onConfirm = vi.fn();
    renderModal({ onConfirm });
    await userEvent.click(screen.getByTestId('delete-cancel-btn'));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  // ── Confirm: happy path ────────────────────────────────────────────────────
  test('calls onConfirm then onClose on successful delete', async () => {
    const onClose   = vi.fn();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    renderModal({ onClose, onConfirm });

    await userEvent.click(screen.getByTestId('delete-confirm-btn'));

    await waitFor(() => expect(onConfirm).toHaveBeenCalledOnce());
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  });

  test('button shows "Deleting…" while request is in-flight', async () => {
    let resolve;
    const onConfirm = vi.fn(() => new Promise((r) => { resolve = r; }));
    renderModal({ onConfirm });

    await userEvent.click(screen.getByTestId('delete-confirm-btn'));

    expect(screen.getByTestId('delete-confirm-btn')).toHaveTextContent('Deleting…');
    expect(screen.getByTestId('delete-confirm-btn')).toBeDisabled();
    resolve(); // clean up
  });

  // ── Confirm: error path ────────────────────────────────────────────────────
  test('shows error message and keeps modal open when onConfirm rejects', async () => {
    const onClose   = vi.fn();
    const onConfirm = vi.fn().mockRejectedValue(new Error('Server error'));
    renderModal({ onClose, onConfirm });

    await userEvent.click(screen.getByTestId('delete-confirm-btn'));

    await waitFor(() =>
      expect(screen.getByTestId('delete-confirm-error')).toHaveTextContent('Server error')
    );
    expect(onClose).not.toHaveBeenCalled();
  });

  test('Delete button returns to "Delete" label after error', async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error('oops'));
    renderModal({ onConfirm });

    await userEvent.click(screen.getByTestId('delete-confirm-btn'));

    await waitFor(() => screen.getByTestId('delete-confirm-error'));
    expect(screen.getByTestId('delete-confirm-btn')).toHaveTextContent('Delete');
    expect(screen.getByTestId('delete-confirm-btn')).not.toBeDisabled();
  });
});
