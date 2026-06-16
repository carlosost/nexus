/**
 * Dashboard — operational overview + application inventory.
 *
 * Layout:
 *   ── Header (branding + Settings link)
 *   ── StatsSection
 *      ├── 4× MetricCard (total apps, active jobs, users, LLM success rate)
 *      └── 3× Chart cards
 *           ├── StatusDistributionChart (donut — application status breakdown)
 *           ├── JobFunnelChart          (horizontal bar — last-24 h execution)
 *           └── LLMResilienceChart      (area — 7-day primary vs fallback)
 *   ── BulkRunBar  (visible when ≥1 row selected)
 *   ── ApplicationTable
 */

import { useState }              from 'react';
import { useApplications }       from '../hooks/useApplications.js';
import { useDashboardStats }     from '../hooks/useDashboardStats.js';
import ApplicationTable          from './ApplicationTable.jsx';
import BulkRunBar                from './BulkRunBar.jsx';
import MetricCard                from './MetricCard.jsx';
import ReviewModal               from './ReviewModal.jsx';
import StatusDistributionChart   from './StatusDistributionChart.jsx';
import JobFunnelChart            from './JobFunnelChart.jsx';
import LLMResilienceChart        from './LLMResilienceChart.jsx';

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmt(n) {
  if (n == null) return '—';
  return Number.isInteger(n) ? n.toLocaleString() : n;
}

// ── Stats section ─────────────────────────────────────────────────────────────

function StatsSection({ stats, loading, error, onRefresh }) {
  const totals = stats?.totals ?? {};
  const statusDist  = stats?.application_status_distribution ?? [];
  const funnelData  = stats?.job_execution_funnel ?? [];
  const resilience  = stats?.llm_resilience?.time_series ?? [];

  return (
    <section className={`stats-section${loading ? ' stats-section--loading' : ''}`}>
      {error && (
        <div className="stats-error">
          <span>⚠</span>
          <span>Could not load dashboard stats — {error.message}</span>
          <button className="btn btn--ghost btn--sm" onClick={onRefresh}>Retry</button>
        </div>
      )}

      {/* ── Metric cards ───────────────────────────────────────────────────── */}
      <div className="stats-grid">
        <MetricCard
          label="Total Applications"
          value={fmt(totals.applications)}
          icon="📋"
          color="brand"
        />
        <MetricCard
          label="Candidates"
          value={fmt(totals.candidates)}
          icon="👤"
          color="teal"
        />
        <MetricCard
          label="Jobs"
          value={fmt(totals.jobs)}
          icon="💼"
          color="purple"
        />
        <MetricCard
          label="Active In Pipeline"
          value={fmt(totals.active_jobs)}
          icon="⚙"
          color="info"
          sub="pending / gate-passed / gate-unknown"
        />
        <MetricCard
          label="LLM Success Rate"
          value={totals.llm_success_rate != null ? `${totals.llm_success_rate}%` : '—'}
          icon="🤖"
          color={totals.llm_success_rate >= 90 ? 'success' : totals.llm_success_rate >= 70 ? 'warning' : 'danger'}
          sub="primary backend calls"
        />
      </div>

      {/* ── Charts ─────────────────────────────────────────────────────────── */}
      <div className="charts-grid">
        {/* Donut — application status */}
        <div className="chart-card">
          <div className="chart-card__title">Application Status</div>
          <div className="chart-card__body">
            <StatusDistributionChart data={statusDist} />
          </div>
        </div>

        {/* Horizontal bars — job execution funnel last 24 h */}
        <div className="chart-card">
          <div className="chart-card__title">Job Execution</div>
          <div className="chart-card__subtitle">Last 24 hours</div>
          <div className="chart-card__body">
            <JobFunnelChart data={funnelData} />
          </div>
        </div>

        {/* Stacked area — LLM resilience 7 days */}
        <div className="chart-card">
          <div className="chart-card__title">LLM Resilience</div>
          <div className="chart-card__subtitle">Primary vs fallback — last 7 days</div>
          <div className="chart-card__body">
            <LLMResilienceChart data={resilience} />
          </div>
        </div>
      </div>
    </section>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [reviewId, setReviewId] = useState(null);

  const {
    applications,
    loading: appsLoading,
    error: appsError,
    pollingIds,
    runErrors,
    selected,
    toggleSelect,
    toggleSelectAll,
    clearSelection,
    runSelected,
    runSingle,
  } = useApplications();

  const {
    stats,
    loading: statsLoading,
    error:   statsError,
    refetch: refetchStats,
  } = useDashboardStats();

  const isRunning = pollingIds.size > 0;

  return (
    <div className="dashboard">
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <header className="dashboard__header">
        <div className="dashboard__brand">
          <span className="dashboard__logo">⬡</span>
          <span className="dashboard__title">Elvex Nexus</span>
          <span className="dashboard__subtitle">Candidate Screening</span>
        </div>

        <nav className="dashboard__actions">
          <a href="/settings" className="btn btn--outline">
            ⚙ Settings
          </a>
        </nav>
      </header>

      {/* ── Telemetry stats ──────────────────────────────────────────────── */}
      <StatsSection
        stats={stats}
        loading={statsLoading}
        error={statsError}
        onRefresh={refetchStats}
      />

      {/* ── Bulk action bar ───────────────────────────────────────────────── */}
      <BulkRunBar
        count={selected.size}
        onRun={runSelected}
        onClear={clearSelection}
        isRunning={isRunning}
      />

      {/* ── Application inventory ─────────────────────────────────────────── */}
      <main className="dashboard__main">
        <div className="dashboard__table-header">
          <h2 className="dashboard__section-title">
            Applications
            {applications.length > 0 && (
              <span className="dashboard__count">{applications.length}</span>
            )}
          </h2>
          {isRunning && (
            <span className="dashboard__running-badge">
              <span className="spinner spinner--sm" />
              {pollingIds.size} running…
            </span>
          )}
        </div>

        <ApplicationTable
          applications={applications}
          selected={selected}
          pollingIds={pollingIds}
          runErrors={runErrors}
          onToggle={toggleSelect}
          onToggleAll={toggleSelectAll}
          onReview={setReviewId}
          onRun={runSingle}
          loading={appsLoading}
          error={appsError}
        />
      </main>

      <ReviewModal applicationId={reviewId} onClose={() => setReviewId(null)} />
    </div>
  );
}
