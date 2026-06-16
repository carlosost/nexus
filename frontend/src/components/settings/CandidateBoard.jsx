/**
 * CandidateBoard — full CRUD administration board for Candidate records.
 *
 * Features:
 *   - List all candidates (name, email, created timestamp)
 *   - Expand row to view parsed resume sections
 *   - Delete: hard-delete with cascade warning
 *   - Create: inline CandidateIngestionModal (PDF upload)
 *
 * Props:
 *   candidates  {CandidateRow[]}
 *   loading     {boolean}
 *   error       {Error|null}
 *   onAdd       {(candidate) => void}
 *   onRemove    {(id: string) => void}
 */

import React, { useState, useCallback } from 'react';
import CandidateIngestionModal from '../CandidateIngestionModal.jsx';
import DeleteConfirmModal      from './DeleteConfirmModal.jsx';
import { deleteCandidate, getCandidate } from '../../api/client.js';

function fmt(iso) {
  return iso ? new Date(iso).toLocaleDateString() : '—';
}

export default function CandidateBoard({
  candidates, loading, error, onAdd, onRemove,
}) {
  const [expanded,     setExpanded]    = useState(null);
  const [creating,     setCreating]    = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [detailCache,  setDetailCache] = useState({});
  const [detailLoading, setDetailLoading] = useState(null);

  const toggleExpand = useCallback(async (id) => {
    if (expanded === id) {
      setExpanded(null);
      return;
    }
    setExpanded(id);
    if (!detailCache[id]) {
      setDetailLoading(id);
      try {
        const detail = await getCandidate(id);
        setDetailCache((prev) => ({ ...prev, [id]: detail }));
      } finally {
        setDetailLoading(null);
      }
    }
  }, [expanded, detailCache]);

  async function handleDelete() {
    await deleteCandidate(deleteTarget.id);
    onRemove(deleteTarget.id);
  }

  return (
    <section className="admin-board" data-testid="candidate-board">
      <div className="admin-board__header">
        <h2 className="admin-board__title">Candidates</h2>
        <button
          className="btn btn--primary btn--sm"
          onClick={() => setCreating(true)}
          data-testid="candidate-create-btn"
        >
          + Add Candidate
        </button>
      </div>

      {loading && (
        <div className="admin-board__placeholder" data-testid="candidate-board-loading">
          <span className="spinner" /> Loading candidates…
        </div>
      )}

      {!loading && error && (
        <div className="admin-board__placeholder admin-board__placeholder--error" data-testid="candidate-board-error">
          Failed to load candidates.{' '}
          <button className="btn-link" onClick={() => window.location.reload()}>Retry</button>
        </div>
      )}

      {!loading && !error && candidates.length === 0 && (
        <div className="admin-board__placeholder" data-testid="candidate-board-empty">
          No candidates yet. Click <strong>+ Add Candidate</strong> to upload a resume.
        </div>
      )}

      {!loading && !error && candidates.length > 0 && (
        <table className="admin-table" data-testid="candidate-table">
          <thead>
            <tr>
              <th className="admin-table__th">Name</th>
              <th className="admin-table__th">Email</th>
              <th className="admin-table__th admin-table__th--date">Added</th>
              <th className="admin-table__th admin-table__th--actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <React.Fragment key={c.id}>
                <tr
                  key={c.id}
                  className={`admin-table__row${expanded === c.id ? ' admin-table__row--expanded' : ''}`}
                  data-testid={`candidate-row-${c.id}`}
                >
                  <td className="admin-table__td">
                    <button
                      className="btn-link admin-table__expand-btn"
                      onClick={() => toggleExpand(c.id)}
                      aria-expanded={expanded === c.id}
                      data-testid={`candidate-expand-${c.id}`}
                    >
                      <span className="admin-table__chevron">{expanded === c.id ? '▾' : '▸'}</span>
                      {c.name}
                    </button>
                  </td>
                  <td className="admin-table__td">{c.email}</td>
                  <td className="admin-table__td admin-table__td--date">{fmt(c.created_at)}</td>
                  <td className="admin-table__td admin-table__td--actions">
                    <button
                      className="btn btn--danger-outline btn--sm"
                      onClick={() => setDeleteTarget(c)}
                      data-testid={`candidate-delete-${c.id}`}
                    >
                      Delete
                    </button>
                  </td>
                </tr>

                {expanded === c.id && (
                  <tr key={`${c.id}-detail`} className="admin-table__detail-row">
                    <td colSpan={4} className="admin-table__detail-cell">
                      <div className="candidate-detail" data-testid={`candidate-detail-${c.id}`}>
                        {detailLoading === c.id ? (
                          <p className="candidate-detail__text"><span className="spinner" /> Loading…</p>
                        ) : (() => {
                          const parsed = detailCache[c.id]?.resume_parsed;
                          const textSections = parsed
                            ? Object.entries(parsed).filter(([, v]) => typeof v === 'string' && v.trim())
                            : [];
                          return textSections.length > 0
                            ? textSections.map(([section, text]) => (
                                <div key={section} className="candidate-detail__section">
                                  <h4 className="candidate-detail__label">
                                    {section.replace(/_/g, ' ')}
                                  </h4>
                                  <p className="candidate-detail__text">{text}</p>
                                </div>
                              ))
                            : <p className="candidate-detail__text">No parsed sections available.</p>;
                        })()}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      )}

      {/* ── Modals ──────────────────────────────────────────────────────────── */}

      <CandidateIngestionModal
        open={creating}
        onClose={() => setCreating(false)}
        onSuccess={(candidate) => { onAdd(candidate); setCreating(false); }}
      />

      <DeleteConfirmModal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        entityLabel={deleteTarget ? deleteTarget.name : ''}
        warning="All Applications linked to this candidate will also be permanently deleted."
      />
    </section>
  );
}
