/**
 * JobFunnelChart — horizontal stacked bar showing job execution buckets
 * for the last 24 hours (Completed / Running / Failed / Retrying via Fallback).
 *
 * Uses Recharts BarChart with layout="vertical".
 *
 * Props:
 *   data  Array<{ status: string, label: string, count: number }>
 */

import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell, LabelList,
} from 'recharts';

const FUNNEL_COLORS = {
  completed: '#22c55e',
  running:   '#38bdf8',
  failed:    '#ef4444',
  fallback:  '#f59e0b',
};

const tooltipStyle = {
  background:   '#1a1d27',
  border:       '1px solid #2e3352',
  borderRadius: '6px',
  color:        '#c8cee8',
  fontSize:     '12px',
};

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={tooltipStyle}>
      <div style={{ padding: '6px 10px' }}>
        {label}: <strong style={{ color: '#fff' }}>{payload[0].value}</strong>
      </div>
    </div>
  );
}

export default function JobFunnelChart({ data = [] }) {
  const total = data.reduce((s, d) => s + d.count, 0);

  if (!total) {
    return (
      <div className="chart-card__body chart-card__body--empty">
        No activity in the last 24 h
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={168}>
      <BarChart
        layout="vertical"
        data={data}
        margin={{ top: 4, right: 40, bottom: 4, left: 8 }}
        barCategoryGap="28%"
      >
        <XAxis
          type="number"
          tick={{ fill: '#555e85', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <YAxis
          type="category"
          dataKey="label"
          width={140}
          tick={{ fill: '#8b92b8', fontSize: 12 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={18}>
          {data.map((entry) => (
            <Cell
              key={entry.status}
              fill={FUNNEL_COLORS[entry.status] ?? '#5c6ef8'}
            />
          ))}
          <LabelList
            dataKey="count"
            position="right"
            style={{ fill: '#8b92b8', fontSize: 11 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
