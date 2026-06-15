/**
 * StatusDistributionChart — donut chart of application status breakdown.
 *
 * Uses Recharts PieChart. Colors are hardcoded hex values matching the
 * project's CSS custom property design tokens (dark theme).
 *
 * Props:
 *   data  Array<{ status: string, label: string, count: number }>
 */

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const STATUS_COLORS = {
  pending:      '#555e85',
  gate_failed:  '#ef4444',
  gate_unknown: '#f59e0b',
  gate_passed:  '#14b8a6',
  scored:       '#22c55e',
  under_review: '#a78bfa',
  approved:     '#22c55e',
  rejected:     '#ef4444',
};

const FALLBACK_COLORS = [
  '#5c6ef8', '#22c55e', '#f59e0b', '#ef4444',
  '#38bdf8', '#14b8a6', '#a78bfa', '#555e85',
];

function getColor(status, index) {
  return STATUS_COLORS[status] ?? FALLBACK_COLORS[index % FALLBACK_COLORS.length];
}

const tooltipStyle = {
  background:   '#1a1d27',
  border:       '1px solid #2e3352',
  borderRadius: '6px',
  color:        '#c8cee8',
  fontSize:     '12px',
};

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const { label, count } = payload[0].payload;
  return (
    <div style={tooltipStyle}>
      <div style={{ padding: '6px 10px' }}>
        <span style={{ color: payload[0].fill, marginRight: 6 }}>●</span>
        {label}: <strong style={{ color: '#fff' }}>{count}</strong>
      </div>
    </div>
  );
}

function CustomLegend({ data }) {
  return (
    <ul className="donut-legend">
      {data.map((entry, i) => (
        <li key={entry.status} className="donut-legend__item">
          <span
            className="donut-legend__dot"
            style={{ background: getColor(entry.status, i) }}
          />
          <span className="donut-legend__label">{entry.label}</span>
          <span className="donut-legend__count">{entry.count}</span>
        </li>
      ))}
    </ul>
  );
}

export default function StatusDistributionChart({ data = [] }) {
  const nonZero = data.filter((d) => d.count > 0);
  const total   = nonZero.reduce((s, d) => s + d.count, 0);

  if (!total) {
    return (
      <div className="chart-card__body chart-card__body--empty">
        No applications yet
      </div>
    );
  }

  return (
    <div className="status-dist-chart">
      <ResponsiveContainer width="100%" height={160}>
        <PieChart>
          <Pie
            data={nonZero}
            dataKey="count"
            nameKey="label"
            cx="50%"
            cy="50%"
            innerRadius={48}
            outerRadius={72}
            paddingAngle={2}
            strokeWidth={0}
          >
            {nonZero.map((entry, i) => (
              <Cell key={entry.status} fill={getColor(entry.status, i)} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
        </PieChart>
      </ResponsiveContainer>
      <CustomLegend data={nonZero} />
    </div>
  );
}
