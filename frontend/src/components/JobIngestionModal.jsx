/**
 * JobIngestionModal — create a new Job from a pasted Markdown job description.
 *
 * The backend parses the Markdown to extract title, description, requirements,
 * and hard-gate criteria automatically.
 *
 * Props:
 *   open      {boolean}
 *   onClose   {Function}
 *   onSuccess {(job: JobRow) => void}  called with the created job on success
 */

import { useState } from 'react';
import Modal from './Modal.jsx';
import { createJob } from '../api/client.js';

const EMPTY = { raw_markdown: '' };

const MARKDOWN_EXAMPLE = `# Senior Backend Engineer

## Description
We are looking for a backend engineer to join our platform team…

## Requirements
### Required Skills
- Python, Django
- PostgreSQL

### Preferred Skills
- Redis, Celery

## Must Haves
- 3+ years of professional backend experience
- Proficiency in Python`;

function fieldError(errors, key) {
  const val = errors?.[key];
  return Array.isArray(val) ? val[0] : val ?? null;
}

export default function JobIngestionModal({ open, onClose, onSuccess }) {
  const [form, setForm]             = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors]         = useState({});
  const [serverErr, setServerErr]   = useState(null);

  function reset() {
    setForm(EMPTY);
    setErrors({});
    setServerErr(null);
  }

  function handleClose() {
    reset();
    onClose();
  }

  function validate() {
    const e = {};
    if (!form.raw_markdown.trim()) e.raw_markdown = 'Job description is required.';
    return e;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const clientErrors = validate();
    if (Object.keys(clientErrors).length) {
      setErrors(clientErrors);
      return;
    }
    setSubmitting(true);
    setServerErr(null);
    try {
      const job = await createJob({ raw_markdown: form.raw_markdown.trim() });
      onSuccess(job);
      handleClose();
    } catch (err) {
      if (err.body && typeof err.body === 'object') {
        setErrors(err.body);
      } else {
        setServerErr(err.message || 'Failed to create job. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={handleClose} title="Add New Job">
      <form onSubmit={handleSubmit} noValidate>
        {serverErr && (
          <p className="form-error form-error--banner" role="alert">{serverErr}</p>
        )}

        <p className="form-hint">
          Paste the full job description in <strong>Markdown format</strong>.
          The title, description, requirements, and hard-gate criteria are extracted
          automatically from the document structure.
        </p>

        <details className="form-hint form-hint--example">
          <summary>Show expected format</summary>
          <pre className="form-hint__code">{MARKDOWN_EXAMPLE}</pre>
        </details>

        <div className="form-field">
          <label htmlFor="job-raw-markdown" className="form-label">
            Markdown Job Description <span aria-hidden="true">*</span>
          </label>
          <textarea
            id="job-raw-markdown"
            className={`form-input form-input--textarea form-input--mono${fieldError(errors, 'raw_markdown') ? ' form-input--error' : ''}`}
            value={form.raw_markdown}
            onChange={(e) => setForm({ ...form, raw_markdown: e.target.value })}
            placeholder={`# Job Title\n\n## Description\n…`}
            rows={12}
            autoFocus
            disabled={submitting}
            data-testid="job-raw-markdown"
          />
          {fieldError(errors, 'raw_markdown') && (
            <p className="form-error" role="alert">{fieldError(errors, 'raw_markdown')}</p>
          )}
        </div>

        <div className="modal__footer">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={handleClose}
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={submitting}
          >
            {submitting ? 'Creating…' : 'Create Job'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
