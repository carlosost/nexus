/**
 * AuditTrail — list of human reviews for an application.
 *
 * Props:
 *   reviews  {Array}  Array of review objects:
 *     { id, reviewer_email, decision, override_reason, reviewed_at }
 */

const DECISION_LABELS = {
  approve:       'Approve',
  reject:        'Reject',
  override_pass: 'Override → Pass',
  override_fail: 'Override → Fail',
};

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export default function AuditTrail({ reviews = [] }) {
  if (reviews.length === 0) {
    return (
      <section className="audit-trail" aria-label="Audit trail">
        <h2 className="audit-trail__title">Review History</h2>
        <p className="audit-trail__empty">No reviews submitted yet.</p>
      </section>
    );
  }

  return (
    <section className="audit-trail" aria-label="Audit trail">
      <h2 className="audit-trail__title">Review History</h2>
      <ul className="audit-trail__list">
        {reviews.map((review) => (
          <li key={review.id} className="audit-trail__item">
            <span
              className="audit-trail__reviewer"
              data-testid={`reviewer-${review.id}`}
            >
              {review.reviewer_email}
            </span>
            <span
              className="audit-trail__decision"
              data-testid={`decision-${review.id}`}
            >
              {DECISION_LABELS[review.decision] ?? review.decision}
            </span>
            {review.override_reason && (
              <span
                className="audit-trail__reason"
                data-testid={`reason-${review.id}`}
              >
                "{review.override_reason}"
              </span>
            )}
            <time
              className="audit-trail__time"
              dateTime={review.reviewed_at}
              data-testid={`time-${review.id}`}
            >
              {formatDate(review.reviewed_at)}
            </time>
          </li>
        ))}
      </ul>
    </section>
  );
}
