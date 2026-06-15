/**
 * InsightPanel — contextual callouts derived from pipeline score data.
 *
 * Renders zero or more insight cards explaining unusual conditions:
 *   - Gate outcome UNKNOWN or FAIL
 *   - Missing semantic or rubric scores (pipeline short-circuited)
 *   - Low semantic match or rubric score
 *   - Low confidence
 *
 * Props:
 *   score  {object}  Full score payload from GET /api/applications/{id}/score/
 */

function pct(v) {
  return v == null ? '—' : `${Math.round(v * 100)}%`;
}

function getInsights(score) {
  const insights = [];

  if (score.gate_outcome === 'unknown') {
    insights.push({
      type: 'warning',
      icon: '?',
      title: 'Gate Outcome: Unknown',
      body: 'The automated screening could not determine whether this candidate meets the minimum requirements. Review each hard-gate criterion manually before making a decision.',
    });
  }

  if (score.gate_outcome === 'fail') {
    insights.push({
      type: 'danger',
      icon: '✕',
      title: 'Hard Gate Failed',
      body: 'This candidate did not meet one or more mandatory requirements. Only use Override if you have strong evidence to justify bypassing the gate — doing so creates an audit record.',
    });
  }

  if (score.semantic_score == null) {
    insights.push({
      type: 'info',
      icon: '~',
      title: 'No Semantic Match Score',
      body: 'Semantic similarity was not computed — the pipeline likely short-circuited after the hard gate. Re-run the pipeline to see a full similarity score.',
    });
  } else if (score.semantic_score < 0.3) {
    insights.push({
      type: 'warning',
      icon: '↓',
      title: `Low Semantic Match (${pct(score.semantic_score)})`,
      body: "The candidate's resume has low vocabulary and experience overlap with this job's requirements. Check whether key skills and role language appear in their resume.",
    });
  }

  if (score.rubric_score == null) {
    insights.push({
      type: 'info',
      icon: '~',
      title: 'No LLM Rubric Score',
      body: 'The LLM rubric evaluation was skipped — this happens when the pipeline stops at the hard gate. Run the full pipeline to generate a rubric assessment.',
    });
  } else if (score.rubric_score < 0.4) {
    insights.push({
      type: 'warning',
      icon: '↓',
      title: `Low Rubric Score (${pct(score.rubric_score)})`,
      body: 'The AI evaluator found limited evidence across the 5 competency areas. See the Rubric Breakdown below to identify which dimensions are weak.',
    });
  }

  if (score.confidence != null && score.confidence < 0.5) {
    insights.push({
      type: 'info',
      icon: '≈',
      title: `Low Confidence (${pct(score.confidence)})`,
      body: 'The AI is uncertain about this evaluation — often caused by sparse resume content or ambiguous role requirements. Extra manual review is recommended.',
    });
  }

  return insights;
}

export default function InsightPanel({ score }) {
  const insights = getInsights(score);
  if (insights.length === 0) return null;

  return (
    <div className="insight-panel" data-testid="insight-panel">
      {insights.map((insight, i) => (
        <div
          key={i}
          className={`insight-panel__item insight-panel__item--${insight.type}`}
          role="note"
        >
          <span className="insight-panel__icon" aria-hidden="true">
            {insight.icon}
          </span>
          <div className="insight-panel__body">
            <strong className="insight-panel__title">{insight.title}</strong>
            <p className="insight-panel__text">{insight.body}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
