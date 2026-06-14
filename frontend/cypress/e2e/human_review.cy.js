/**
 * Cypress e2e tests for the Human-in-the-Loop Review UI.
 *
 * These are the outer BDD loop implementation for features/human_review_ui.feature.
 * All API calls are intercepted with cy.intercept() — no real backend required.
 *
 * Run: npx cypress run   (or cy:run npm script)
 */

const APP_ID = 'app-001';
const REVIEW_URL = `/review/${APP_ID}`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function visitAndWaitForScore(appId = APP_ID) {
  cy.stubScore(appId);
  cy.visit(`/review/${appId}`);
  cy.wait('@getScore');
}

// ---------------------------------------------------------------------------
// Score Card display
// ---------------------------------------------------------------------------

describe('Score Card', () => {
  beforeEach(() => visitAndWaitForScore());

  it('displays final score as a percentage', () => {
    cy.get('[data-testid="final-score"]').should('contain', '82%');
  });

  it('shows PASS gate badge', () => {
    cy.get('[data-testid="gate-badge"]').should('contain', 'PASS');
  });

  it('shows confidence as 100%', () => {
    cy.get('[data-testid="confidence"]').should('contain', '100%');
  });

  it('shows semantic score as 79%', () => {
    cy.get('[data-testid="semantic-score"]').should('contain', '79%');
  });

  it('shows rubric score as 84%', () => {
    cy.get('[data-testid="rubric-score"]').should('contain', '84%');
  });

  it('shows FAIL badge and 0% when gate failed', () => {
    cy.stubScore(APP_ID, { gate_outcome: 'fail', gate_passed: false, final_score: 0.0 });
    cy.visit(REVIEW_URL);
    cy.wait('@getScore');
    cy.get('[data-testid="gate-badge"]').should('contain', 'FAIL');
    cy.get('[data-testid="final-score"]').should('contain', '0%');
  });
});

// ---------------------------------------------------------------------------
// Rubric Breakdown
// ---------------------------------------------------------------------------

describe('Rubric Breakdown', () => {
  beforeEach(() => visitAndWaitForScore());

  it('renders all five criteria', () => {
    cy.get('[data-testid="criterion-score-core_skills"]').should('exist');
    cy.get('[data-testid="criterion-score-relevant_experience"]').should('exist');
    cy.get('[data-testid="criterion-score-scope_impact"]').should('exist');
    cy.get('[data-testid="criterion-score-domain_alignment"]').should('exist');
    cy.get('[data-testid="criterion-score-education_certs"]').should('exist');
  });

  it('shows core_skills score as 4.5', () => {
    cy.get('[data-testid="criterion-score-core_skills"]').should('contain', '4.5');
  });

  it('shows education_certs score as 3.5', () => {
    cy.get('[data-testid="criterion-score-education_certs"]').should('contain', '3.5');
  });

  it('core_skills bar width is 90% (4.5/5)', () => {
    cy.get('[data-testid="criterion-bar-core_skills"]')
      .should('have.attr', 'style')
      .and('include', '90%');
  });
});

// ---------------------------------------------------------------------------
// Override Panel — submit guard
// ---------------------------------------------------------------------------

describe('Override Panel — submit guard', () => {
  beforeEach(() => visitAndWaitForScore());

  it('approve — reason textarea not visible, submit enabled', () => {
    cy.get('[data-testid="decision-select"]').select('approve');
    cy.get('[data-testid="override-reason"]').should('not.exist');
    cy.get('[data-testid="submit-button"]').should('not.be.disabled');
  });

  it('reject — reason textarea not visible, submit enabled', () => {
    cy.get('[data-testid="decision-select"]').select('reject');
    cy.get('[data-testid="override-reason"]').should('not.exist');
    cy.get('[data-testid="submit-button"]').should('not.be.disabled');
  });

  it('override_pass — reason textarea visible, submit initially disabled', () => {
    cy.get('[data-testid="decision-select"]').select('override_pass');
    cy.get('[data-testid="override-reason"]').should('be.visible');
    cy.get('[data-testid="submit-button"]').should('be.disabled');
  });

  it('override_fail — reason textarea visible, submit initially disabled', () => {
    cy.get('[data-testid="decision-select"]').select('override_fail');
    cy.get('[data-testid="override-reason"]').should('be.visible');
    cy.get('[data-testid="submit-button"]').should('be.disabled');
  });

  it('override_pass — submit enabled once reason filled', () => {
    cy.get('[data-testid="decision-select"]').select('override_pass');
    cy.get('[data-testid="override-reason"]').type('Strong portfolio despite missing cert');
    cy.get('[data-testid="submit-button"]').should('not.be.disabled');
  });

  it('override_pass — submit disabled again after clearing reason', () => {
    cy.get('[data-testid="decision-select"]').select('override_pass');
    cy.get('[data-testid="override-reason"]').type('Strong portfolio');
    cy.get('[data-testid="override-reason"]').clear();
    cy.get('[data-testid="submit-button"]').should('be.disabled');
  });
});

// ---------------------------------------------------------------------------
// Successful submission
// ---------------------------------------------------------------------------

describe('Submission — success', () => {
  beforeEach(() => {
    visitAndWaitForScore();
    cy.stubReviewPost(APP_ID);
  });

  it('approve — posts to API and shows confirmation', () => {
    cy.get('[data-testid="reviewer-email"]').type('alice@company.com');
    cy.get('[data-testid="decision-select"]').select('approve');
    cy.get('[data-testid="submit-button"]').click();

    cy.wait('@postReview').then((interception) => {
      expect(interception.request.body.decision).to.equal('approve');
      expect(interception.request.body.reviewer_email).to.equal('alice@company.com');
    });

    cy.get('[data-testid="success-message"]').should('be.visible');
    cy.get('[data-testid="review-form"]').should('not.exist');
  });

  it('override_pass — posts reason to API', () => {
    cy.get('[data-testid="reviewer-email"]').type('alice@company.com');
    cy.get('[data-testid="decision-select"]').select('override_pass');
    cy.get('[data-testid="override-reason"]').type('Strong portfolio despite missing cert');
    cy.get('[data-testid="submit-button"]').click();

    cy.wait('@postReview').then((interception) => {
      expect(interception.request.body.decision).to.equal('override_pass');
      expect(interception.request.body.override_reason).to.equal(
        'Strong portfolio despite missing cert'
      );
    });
  });
});

// ---------------------------------------------------------------------------
// Error states
// ---------------------------------------------------------------------------

describe('Error states', () => {
  it('shows "Application not found" on 404', () => {
    cy.intercept('GET', '/api/applications/app-999/score/', {
      statusCode: 404,
      body: { detail: 'Not found.' },
    }).as('notFound');
    cy.visit('/review/app-999');
    cy.wait('@notFound');
    cy.get('[data-testid="error-message"]').should('contain', 'Application not found');
  });

  it('shows "Submission failed" on 500 and keeps form visible', () => {
    visitAndWaitForScore();
    cy.stubReviewPost(APP_ID, 500);

    cy.get('[data-testid="reviewer-email"]').type('alice@company.com');
    cy.get('[data-testid="submit-button"]').click();
    cy.wait('@postReview');

    cy.get('[data-testid="submit-error-message"]').should('contain', 'Submission failed');
    cy.get('[data-testid="review-form"]').should('exist');
  });
});

// ---------------------------------------------------------------------------
// Audit Trail
// ---------------------------------------------------------------------------

describe('Audit Trail', () => {
  it('shows reviewer and decision after successful submission', () => {
    visitAndWaitForScore();
    cy.intercept('POST', `/api/applications/${APP_ID}/reviews/`, {
      statusCode: 201,
      body: {
        id: 'rev-001',
        reviewer_email: 'bob@company.com',
        decision: 'approve',
        override_reason: '',
        reviewed_at: '2026-06-10T14:00:00Z',
      },
    }).as('postReview');

    cy.get('[data-testid="reviewer-email"]').type('bob@company.com');
    cy.get('[data-testid="submit-button"]').click();
    cy.wait('@postReview');

    cy.get('[data-testid="success-message"]').should('exist');
    cy.get('[data-testid="reviewer-rev-001"]').should('contain', 'bob@company.com');
    cy.get('[data-testid="decision-rev-001"]').should('contain', 'Approve');
  });
});
