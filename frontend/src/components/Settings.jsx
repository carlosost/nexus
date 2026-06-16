/**
 * Settings — administrative control center.
 *
 * Provides three tabbed panels:
 *   Jobs        — create / view / edit / delete Job records
 *   Candidates  — create / view / edit / delete Candidate records
 *   Applications — link a Job to a Candidate (create Application)
 *
 * This page owns the authoritative useJobs / useCandidates data fetches.
 * The Dashboard no longer imports those hooks — it is purely read-only.
 *
 * Route: /settings  (wired in main.jsx)
 */

import { useState } from 'react';
import { useJobs }       from '../hooks/useJobs.js';
import { useCandidates } from '../hooks/useCandidates.js';
import JobBoard           from './settings/JobBoard.jsx';
import CandidateBoard     from './settings/CandidateBoard.jsx';
import ApplicationCenter  from './settings/ApplicationCenter.jsx';
import JobIngestionModal  from './JobIngestionModal.jsx';
import { deleteJob }      from '../api/client.js';
import '../styles/settings.css';

const TABS = [
  { id: 'jobs',         label: 'Jobs' },
  { id: 'candidates',   label: 'Candidates' },
  { id: 'applications', label: 'Applications' },
];

export default function Settings() {
  const [activeTab,   setActiveTab]   = useState('jobs');
  const [creatingJob, setCreatingJob] = useState(false);

  const {
    jobs,
    loading:  jobsLoading,
    error:    jobsError,
    addJob,
    removeJob,
  } = useJobs();

  const {
    candidates,
    loading:  candidatesLoading,
    error:    candidatesError,
    addCandidate,
    removeCandidate,
  } = useCandidates();

  return (
    <div className="settings">
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <header className="settings__header">
        <div className="settings__brand">
          <a href="/" className="settings__back" aria-label="Back to Dashboard">
            ← Dashboard
          </a>
          <span className="settings__divider" aria-hidden="true">|</span>
          <span className="settings__title">Settings</span>
        </div>
      </header>

      {/* ── Tab navigation ────────────────────────────────────────────────── */}
      <nav className="settings__tabs" role="tablist" aria-label="Settings sections">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`panel-${tab.id}`}
            id={`tab-${tab.id}`}
            className={`settings__tab${activeTab === tab.id ? ' settings__tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
            data-testid={`tab-${tab.id}`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* ── Panel: Jobs ──────────────────────────────────────────────────── */}
      <div
        role="tabpanel"
        id="panel-jobs"
        aria-labelledby="tab-jobs"
        hidden={activeTab !== 'jobs'}
        className="settings__panel"
      >
        <JobBoard
          jobs={jobs}
          loading={jobsLoading}
          error={jobsError}
          onAdd={() => setCreatingJob(true)}
          onRemove={async (id) => { await deleteJob(id); removeJob(id); }}
        />
      </div>

      {/* ── Panel: Candidates ────────────────────────────────────────────── */}
      <div
        role="tabpanel"
        id="panel-candidates"
        aria-labelledby="tab-candidates"
        hidden={activeTab !== 'candidates'}
        className="settings__panel"
      >
        <CandidateBoard
          candidates={candidates}
          loading={candidatesLoading}
          error={candidatesError}
          onAdd={addCandidate}
          onRemove={removeCandidate}
        />
      </div>

      {/* ── Panel: Applications ──────────────────────────────────────────── */}
      <div
        role="tabpanel"
        id="panel-applications"
        aria-labelledby="tab-applications"
        hidden={activeTab !== 'applications'}
        className="settings__panel"
      >
        <ApplicationCenter
          jobs={jobs}
          candidates={candidates}
          onSuccess={() => {/* navigation to dashboard handled inside component */}}
        />
      </div>
      <JobIngestionModal
        open={creatingJob}
        onClose={() => setCreatingJob(false)}
        onSuccess={(job) => { addJob(job); setCreatingJob(false); }}
      />
    </div>
  );
}
