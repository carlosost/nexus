/**
 * DeleteConfirmModal — generic, reusable hard-delete confirmation dialog.
 *
 * Props:
 *   open        {boolean}
 *   onClose     {Function}
 *   onConfirm   {Function}  — async handler; modal shows spinner while pending
 *   entityLabel {string}    — human-readable name of the thing being deleted
 *                             e.g. "the job "Senior Engineer"" or "Alice Chen"
 *   warning     {string?}   — optional cascade warning shown in amber
 */

import { useState } from 'react';
import Modal from '../Modal.jsx';

export default function DeleteConfirmModal({
  open,
  onClose,
  onConfirm,
  entityLabel,
  warning,
}) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError]       = useState(null);

  async function handleConfirm() {
    setDeleting(true);
    setError(null);
    try {
      await onConfirm();
      onClose();
    } catch (err) {
      setError(err.message || 'Delete failed. Please try again.');
    } finally {
      setDeleting(false);
    }
  }

  function handleClose() {
    if (deleting) return;
    setError(null);
    onClose();
  }

  return (
    <Modal open={open} onClose={handleClose} title="Confirm Delete">
      <p className="delete-confirm__body" data-testid="delete-confirm-body">
        Are you sure you want to permanently delete{' '}
        <strong>{entityLabel}</strong>? This action cannot be undone.
      </p>

      {warning && (
        <p className="delete-confirm__warning" role="note" data-testid="delete-confirm-warning">
          ⚠ {warning}
        </p>
      )}

      {error && (
        <p className="form-error form-error--banner" role="alert" data-testid="delete-confirm-error">
          {error}
        </p>
      )}

      <div className="modal__footer">
        <button
          type="button"
          className="btn btn--ghost"
          onClick={handleClose}
          disabled={deleting}
          data-testid="delete-cancel-btn"
        >
          Cancel
        </button>
        <button
          type="button"
          className="btn btn--danger"
          onClick={handleConfirm}
          disabled={deleting}
          data-testid="delete-confirm-btn"
        >
          {deleting ? 'Deleting…' : 'Delete'}
        </button>
      </div>
    </Modal>
  );
}
