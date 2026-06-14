/**
 * Unit tests for RubricBreakdown component.
 */
import { render, screen } from '@testing-library/react';
import RubricBreakdown from '../components/RubricBreakdown.jsx';

const BREAKDOWN = {
  core_skills: 4.5,
  relevant_experience: 4.2,
  scope_impact: 4.0,
  domain_alignment: 3.8,
  education_certs: 3.5,
};

describe('RubricBreakdown', () => {
  test('renders all five criteria', () => {
    render(<RubricBreakdown breakdown={BREAKDOWN} />);
    expect(screen.getByTestId('criterion-score-core_skills')).toBeInTheDocument();
    expect(screen.getByTestId('criterion-score-relevant_experience')).toBeInTheDocument();
    expect(screen.getByTestId('criterion-score-scope_impact')).toBeInTheDocument();
    expect(screen.getByTestId('criterion-score-domain_alignment')).toBeInTheDocument();
    expect(screen.getByTestId('criterion-score-education_certs')).toBeInTheDocument();
  });

  test('displays correct raw score for core_skills', () => {
    render(<RubricBreakdown breakdown={BREAKDOWN} />);
    expect(screen.getByTestId('criterion-score-core_skills')).toHaveTextContent('4.5');
  });

  test('displays correct raw score for education_certs', () => {
    render(<RubricBreakdown breakdown={BREAKDOWN} />);
    expect(screen.getByTestId('criterion-score-education_certs')).toHaveTextContent('3.5');
  });

  test('bar width for score 5 is 100%', () => {
    render(<RubricBreakdown breakdown={{ core_skills: 5.0 }} />);
    const bar = screen.getByTestId('criterion-bar-core_skills');
    expect(bar.style.width).toBe('100%');
  });

  test('bar width for score 2.5 is 50%', () => {
    render(<RubricBreakdown breakdown={{ core_skills: 2.5 }} />);
    const bar = screen.getByTestId('criterion-bar-core_skills');
    expect(bar.style.width).toBe('50%');
  });

  test('bar width for score 1 is 20%', () => {
    render(<RubricBreakdown breakdown={{ core_skills: 1.0 }} />);
    const bar = screen.getByTestId('criterion-bar-core_skills');
    expect(bar.style.width).toBe('20%');
  });

  test('shows empty state when breakdown is empty', () => {
    render(<RubricBreakdown breakdown={{}} />);
    expect(screen.getByText(/no rubric data/i)).toBeInTheDocument();
  });

  test('shows empty state when breakdown is undefined', () => {
    render(<RubricBreakdown />);
    expect(screen.getByText(/no rubric data/i)).toBeInTheDocument();
  });

  test('has rubric breakdown aria-label', () => {
    render(<RubricBreakdown breakdown={BREAKDOWN} />);
    expect(screen.getByRole('region', { name: /rubric breakdown/i })).toBeInTheDocument();
  });
});
