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
export default function ScoreCard({ score }) {
  const pct = (v) =>
    v == null ? '—' : `${Math.round(v * 100)}%`;

  const gateBadgeClass =
    score.gate_outcome === 'pass'
      ? 'badge badge-pass'
      : score.gate_outcome === 'fail'
      ? 'badge badge-fail'
      : 'badge badge-unknown';

  return (
    <section className="score-card" aria-label="Score card">
      <div className="score-card__hero">
        <span className="score-card__final" data-testid="final-score">
          {pct(score.final_score)}
        </span>
        <span className={gateBadgeClass} data-testid="gate-badge">
          {score.gate_outcome.toUpperCase()}
        </span>
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
