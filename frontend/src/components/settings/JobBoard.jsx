/**
 * JobBoard — administration board for Job records.
 *
 * Features:
 *   - List all jobs (title, created/updated timestamps)
 *   - Expand row to view description + must_haves criteria
 *   - Delete: hard-delete with cascade warning
 *   - Create: inline JobIngestionModal
 *
 * Props:
 *   jobs        {JobRow[]}
 *   loading     {boolean}
 *   error       {Error|null}
 *   onAdd       {(job) => void}
 *   onRemove    {(id: string) => void}
 */

import { useState } from 'react';
import DeleteConfirmModal from './DeleteConfirmModal.jsx';

function fmt(iso) {
  return iso ? new Date(iso).toLocaleDateString() : '—';
}

export default function JobBoard({ jobs, loading, error, onAdd, onRemove }) {
  const [expanded,     setExpanded]     = useState(null);   // job id
  const [deleteTarget, setDeleteTarget] = useState(null);   // job object

  function toggleExpand(id) {
    setExpanded((prev) => (prev === id ? null : id));
  }

  async function handleDelete() {
    await onRemove(deleteTarget.id);
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <section className="admin-board" data-testid="job-board">
      <div className="admin-board__header">
        <h2 className="admin-board__title">Jobs</h2>
        <button
          className="btn btn--primary btn--sm"
          onClick={() => onAdd()}
          data-testid="job-create-btn"
        >
          + Add Job
        </button>
      </div>

      {loading && (
        <div className="admin-board__placeholder" data-testid="jobs-loading-skeleton">
          <span className="spinner" /> Loading jobs…
        </div>
      )}

      {!loading && error && (
        <div className="admin-board__placeholder admin-board__placeholder--error" role="alert" data-testid="job-board-error">
          Failed to load jobs. <button className="btn-link" onClick={() => window.location.reload()}>Retry</button>
        </div>
      )}

      {!loading && !error && jobs.length === 0 && (
        <div className="admin-board__placeholder" data-testid="job-board-empty">
          No jobs yet. Click <strong>+ Add Job</strong> to create one.
        </div>
      )}

      {!loading && !error && jobs.length > 0 && (
        <table className="admin-table" data-testid="job-table">
          <thead>
            <tr>
              <th className="admin-table__th">Title</th>
              <th className="admin-table__th admin-table__th--date">Created</th>
              <th className="admin-table__th admin-table__th--date">Updated</th>
              <th className="admin-table__th admin-table__th--actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <>
                <tr
                  key={job.id}
                  className={`admin-table__row${expanded === job.id ? ' admin-table__row--expanded' : ''}`}
                  data-testid={`job-row-${job.id}`}
                >
                  <td className="admin-table__td">
                    <button
                      className="btn-link admin-table__expand-btn"
                      onClick={() => toggleExpand(job.id)}
                      aria-expanded={expanded === job.id}
                      aria-label={`Expand ${job.title}`}
                      data-testid={`job-expand-${job.id}`}
                    >
                      <span className="admin-table__chevron">{expanded === job.id ? '▾' : '▸'}</span>
                      {job.title}
                    </button>
                  </td>
                  <td className="admin-table__td admin-table__td--date">{fmt(job.created_at)}</td>
                  <td className="admin-table__td admin-table__td--date">{fmt(job.updated_at)}</td>
                  <td className="admin-table__td admin-table__td--actions">
                    <button
                      className="btn btn--danger-outline btn--sm"
                      onClick={() => setDeleteTarget(job)}
                      data-testid={`job-delete-${job.id}`}
                    >
                      Delete
                    </button>
                  </td>
                </tr>

                {expanded === job.id && (
                  <tr key={`${job.id}-detail`} className="admin-table__detail-row">
                    <td colSpan={4} className="admin-table__detail-cell">
                      <div className="job-detail" data-testid={`job-detail-${job.id}`}>
                        <div className="job-detail__section">
                          <h4 className="job-detail__label">Description</h4>
                          <p className="job-detail__text">{job.description || '—'}</p>
                        </div>
                        {job.must_haves && Object.keys(job.must_haves).length > 0 && (
                          <div className="job-detail__section">
                            <h4 className="job-detail__label">Hard Gate Criteria</h4>
                            <pre className="job-detail__json">
                              {JSON.stringify(job.must_haves, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      )}

      {/* ── Modals ──────────────────────────────────────────────────────────── */}

      <DeleteConfirmModal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        entityLabel={deleteTarget ? `"${deleteTarget.title}"` : ''}
        warning="This will also delete all Applications linked to this job."
      />
    </section>
  );
}
