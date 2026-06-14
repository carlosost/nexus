/**
 * OverridePanel — review form with override submit guard.
 *
 * Submit guard contract:
 *   - approve / reject   → reason textarea hidden; submit always enabled.
 *   - override_pass / override_fail → reason textarea visible;
 *     submit disabled until reason.trim().length > 0.
 *
 * Props:
 *   applicationId  {string}   UUID of the application being reviewed.
 *   onSubmit       {function} Called with the API response on success.
 *   onError        {function} Called with an Error on submission failure.
 */
import { useState } from 'react';
import { submitReview } from '../api/client.js';

const OVERRIDE_DECISIONS = new Set(['override_pass', 'override_fail']);

const DECISION_OPTIONS = [
  { value: 'approve',       label: 'Approve' },
  { value: 'reject',        label: 'Reject' },
  { value: 'override_pass', label: 'Override — Move to Pass' },
  { value: 'override_fail', label: 'Override — Move to Fail' },
];

export default function OverridePanel({ applicationId, onSubmit, onError }) {
  const [reviewerEmail, setReviewerEmail] = useState('');
  const [decision, setDecision] = useState('approve');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const isOverride = OVERRIDE_DECISIONS.has(decision);
  const submitDisabled = submitting || (isOverride && reason.trim().length === 0);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload = { reviewer_email: reviewerEmail, decision };
      if (isOverride) payload.override_reason = reason.trim();
      const result = await submitReview(applicationId, payload);
      onSubmit?.(result);
    } catch (err) {
      onError?.(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="override-panel" aria-label="Override panel">
      <h2 className="override-panel__title">Submit Review</h2>

      <form
        className="override-panel__form"
        onSubmit={handleSubmit}
        data-testid="review-form"
      >
        <label className="override-panel__label" htmlFor="reviewer-email">
          Reviewer email
        </label>
        <input
          id="reviewer-email"
          type="email"
          className="override-panel__input"
          data-testid="reviewer-email"
          value={reviewerEmail}
          onChange={(e) => setReviewerEmail(e.target.value)}
          required
          placeholder="you@company.com"
        />

        <label className="override-panel__label" htmlFor="decision">
          Decision
        </label>
        <select
          id="decision"
          className="override-panel__select"
          data-testid="decision-select"
          value={decision}
          onChange={(e) => {
            setDecision(e.target.value);
            setReason('');
          }}
        >
          {DECISION_OPTIONS.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>

        {isOverride && (
          <>
            <label className="override-panel__label" htmlFor="override-reason">
              Override reason <span aria-hidden="true">*</span>
            </label>
            <textarea
              id="override-reason"
              className="override-panel__textarea"
              data-testid="override-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              placeholder="Explain why you are overriding the AI decision…"
            />
          </>
        )}

        <button
          type="submit"
          className="override-panel__submit"
          data-testid="submit-button"
          disabled={submitDisabled}
          aria-disabled={submitDisabled}
        >
          {submitting ? 'Submitting…' : 'Submit review'}
        </button>
      </form>
    </section>
  );
}
