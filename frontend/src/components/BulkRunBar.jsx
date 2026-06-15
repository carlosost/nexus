/**
 * BulkRunBar — sticky action bar that slides in when ≥1 row is selected.
 *
 * Shows:
 *   - How many applications are selected
 *   - "Run Pipeline" button (triggers async evaluation for all selected)
 *   - "Clear" button to deselect all
 *
 * Props:
 *   count         {number}    number of selected applications
 *   onRun         {Function}  called when "Run Pipeline" is clicked
 *   onClear       {Function}  called when "Clear" is clicked
 *   isRunning     {boolean}   true while any pipeline requests are in flight
 */

export default function BulkRunBar({ count, onRun, onClear, isRunning }) {
  if (count === 0) return null;

  return (
    <div className="bulk-run-bar" role="toolbar" data-testid="bulk-run-bar" aria-label="Bulk actions">
      <span className="bulk-run-bar__count">
        {count} application{count !== 1 ? 's' : ''} selected
      </span>

      <div className="bulk-run-bar__actions">
        <button
          className="btn btn--ghost"
          onClick={onClear}
          disabled={isRunning}
          type="button"
        >
          Clear
        </button>
        <button
          className="btn btn--primary"
          onClick={onRun}
          disabled={isRunning}
          type="button"
          data-testid="bulk-run-btn"
        >
          {isRunning ? 'Running…' : '▶ Run Pipeline'}
        </button>
      </div>
    </div>
  );
}
