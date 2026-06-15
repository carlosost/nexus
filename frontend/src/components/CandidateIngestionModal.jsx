/**
 * CandidateIngestionModal — create a new Candidate from a PDF resume upload.
 *
 * Submits multipart/form-data to POST /api/candidates/.
 * Client-side validation gates:
 *   - name and email required
 *   - email format check
 *   - file must be a PDF and ≤ 10 MB
 *
 * Props:
 *   open      {boolean}
 *   onClose   {Function}
 *   onSuccess {(candidate: CandidateRow) => void}
 */

import { useState, useRef } from 'react';
import Modal from './Modal.jsx';
import { createCandidate } from '../api/client.js';

const EMPTY = { name: '', email: '', file: null };

function fieldError(errors, key) {
  const val = errors?.[key];
  return Array.isArray(val) ? val[0] : val ?? null;
}

export default function CandidateIngestionModal({ open, onClose, onSuccess }) {
  const [form, setForm]             = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors]         = useState({});
  const [serverErr, setServerErr]   = useState(null);
  const fileInputRef                = useRef(null);

  function reset() {
    setForm(EMPTY);
    setErrors({});
    setServerErr(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  function handleClose() { reset(); onClose(); }

  function validate() {
    const e = {};
    if (!form.name.trim())  e.name  = 'Full name is required.';
    if (!form.email.trim()) e.email = 'Email address is required.';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email))
      e.email = 'Enter a valid email address.';
    if (!form.file)         e.resume_pdf = 'Please select a PDF resume.';
    else if (!form.file.name.toLowerCase().endsWith('.pdf') &&
             form.file.type !== 'application/pdf')
      e.resume_pdf = 'Only PDF files are accepted.';
    else if (form.file.size > 10 * 1024 * 1024)
      e.resume_pdf = 'File must be smaller than 10 MB.';
    return e;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const clientErrors = validate();
    if (Object.keys(clientErrors).length) { setErrors(clientErrors); return; }
    setSubmitting(true);
    setServerErr(null);
    try {
      const candidate = await createCandidate({
        name:       form.name.trim(),
        email:      form.email.trim(),
        resume_pdf: form.file,
      });
      onSuccess(candidate);
      handleClose();
    } catch (err) {
      if (err.status === 409 || fieldError(err.body, 'email')) {
        setErrors(err.body ?? {});
      } else if (err.body && typeof err.body === 'object') {
        setErrors(err.body);
      } else {
        setServerErr(err.message || 'Failed to upload resume. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={handleClose} title="Add New Candidate">
      <form onSubmit={handleSubmit} noValidate encType="multipart/form-data">
        {serverErr && (
          <p className="form-error form-error--banner" role="alert">{serverErr}</p>
        )}

        <div className="form-field">
          <label htmlFor="cand-name" className="form-label">
            Full Name <span aria-hidden="true">*</span>
          </label>
          <input
            id="cand-name"
            className={`form-input${fieldError(errors, 'name') ? ' form-input--error' : ''}`}
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. Alice Chen"
            autoFocus
            disabled={submitting}
          />
          {fieldError(errors, 'name') && (
            <p className="form-error" role="alert">{fieldError(errors, 'name')}</p>
          )}
        </div>

        <div className="form-field">
          <label htmlFor="cand-email" className="form-label">
            Email Address <span aria-hidden="true">*</span>
          </label>
          <input
            id="cand-email"
            className={`form-input${fieldError(errors, 'email') ? ' form-input--error' : ''}`}
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            placeholder="alice@example.com"
            disabled={submitting}
          />
          {fieldError(errors, 'email') && (
            <p className="form-error" role="alert">{fieldError(errors, 'email')}</p>
          )}
        </div>

        <div className="form-field">
          <label htmlFor="cand-pdf" className="form-label">
            Resume PDF <span aria-hidden="true">*</span>
          </label>
          <div className={`file-drop${fieldError(errors, 'resume_pdf') ? ' file-drop--error' : ''}`}>
            <input
              id="cand-pdf"
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              className="file-drop__input"
              onChange={(e) => setForm({ ...form, file: e.target.files[0] ?? null })}
              disabled={submitting}
            />
            <label htmlFor="cand-pdf" className="file-drop__label">
              {form.file
                ? <><strong>{form.file.name}</strong> ({(form.file.size / 1024).toFixed(0)} KB)</>
                : <>Click to choose or drag a PDF here</>
              }
            </label>
          </div>
          {fieldError(errors, 'resume_pdf') && (
            <p className="form-error" role="alert">{fieldError(errors, 'resume_pdf')}</p>
          )}
        </div>

        <div className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={handleClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" className="btn btn--primary" disabled={submitting}>
            {submitting ? 'Uploading…' : 'Upload Resume'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
