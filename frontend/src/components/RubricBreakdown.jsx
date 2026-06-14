/**
 * RubricBreakdown — per-criterion scores from Stage 3.
 *
 * Props:
 *   breakdown  {object}  rubric_breakdown from score API.
 *              Keys are criterion names; values are raw scores 1–5.
 *              Example: { core_skills: 4.5, relevant_experience: 4.2, ... }
 */

const CRITERION_LABELS = {
  core_skills: 'Core Skills',
  relevant_experience: 'Relevant Experience',
  scope_impact: 'Scope & Impact',
  domain_alignment: 'Domain Alignment',
  education_certs: 'Education & Certs',
};

const MAX_SCORE = 5;

export default function RubricBreakdown({ breakdown }) {
  if (!breakdown || Object.keys(breakdown).length === 0) {
    return (
      <section className="rubric-breakdown" aria-label="Rubric breakdown">
        <p className="rubric-breakdown__empty">No rubric data available.</p>
      </section>
    );
  }

  return (
    <section className="rubric-breakdown" aria-label="Rubric breakdown">
      <h2 className="rubric-breakdown__title">Rubric Breakdown</h2>
      <ul className="rubric-breakdown__list">
        {Object.entries(breakdown).map(([criterion, rawScore]) => {
          const pct = Math.round((rawScore / MAX_SCORE) * 100);
          const label = CRITERION_LABELS[criterion] ?? criterion;
          return (
            <li key={criterion} className="rubric-breakdown__item">
              <span
                className="rubric-breakdown__label"
                data-testid={`criterion-label-${criterion}`}
              >
                {label}
              </span>
              <div className="rubric-breakdown__bar-track" aria-hidden="true">
                <div
                  className="rubric-breakdown__bar-fill"
                  data-testid={`criterion-bar-${criterion}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span
                className="rubric-breakdown__score"
                data-testid={`criterion-score-${criterion}`}
              >
                {rawScore.toFixed(1)}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
