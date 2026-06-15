/**
 * AssociationModal — link an existing Job to an existing Candidate.
 *
 * Submits POST /api/applications/ with { job_id, candidate_id }.
 * The backend is idempotent: re-submitting the same pair returns the
 * existing record (HTTP 200) rather than a conflict error.
 *
 * Props:
 *   open        {boolean}
 *   onClose     {Function}
 *   onSuccess   {(app: ApplicationRow) => void}
 *   jobs        {JobRow[]}        from useJobs hook
 *   candidates  {CandidateRow[]}  from useCandidates hook
 */

import { useState } from 'react';
import Modal from './Modal.jsx';
import { createApplication } from '../api/client.js';

const EMPTY = { job_id: '', candidate_id: '' };

function fieldError(errors, key) {
  const val = errors?.[key];
  return Array.isArray(val) ? val[0] : val ?? null;
}

export default function AssociationModal({ open, onClose, onSuccess, jobs, candidates }) {
  const [form, setForm]             = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors]         = useState({});
  const [serverErr, setServerErr]   = useState(null);

  function reset() { setForm(EMPTY); setErrors({}); setServerErr(null); }
  function handleClose() { reset(); onClose(); }

  function validate() {
    const e = {};
    if (!form.job_id)       e.job_id       = 'Please select a job.';
    if (!form.candidate_id) e.candidate_id = 'Please select a candidate.';
    return e;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const clientErrors = validate();
    if (Object.keys(clientErrors).length) { setErrors(clientErrors); return; }
    setSubmitting(true);
    setServerErr(null);
    try {
      const app = await createApplication(form);
      onSuccess(app);
      handleClose();
    } catch (err) {
      if (err.body && typeof err.body === 'object') {
        setErrors(err.body);
      } else {
        setServerErr(err.message || 'Failed to create application. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  const noJobs       = jobs.length === 0;
  const noCandidates = candidates.length === 0;

  return (
    <Modal open={open} onClose={handleClose} title="New Application">
      <form onSubmit={handleSubmit} noValidate>
        {serverErr && (
          <p className="form-error form-error--banner" role="alert">{serverErr}</p>
        )}

        {(noJobs || noCandidates) && (
          <div className="form-notice" role="note">
            {noJobs && <p>No jobs found — add a Job first.</p>}
            {noCandidates && <p>No candidates found — upload a resume first.</p>}
          </div>
        )}

        <div className="form-field">
          <label htmlFor="assoc-job" className="form-label">
            Job <span aria-hidden="true">*</span>
          </label>
          <select
            id="assoc-job"
            className={`form-input form-input--select${fieldError(errors, 'job_id') ? ' form-input--error' : ''}`}
            value={form.job_id}
            onChange={(e) => setForm({ ...form, job_id: e.target.value })}
            disabled={submitting || noJobs}
            autoFocus
          >
            <option value="">— Select a job —</option>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>{j.title}</option>
            ))}
          </select>
          {fieldError(errors, 'job_id') && (
            <p className="form-error" role="alert">{fieldError(errors, 'job_id')}</p>
          )}
        </div>

        <div className="form-field">
          <label htmlFor="assoc-candidate" className="form-label">
            Candidate <span aria-hidden="true">*</span>
          </label>
          <select
            id="assoc-candidate"
            className={`form-input form-input--select${fieldError(errors, 'candidate_id') ? ' form-input--error' : ''}`}
            value={form.candidate_id}
            onChange={(e) => setForm({ ...form, candidate_id: e.target.value })}
            disabled={submitting || noCandidates}
          >
            <option value="">— Select a candidate —</option>
            {candidates.map((c) => (
              <option key={c.id} value={c.id}>{c.name} ({c.email})</option>
            ))}
          </select>
          {fieldError(errors, 'candidate_id') && (
            <p className="form-error" role="alert">{fieldError(errors, 'candidate_id')}</p>
          )}
        </div>

        <div className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={handleClose} disabled={submitting}>
            Cancel
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={submitting || noJobs || noCandidates}
          >
            {submitting ? 'Creating…' : 'Create Application'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
