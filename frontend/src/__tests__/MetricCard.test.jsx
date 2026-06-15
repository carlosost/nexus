/**
 * Unit tests for MetricCard.
 *
 * BDD scenarios:
 *   Given a label and value → card renders both
 *   Given a null/undefined value → card renders the em-dash fallback
 *   Given an icon prop → icon is rendered
 *   Given a sub prop → sub-label is rendered beneath the value
 *   Given no sub prop → no sub-label element
 *   Given a color prop → CSS custom property is set on the container
 *   Given no color prop → defaults to brand color
 */

import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import MetricCard from '../components/MetricCard.jsx';

function renderCard(props = {}) {
  const defaults = { label: 'Total Applications', value: 42 };
  return render(<MetricCard {...defaults} {...props} />);
}

describe('MetricCard', () => {

  // ── Rendering — label and value ───────────────────────────────────────────
  test('Given label and value → both are rendered', () => {
    renderCard({ label: 'Active Jobs', value: 7 });
    expect(screen.getByText('Active Jobs')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
  });

  test('Given string value → renders string', () => {
    renderCard({ value: '94.2%' });
    expect(screen.getByText('94.2%')).toBeInTheDocument();
  });

  test('Given value of 0 → renders 0 not the fallback dash', () => {
    renderCard({ value: 0 });
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.queryByText('—')).not.toBeInTheDocument();
  });

  // ── Null / undefined value fallback ──────────────────────────────────────
  test('Given null value → renders em-dash', () => {
    renderCard({ value: null });
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  test('Given undefined value → renders em-dash', () => {
    renderCard({ value: undefined });
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  // ── Icon prop ─────────────────────────────────────────────────────────────
  test('Given icon prop → icon character is rendered', () => {
    renderCard({ icon: '📋' });
    expect(screen.getByText('📋')).toBeInTheDocument();
  });

  test('Given no icon prop → no icon element rendered', () => {
    const { container } = renderCard({ icon: undefined });
    expect(container.querySelector('.metric-card__icon')).not.toBeInTheDocument();
  });

  // ── Sub-label prop ────────────────────────────────────────────────────────
  test('Given sub prop → sub-label is rendered', () => {
    renderCard({ sub: 'last 24 hours' });
    expect(screen.getByText('last 24 hours')).toBeInTheDocument();
  });

  test('Given no sub prop → sub-label element is absent', () => {
    const { container } = renderCard({ sub: undefined });
    expect(container.querySelector('.metric-card__sub')).not.toBeInTheDocument();
  });

  // ── Color / CSS custom property ───────────────────────────────────────────
  test('Given color="success" → --metric-color is set to var(--color-success)', () => {
    const { container } = renderCard({ color: 'success' });
    const card = container.querySelector('.metric-card');
    expect(card).toHaveStyle('--metric-color: var(--color-success)');
  });

  test('Given color="danger" → --metric-color is set to var(--color-danger)', () => {
    const { container } = renderCard({ color: 'danger' });
    const card = container.querySelector('.metric-card');
    expect(card).toHaveStyle('--metric-color: var(--color-danger)');
  });

  test('Given no color prop → defaults to var(--color-brand)', () => {
    const { container } = renderCard({ color: undefined });
    const card = container.querySelector('.metric-card');
    expect(card).toHaveStyle('--metric-color: var(--color-brand)');
  });

  // ── CSS class structure ───────────────────────────────────────────────────
  test('Root element has metric-card class', () => {
    const { container } = renderCard();
    expect(container.querySelector('.metric-card')).toBeInTheDocument();
  });

  test('Label element has metric-card__label class', () => {
    const { container } = renderCard({ label: 'Test Label' });
    const label = container.querySelector('.metric-card__label');
    expect(label).toBeInTheDocument();
    expect(label).toHaveTextContent('Test Label');
  });

  test('Value element has metric-card__value class', () => {
    const { container } = renderCard({ value: 99 });
    const val = container.querySelector('.metric-card__value');
    expect(val).toBeInTheDocument();
    expect(val).toHaveTextContent('99');
  });
});
