/**
 * LLMResilienceChart — stacked area chart showing primary vs fallback LLM
 * usage over the last 7 days.
 *
 * Uses Recharts AreaChart. The primary backend usage fills bottom; fallback
 * sits on top so the operator can see at a glance when fallback spikes.
 *
 * Props:
 *   data  Array<{ date: string, primary: number, fallback: number }>
 */

import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  CartesianGrid, ResponsiveContainer, Legend,
} from 'recharts';

const tooltipStyle = {
  background:   '#1a1d27',
  border:       '1px solid #2e3352',
  borderRadius: '6px',
  color:        '#c8cee8',
  fontSize:     '12px',
};

function fmtDate(iso) {
  // "2024-01-08" → "Jan 8"
  const [, m, d] = iso.split('-');
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${months[parseInt(m, 10) - 1]} ${parseInt(d, 10)}`;
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={tooltipStyle}>
      <div style={{ padding: '6px 10px', borderBottom: '1px solid #2e3352', marginBottom: 4 }}>
        <strong style={{ color: '#fff' }}>{fmtDate(label)}</strong>
      </div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ padding: '2px 10px', display: 'flex', gap: 8 }}>
          <span style={{ color: p.fill }}>●</span>
          <span style={{ minWidth: 60 }}>{p.name}</span>
          <strong style={{ color: '#fff' }}>{p.value}</strong>
        </div>
      ))}
    </div>
  );
}

export default function LLMResilienceChart({ data = [] }) {
  const hasData = data.some((d) => d.primary > 0 || d.fallback > 0);

  if (!hasData) {
    return (
      <div className="chart-card__body chart-card__body--empty">
        No LLM calls recorded in the last 7 days
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={168}>
      <AreaChart data={data} margin={{ top: 4, right: 16, bottom: 0, left: -8 }}>
        <defs>
          <linearGradient id="gradPrimary" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#5c6ef8" stopOpacity={0.35} />
            <stop offset="95%" stopColor="#5c6ef8" stopOpacity={0.04} />
          </linearGradient>
          <linearGradient id="gradFallback" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.45} />
            <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid
          strokeDasharray="3 3"
          stroke="#2e3352"
          vertical={false}
        />
        <XAxis
          dataKey="date"
          tickFormatter={fmtDate}
          tick={{ fill: '#555e85', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: '#555e85', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <Tooltip content={<CustomTooltip />} />
        <Area
          type="monotone"
          dataKey="primary"
          name="Primary"
          stackId="1"
          stroke="#5c6ef8"
          strokeWidth={2}
          fill="url(#gradPrimary)"
        />
        <Area
          type="monotone"
          dataKey="fallback"
          name="Fallback"
          stackId="1"
          stroke="#f59e0b"
          strokeWidth={2}
          fill="url(#gradFallback)"
        />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 11, color: '#8b92b8', paddingTop: 4 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
