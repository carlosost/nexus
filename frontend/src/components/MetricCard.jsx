/**
 * MetricCard — single KPI summary tile used in the Dashboard stats grid.
 *
 * Props:
 *   label    string   — card header label (e.g. "Total Applications")
 *   value    string|number  — primary display value
 *   sub      string   — optional sub-label beneath the value
 *   icon     string   — emoji or single character icon
 *   color    string   — CSS custom property suffix: 'brand' | 'success' | 'warning' | 'danger' | 'info' | 'teal' | 'purple'
 */

export default function MetricCard({ label, value, sub, icon, color = 'brand' }) {
  return (
    <div className="metric-card" data-color={color} style={{ '--metric-color': `var(--color-${color})` }}>
      <div className="metric-card__header">
        {icon && <span className="metric-card__icon" aria-hidden="true">{icon}</span>}
        <span className="metric-card__label">{label}</span>
      </div>
      <div className="metric-card__value">{value ?? '—'}</div>
      {sub && <div className="metric-card__sub">{sub}</div>}
    </div>
  );
}
