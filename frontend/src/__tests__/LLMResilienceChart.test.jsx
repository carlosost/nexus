/**
 * Unit tests for LLMResilienceChart.
 *
 * BDD scenarios:
 *   Given no data → shows empty state
 *   Given data with all-zero counts → shows empty state
 *   Given data with non-zero values → chart is rendered, empty state absent
 *   Given data → legend labels "Primary" and "Fallback" are present
 */

import { describe, test, expect, beforeAll, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import LLMResilienceChart from '../components/LLMResilienceChart.jsx';

// ResponsiveContainer normally measures the DOM and clones its child with
// {width, height}. jsdom has no layout engine so it reports 0×0, causing
// AreaChart to bail out and render nothing (Legend included). We replace
// ResponsiveContainer with a version that injects fixed fake dimensions so
// the full chart tree — including Legend — renders in tests.
vi.mock('recharts', async () => {
  const actual = await vi.importActual('recharts');
  const { cloneElement } = await import('react');
  return {
    ...actual,
    ResponsiveContainer: ({ children, width = 800, height = 300 }) => (
      <div className="recharts-responsive-container" style={{ width, height }}>
        {cloneElement(children, { width: 800, height: 300 })}
      </div>
    ),
  };
});

beforeAll(() => {
  global.ResizeObserver = class {
    observe()    {}
    unobserve()  {}
    disconnect() {}
  };
});

const SERIES = [
  { date: '2024-01-09', primary: 0,   fallback: 0  },
  { date: '2024-01-10', primary: 45,  fallback: 2  },
  { date: '2024-01-11', primary: 67,  fallback: 0  },
  { date: '2024-01-12', primary: 120, fallback: 5  },
  { date: '2024-01-13', primary: 88,  fallback: 1  },
  { date: '2024-01-14', primary: 34,  fallback: 3  },
  { date: '2024-01-15', primary: 99,  fallback: 0  },
];

const ALL_ZERO = SERIES.map((d) => ({ ...d, primary: 0, fallback: 0 }));

describe('LLMResilienceChart', () => {

  // ── Empty states ──────────────────────────────────────────────────────────
  test('Given no data → shows empty state message', () => {
    render(<LLMResilienceChart data={[]} />);
    expect(screen.getByText(/no llm calls recorded/i)).toBeInTheDocument();
  });

  test('Given all-zero data → shows empty state message', () => {
    render(<LLMResilienceChart data={ALL_ZERO} />);
    expect(screen.getByText(/no llm calls recorded/i)).toBeInTheDocument();
  });

  test('Given no data prop → shows empty state', () => {
    render(<LLMResilienceChart />);
    expect(screen.getByText(/no llm calls recorded/i)).toBeInTheDocument();
  });

  // ── Data present ──────────────────────────────────────────────────────────
  test('Given non-zero data → empty state message is absent', () => {
    render(<LLMResilienceChart data={SERIES} />);
    expect(screen.queryByText(/no llm calls recorded/i)).not.toBeInTheDocument();
  });

  test('Given non-zero data → Recharts container is mounted', () => {
    const { container } = render(<LLMResilienceChart data={SERIES} />);
    expect(container.querySelector('.recharts-responsive-container')).toBeInTheDocument();
  });

  // ── Legend ────────────────────────────────────────────────────────────────
  test('Given non-zero data → "Primary" legend label is rendered', () => {
    render(<LLMResilienceChart data={SERIES} />);
    expect(screen.getByText('Primary')).toBeInTheDocument();
  });

  test('Given non-zero data → "Fallback" legend label is rendered', () => {
    render(<LLMResilienceChart data={SERIES} />);
    expect(screen.getByText('Fallback')).toBeInTheDocument();
  });

  // ── Single non-zero point ─────────────────────────────────────────────────
  test('Given one non-zero primary point → chart is rendered (not empty state)', () => {
    render(<LLMResilienceChart data={[
      { date: '2024-01-15', primary: 1, fallback: 0 },
    ]} />);
    expect(screen.queryByText(/no llm calls recorded/i)).not.toBeInTheDocument();
  });

  test('Given one non-zero fallback point → chart is rendered', () => {
    render(<LLMResilienceChart data={[
      { date: '2024-01-15', primary: 0, fallback: 1 },
    ]} />);
    expect(screen.queryByText(/no llm calls recorded/i)).not.toBeInTheDocument();
  });
});
