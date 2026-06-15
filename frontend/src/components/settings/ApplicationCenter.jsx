/**
 * ApplicationCenter — link an existing Job to an existing Candidate.
 *
 * Moved here from AssociationModal: the UX is now inline on the Settings page
 * rather than a modal on the Dashboard. The association form sits permanently
 * visible in the panel (no "open/close" trigger needed).
 *
 * Props:
 *   jobs        {JobRow[]}
 *   candidates  {CandidateRow[]}
 *   onSuccess   {(app: ApplicationRow) => void}
 */

import { useState } from 'react';
import { createApplication } from '../../api/client.js';

const EMPTY = { job_id: '', candidate_id: '' };

function fieldError(errors, key) {
  const val = errors?.[key];
  return Array.isArray(val) ? val[0] : val ?? null;
}

export default function ApplicationCenter({ jobs, candidates, onSuccess }) {
  const [form, setForm]             = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors]         = useState({});
  const [serverErr, setServerErr]   = useState(null);
  const [result, setResult]         = useState(null); // { app, created }

  const noJobs       = jobs.length === 0;
  const noCandidates = candidates.length === 0;

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
    setResult(null);
    try {
      const { data: app, created } = await createApplication(form);
      if (created) onSuccess(app);
      setResult({ app, created });
      setForm(EMPTY);
      setErrors({});
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

  const candidateName = (id) => candidates.find((c) => c.id === id)?.name ?? 'this candidate';
  const jobTitle      = (id) => jobs.find((j) => j.id === id)?.title ?? 'this job';

  return (
    <section className="admin-board" data-testid="application-center">
      <div className="admin-board__header">
        <h2 className="admin-board__title">New Application</h2>
        <p className="admin-board__subtitle">
          Link a job to a candidate to create an application for evaluation.
        </p>
      </div>

      {result?.created && (
        <div className="assoc-success" role="status" data-testid="assoc-success">
          ✓ Application created for{' '}
          <strong>{candidateName(result.app.candidate_id)}</strong>
          {' '}→{' '}
          <strong>{jobTitle(result.app.job_id)}</strong>.
          Visit the{' '}
          <a href="/" className="assoc-success__link">Dashboard</a>
          {' '}to run the pipeline.
        </div>
      )}

      {result && !result.created && (
        <div className="assoc-duplicate" role="status" data-testid="assoc-duplicate">
          An application for{' '}
          <strong>{candidateName(result.app.candidate_id)}</strong>
          {' '}→{' '}
          <strong>{jobTitle(result.app.job_id)}</strong>
          {' '}already exists.{' '}
          <a href="/" className="assoc-success__link">Visit the Dashboard</a>
          {' '}to manage it.
        </div>
      )}

      {(noJobs || noCandidates) && (
        <div className="form-notice" role="note" data-testid="assoc-prereq-notice">
          {noJobs       && <p>No jobs found — add at least one job in the <strong>Jobs</strong> tab first.</p>}
          {noCandidates && <p>No candidates found — upload at least one resume in the <strong>Candidates</strong> tab first.</p>}
        </div>
      )}

      <form
        className="assoc-form"
        onSubmit={handleSubmit}
        noValidate
        data-testid="assoc-form"
      >
        {serverErr && (
          <p className="form-error form-error--banner" role="alert" data-testid="server-error-banner">{serverErr}</p>
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
            data-testid="assoc-job-select"
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
            data-testid="assoc-candidate-select"
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

        <div className="assoc-form__footer">
          <button
            type="submit"
            className="btn btn--primary"
            disabled={submitting || noJobs || noCandidates}
            data-testid="assoc-submit-btn"
          >
            {submitting ? 'Creating…' : 'Create Application'}
          </button>
        </div>
      </form>
    </section>
  );
}
