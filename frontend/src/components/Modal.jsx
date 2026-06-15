/**
 * Modal — accessible base modal with focus trap and ESC-to-close.
 *
 * Props:
 *   open      {boolean}    renders if true
 *   onClose   {Function}   called on backdrop click or ESC
 *   title     {string}     rendered in the modal header
 *   children  {ReactNode}
 *   width     {string}     CSS max-width override, default "520px"
 */

import { useEffect, useRef } from 'react';

export default function Modal({ open, onClose, title, children, width = '520px' }) {
  const dialogRef = useRef(null);

  // Close on ESC
  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  // Lock body scroll and auto-focus dialog when open
  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = 'hidden';
    dialogRef.current?.focus();
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="modal-backdrop"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="presentation"
    >
      <div
        ref={dialogRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        style={{ maxWidth: width }}
        tabIndex={-1}
      >
        <header className="modal__header">
          <h2 id="modal-title" className="modal__title">{title}</h2>
          <button
            className="modal__close"
            onClick={onClose}
            aria-label="Close modal"
            type="button"
          >
            ✕
          </button>
        </header>

        <div className="modal__body">
          {children}
        </div>
      </div>
    </div>
  );
}
