/**
 * Unit tests for StatusDistributionChart.
 *
 * Recharts renders SVG via its internal ResizeObserver. jsdom doesn't have a
 * real layout engine, so Recharts often produces empty SVG or relies on
 * container dimensions. We test component-level contract:
 *   - empty state message when all counts are zero
 *   - empty state message when data array is empty
 *   - chart container rendered when data has non-zero entries
 *   - legend items rendered for each non-zero status
 *
 * We do NOT assert on SVG path geometry (that is Recharts' responsibility).
 */

import { describe, test, expect, beforeAll } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusDistributionChart from '../components/StatusDistributionChart.jsx';

// Recharts uses ResizeObserver internally — stub it for jsdom.
beforeAll(() => {
  global.ResizeObserver = class {
    observe()   {}
    unobserve() {}
    disconnect() {}
  };
});

const FULL_DATA = [
  { status: 'pending',      label: 'Pending',      count: 10 },
  { status: 'gate_failed',  label: 'Gate Failed',  count: 3  },
  { status: 'gate_unknown', label: 'Gate Unknown', count: 1  },
  { status: 'gate_passed',  label: 'Gate Passed',  count: 5  },
  { status: 'scored',       label: 'Scored',       count: 22 },
  { status: 'under_review', label: 'Under Review', count: 4  },
  { status: 'approved',     label: 'Approved',     count: 8  },
  { status: 'rejected',     label: 'Rejected',     count: 2  },
];

const ALL_ZERO = FULL_DATA.map((d) => ({ ...d, count: 0 }));

describe('StatusDistributionChart', () => {

  // ── Empty states ──────────────────────────────────────────────────────────
  test('Given empty data array → shows empty state message', () => {
    render(<StatusDistributionChart data={[]} />);
    expect(screen.getByText(/no applications yet/i)).toBeInTheDocument();
  });

  test('Given all counts are zero → shows empty state message', () => {
    render(<StatusDistributionChart data={ALL_ZERO} />);
    expect(screen.getByText(/no applications yet/i)).toBeInTheDocument();
  });

  test('Given default (no data prop) → shows empty state message', () => {
    render(<StatusDistributionChart />);
    expect(screen.getByText(/no applications yet/i)).toBeInTheDocument();
  });

  // ── Data present ──────────────────────────────────────────────────────────
  test('Given non-zero data → empty state message is absent', () => {
    render(<StatusDistributionChart data={FULL_DATA} />);
    expect(screen.queryByText(/no applications yet/i)).not.toBeInTheDocument();
  });

  // ── Custom legend ─────────────────────────────────────────────────────────
  test('Given non-zero data → legend item rendered for each non-zero status', () => {
    render(<StatusDistributionChart data={FULL_DATA} />);
    // Every non-zero entry's label should appear in the custom legend
    const nonZero = FULL_DATA.filter((d) => d.count > 0);
    for (const entry of nonZero) {
      expect(screen.getByText(entry.label)).toBeInTheDocument();
    }
  });

  test('Given non-zero data → legend shows count for each entry', () => {
    render(<StatusDistributionChart data={[
      { status: 'scored', label: 'Scored', count: 42 },
    ]} />);
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  test('Given mixed zero and non-zero → only non-zero entries appear in legend', () => {
    const mixed = [
      { status: 'scored',      label: 'Scored',      count: 5 },
      { status: 'gate_failed', label: 'Gate Failed',  count: 0 },
    ];
    render(<StatusDistributionChart data={mixed} />);
    expect(screen.getByText('Scored')).toBeInTheDocument();
    // Gate Failed has count 0 → filtered out of nonZero → not in legend
    expect(screen.queryByText('Gate Failed')).not.toBeInTheDocument();
  });

  // ── CSS structure ─────────────────────────────────────────────────────────
  test('Given non-zero data → renders donut-legend container', () => {
    const { container } = render(<StatusDistributionChart data={FULL_DATA} />);
    expect(container.querySelector('.donut-legend')).toBeInTheDocument();
  });

  test('Given non-zero data → each legend item has a color dot', () => {
    const { container } = render(<StatusDistributionChart data={[
      { status: 'pending', label: 'Pending', count: 3 },
    ]} />);
    expect(container.querySelector('.donut-legend__dot')).toBeInTheDocument();
  });
});
