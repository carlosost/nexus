/**
 * ScoreCard — Stage 4 pipeline output display.
 *
 * Props:
 *   score        {object} — full score data from GET /api/applications/{id}/score/
 *   score.final_score    {number}  0–1
 *   score.confidence     {number}  0–1 | null
 *   score.gate_passed    {boolean}
 *   score.gate_outcome   {string}  "pass" | "fail" | "unknown"
 *   score.semantic_score {number}  0–1 | null
 *   score.rubric_score   {number}  0–1 | null
 */

const RADIUS = 44;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function ScoreRing({ value }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(1, value));
  const filled = pct * CIRCUMFERENCE;
  const color =
    pct >= 0.7 ? 'var(--color-success)' :
    pct >= 0.4 ? 'var(--color-warning)' :
                 'var(--color-danger)';

  return (
    <svg className="score-ring" viewBox="0 0 100 100" aria-hidden="true">
      <circle
        className="score-ring__track"
        cx="50" cy="50" r={RADIUS}
        fill="none"
        stroke="var(--color-border)"
        strokeWidth="8"
      />
      <circle
        className="score-ring__fill"
        cx="50" cy="50" r={RADIUS}
        fill="none"
        stroke={color}
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${CIRCUMFERENCE}`}
        strokeDashoffset="0"
        transform="rotate(-90 50 50)"
        style={{ transition: 'stroke-dasharray 0.5s ease' }}
      />
    </svg>
  );
}

export default function ScoreCard({ score }) {
  const pct = (v) =>
    v == null ? '—' : `${Math.round(v * 100)}%`;

  const gateClass =
    score.gate_outcome === 'pass'    ? 'badge badge--pass' :
    score.gate_outcome === 'fail'    ? 'badge badge--fail' :
                                       'badge badge--unknown';

  return (
    <section className="score-card" aria-label="Score card">
      <div className="score-card__hero">
        <div className="score-card__ring-wrap">
          <ScoreRing value={score.final_score} />
          <span className="score-card__final" data-testid="final-score">
            {pct(score.final_score)}
          </span>
        </div>

        <div className="score-card__meta">
          <span className={gateClass} data-testid="gate-badge">
            {score.gate_outcome?.toUpperCase()}
          </span>
          <p className="score-card__meta-label">Final Score</p>
        </div>
      </div>

      <dl className="score-card__details">
        <div className="score-card__detail">
          <dt>Confidence</dt>
          <dd data-testid="confidence">{pct(score.confidence)}</dd>
        </div>
        <div className="score-card__detail">
          <dt>Semantic match</dt>
          <dd data-testid="semantic-score">{pct(score.semantic_score)}</dd>
        </div>
        <div className="score-card__detail">
          <dt>Rubric score</dt>
          <dd data-testid="rubric-score">{pct(score.rubric_score)}</dd>
        </div>
      </dl>
    </section>
  );
}
