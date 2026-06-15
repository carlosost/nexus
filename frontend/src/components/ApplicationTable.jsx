/**
 * ApplicationTable — scannable inventory of all applications.
 *
 * Features:
 *   - Checkbox per row + select-all header checkbox
 *   - StatusBadge with inline spinner for "processing" rows
 *   - FallbackAlert icon on rows evaluated via backup LLM
 *   - Final score rendered as percentage or "—" if not yet scored
 *   - Clicking a row (outside the checkbox) navigates to /review/:id
 *   - Empty and loading states handled inline
 *
 * Props:
 *   applications   {ApplicationRow[]}
 *   selected       {Set<string>}          currently checked IDs
 *   pollingIds     {Set<string>}          IDs whose run is in flight
 *   onToggle       {(id: string) => void}
 *   onToggleAll    {() => void}
 *   loading        {boolean}
 *   error          {Error | null}
 */

import StatusBadge  from './StatusBadge.jsx';
import FallbackAlert from './FallbackAlert.jsx';

function pct(v) {
  return v == null ? '—' : `${Math.round(v * 100)}%`;
}

function fmt(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

export default function ApplicationTable({
  applications,
  selected,
  pollingIds,
  onToggle,
  onToggleAll,
  onReview,
  onRun,
  loading,
  error,
}) {
  const allSelected =
    applications.length > 0 && selected.size === applications.length;
  const someSelected = selected.size > 0 && !allSelected;

  if (loading) {
    return (
      <div className="table-placeholder" data-testid="table-loading">
        <span className="spinner" aria-label="Loading applications…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="table-placeholder table-placeholder--error" role="alert">
        Failed to load applications: {error.message}
      </div>
    );
  }

  if (applications.length === 0) {
    return (
      <div className="table-placeholder" data-testid="table-empty">
        <p>No applications yet.</p>
        <p>Add a Job and a Candidate, then create an Application to get started.</p>
      </div>
    );
  }

  return (
    <div className="table-wrapper">
      <table className="app-table" data-testid="application-table">
        <thead>
          <tr>
            <th className="app-table__check">
              <input
                type="checkbox"
                checked={allSelected}
                ref={(el) => {
                  if (el) el.indeterminate = someSelected;
                }}
                onChange={onToggleAll}
                aria-label="Select all applications"
              />
            </th>
            <th>Candidate</th>
            <th>Job</th>
            <th>Status</th>
            <th className="app-table__score">Score</th>
            <th className="app-table__date">Created</th>
            <th className="app-table__action" />
          </tr>
        </thead>

        <tbody>
          {applications.map((app) => {
            const isPolling = pollingIds.has(app.id);
            const isChecked = selected.has(app.id);

            return (
              <tr
                key={app.id}
                className={[
                  'app-table__row',
                  isPolling  ? 'app-table__row--polling'  : '',
                  isChecked  ? 'app-table__row--selected' : '',
                ].join(' ').trim()}
                data-testid="app-row"
              >
                <td className="app-table__check">
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => onToggle(app.id)}
                    aria-label={`Select ${app.candidate_name}`}
                    onClick={(e) => e.stopPropagation()}
                  />
                </td>

                <td>
                  <span className="app-table__name">{app.candidate_name}</span>
                  <span className="app-table__email">{app.candidate_email}</span>
                </td>

                <td className="app-table__job">{app.job_title}</td>

                <td>
                  <StatusBadge status={isPolling ? 'processing' : app.status} />
                </td>

                <td className="app-table__score">
                  {pct(app.final_score)}
                  {app.is_evaluated_via_fallback && <FallbackAlert />}
                </td>

                <td className="app-table__date">{fmt(app.created_at)}</td>

                <td className="app-table__action">
                  <button
                    className="btn btn--sm btn--ghost"
                    onClick={() => onRun(app.id)}
                    aria-label={`Run pipeline for ${app.candidate_name}`}
                    type="button"
                    disabled={isPolling}
                  >
                    ▶ Run
                  </button>
                  <button
                    className="btn btn--sm btn--ghost"
                    onClick={() => onReview(app.id)}
                    aria-label={`Review ${app.candidate_name}`}
                    type="button"
                  >
                    Review →
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
