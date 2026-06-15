/**
 * Unit tests for JobFunnelChart.
 *
 * BDD scenarios:
 *   Given total count is 0 → empty state message shown
 *   Given all counts are 0 → empty state message shown
 *   Given no data prop → empty state message shown
 *   Given data with non-zero counts → empty state is absent
 *   Given data with labels → labels are accessible in the DOM (YAxis)
 */

import { describe, test, expect, beforeAll } from 'vitest';
import { render, screen } from '@testing-library/react';
import JobFunnelChart from '../components/JobFunnelChart.jsx';

beforeAll(() => {
  global.ResizeObserver = class {
    observe()    {}
    unobserve()  {}
    disconnect() {}
  };
});

const FUNNEL_DATA = [
  { status: 'completed', label: 'Completed',            count: 12 },
  { status: 'running',   label: 'Running',              count: 3  },
  { status: 'failed',    label: 'Failed',               count: 1  },
  { status: 'fallback',  label: 'Retrying via Fallback', count: 0  },
];

const ALL_ZERO = FUNNEL_DATA.map((d) => ({ ...d, count: 0 }));

describe('JobFunnelChart', () => {

  // ── Empty states ──────────────────────────────────────────────────────────
  test('Given empty data → shows empty state message', () => {
    render(<JobFunnelChart data={[]} />);
    expect(screen.getByText(/no activity in the last 24/i)).toBeInTheDocument();
  });

  test('Given all counts zero → shows empty state message', () => {
    render(<JobFunnelChart data={ALL_ZERO} />);
    expect(screen.getByText(/no activity in the last 24/i)).toBeInTheDocument();
  });

  test('Given no data prop → shows empty state', () => {
    render(<JobFunnelChart />);
    expect(screen.getByText(/no activity in the last 24/i)).toBeInTheDocument();
  });

  // ── Data present ──────────────────────────────────────────────────────────
  test('Given non-zero data → empty state message is absent', () => {
    render(<JobFunnelChart data={FUNNEL_DATA} />);
    expect(screen.queryByText(/no activity/i)).not.toBeInTheDocument();
  });

  test('Given non-zero data → Recharts ResponsiveContainer is mounted', () => {
    const { container } = render(<JobFunnelChart data={FUNNEL_DATA} />);
    // Recharts wraps in a div with recharts-wrapper or recharts-responsive-container
    expect(container.querySelector('.recharts-responsive-container')).toBeInTheDocument();
  });

  // ── YAxis labels ─────────────────────────────────────────────────────────
  test('Given funnel data → category labels are rendered in YAxis', () => {
    render(<JobFunnelChart data={FUNNEL_DATA} />);
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  test('Given single non-zero bucket → only that bucket avoids empty state', () => {
    render(<JobFunnelChart data={[
      { status: 'completed', label: 'Completed', count: 1 },
      { status: 'running',   label: 'Running',   count: 0 },
    ]} />);
    expect(screen.queryByText(/no activity/i)).not.toBeInTheDocument();
  });
});
