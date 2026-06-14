// Custom Cypress commands for the review UI.

/**
 * Intercept the score API and stub a scored application.
 *
 * Usage:
 *   cy.stubScore('app-001', { final_score: 0.82, ... });
 */
Cypress.Commands.add('stubScore', (appId, overrides = {}) => {
  const defaultScore = {
    application_id: appId,
    final_score: 0.82,
    confidence: 1.0,
    gate_passed: true,
    gate_outcome: 'pass',
    semantic_score: 0.79,
    rubric_score: 0.84,
    rubric_breakdown: {
      core_skills: 4.5,
      relevant_experience: 4.2,
      scope_impact: 4.0,
      domain_alignment: 3.8,
      education_certs: 3.5,
    },
  };
  cy.intercept('GET', `/api/applications/${appId}/score/`, {
    statusCode: 200,
    body: { ...defaultScore, ...overrides },
  }).as('getScore');
});

/**
 * Intercept the reviews POST endpoint.
 *
 * Usage:
 *   cy.stubReviewPost('app-001');       // → 201
 *   cy.stubReviewPost('app-001', 500);  // → 500
 */
Cypress.Commands.add('stubReviewPost', (appId, statusCode = 201) => {
  cy.intercept('POST', `/api/applications/${appId}/reviews/`, (req) => {
    if (statusCode >= 400) {
      req.reply({ statusCode, body: { detail: 'Server error' } });
    } else {
      req.reply({
        statusCode: 201,
        body: {
          id: 'rev-001',
          reviewer_email: req.body.reviewer_email,
          decision: req.body.decision,
          override_reason: req.body.override_reason ?? '',
          reviewed_at: new Date().toISOString(),
        },
      });
    }
  }).as('postReview');
});
