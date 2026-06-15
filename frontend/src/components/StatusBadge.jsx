/**
 * StatusBadge — pill-shaped indicator for Application.status values.
 *
 * Maps each backend enum value to a semantic colour tier:
 *   pending          → neutral grey
 *   processing       → blue (local optimistic sentinel — not a backend value)
 *   gate_failed      → red
 *   gate_unknown     → amber
 *   gate_passed      → teal
 *   scored           → green
 *   under_review     → purple
 *   approved         → green (darker)
 *   rejected         → red   (darker)
 */

const LABEL = {
  pending:      'Pending',
  processing:   'Processing…',
  gate_failed:  'Gate Failed',
  gate_unknown: 'Gate Unknown',
  gate_passed:  'Gate Passed',
  scored:       'Scored',
  under_review: 'Under Review',
  approved:     'Approved',
  rejected:     'Rejected',
};

export default function StatusBadge({ status }) {
  const label = LABEL[status] ?? status;
  return (
    <span className={`status-badge status-badge--${status}`} data-testid="status-badge">
      {status === 'processing' && (
        <span className="status-badge__spinner" aria-hidden="true" />
      )}
      {label}
    </span>
  );
}
