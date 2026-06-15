/**
 * ReviewApp — root component for the Human-in-the-Loop review page.
 *
 * Lifecycle:
 *   1. On mount, fetches GET /api/applications/{applicationId}/score/
 *   2. Renders ScoreCard + RubricBreakdown from the score data
 *   3. Renders OverridePanel — on successful submit, shows confirmation
 *   4. Renders AuditTrail (populated after submission)
 *
 * Props:
 *   applicationId  {string | null}  UUID from the URL. Null → error state.
 */
import { useState, useEffect } from 'react';
import ScoreCard from './ScoreCard.jsx';
import InsightPanel from './InsightPanel.jsx';
import RubricBreakdown from './RubricBreakdown.jsx';
import OverridePanel from './OverridePanel.jsx';
import AuditTrail from './AuditTrail.jsx';
import { fetchScore } from '../api/client.js';

export default function ReviewApp({ applicationId }) {
  const [scoreData, setScoreData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [reviews, setReviews] = useState([]);

  useEffect(() => {
    if (!applicationId) {
      setFetchError(new Error('No application ID provided'));
      setLoading(false);
      return;
    }
    setLoading(true);
    fetchScore(applicationId)
      .then((data) => {
        setScoreData(data);
        setLoading(false);
      })
      .catch((err) => {
        setFetchError(err);
        setLoading(false);
      });
  }, [applicationId]);

  function handleSubmitSuccess(result) {
    setSubmitSuccess(true);
    setSubmitError(null);
    if (result) {
      setReviews((prev) => [result, ...prev]);
    }
  }

  function handleSubmitError(err) {
    setSubmitError(err);
    setSubmitSuccess(false);
  }

  if (loading) {
    return (
      <div className="review-app review-app--loading" aria-busy="true">
        <p data-testid="loading-message">Loading…</p>
      </div>
    );
  }

  if (fetchError) {
    const is404 = fetchError.status === 404;
    return (
      <div className="review-app review-app--error">
        <p
          className="review-app__error"
          data-testid="error-message"
          role="alert"
        >
          {is404
            ? 'No score available yet. Run the pipeline first to generate a review.'
            : `Error: ${fetchError.message}`}
        </p>
      </div>
    );
  }

  return (
    <div className="review-app" data-testid="review-app">
      <header className="review-app__header">
        <h1 className="review-app__title">Application Review</h1>
        <code className="review-app__id" data-testid="application-id">
          {applicationId}
        </code>
      </header>

      <ScoreCard score={scoreData} />

      <InsightPanel score={scoreData} />

      <RubricBreakdown breakdown={scoreData.rubric_breakdown ?? {}} />

      {submitSuccess ? (
        <p
          className="review-app__success"
          data-testid="success-message"
          role="status"
        >
          Review submitted successfully.
        </p>
      ) : (
        <>
          {submitError && (
            <p
              className="review-app__error"
              data-testid="submit-error-message"
              role="alert"
            >
              Submission failed. Please try again.
            </p>
          )}
          <OverridePanel
            applicationId={applicationId}
            onSubmit={handleSubmitSuccess}
            onError={handleSubmitError}
          />
        </>
      )}

      <AuditTrail reviews={reviews} />
    </div>
  );
}
