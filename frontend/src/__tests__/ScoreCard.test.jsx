/**
 * Unit tests for ScoreCard component.
 * Inner TDD loop — must pass after implementation.
 */
import { render, screen } from '@testing-library/react';
import ScoreCard from '../components/ScoreCard.jsx';

const BASE_SCORE = {
  final_score: 0.82,
  confidence: 1.0,
  gate_passed: true,
  gate_outcome: 'pass',
  semantic_score: 0.79,
  rubric_score: 0.84,
};

describe('ScoreCard', () => {
  test('displays final score as percentage', () => {
    render(<ScoreCard score={BASE_SCORE} />);
    expect(screen.getByTestId('final-score')).toHaveTextContent('82%');
  });

  test('rounds final score correctly', () => {
    render(<ScoreCard score={{ ...BASE_SCORE, final_score: 0.825 }} />);
    // Math.round(82.5) = 83
    expect(screen.getByTestId('final-score')).toHaveTextContent('83%');
  });

  test('shows PASS gate badge when gate_outcome is pass', () => {
    render(<ScoreCard score={BASE_SCORE} />);
    expect(screen.getByTestId('gate-badge')).toHaveTextContent('PASS');
  });

  test('shows FAIL gate badge when gate_outcome is fail', () => {
    render(<ScoreCard score={{ ...BASE_SCORE, gate_outcome: 'fail', final_score: 0.0 }} />);
    expect(screen.getByTestId('gate-badge')).toHaveTextContent('FAIL');
  });

  test('shows UNKNOWN gate badge when gate_outcome is unknown', () => {
    render(<ScoreCard score={{ ...BASE_SCORE, gate_outcome: 'unknown' }} />);
    expect(screen.getByTestId('gate-badge')).toHaveTextContent('UNKNOWN');
  });

  test('displays confidence as percentage', () => {
    render(<ScoreCard score={BASE_SCORE} />);
    expect(screen.getByTestId('confidence')).toHaveTextContent('100%');
  });

  test('displays confidence as — when null', () => {
    render(<ScoreCard score={{ ...BASE_SCORE, confidence: null }} />);
    expect(screen.getByTestId('confidence')).toHaveTextContent('—');
  });

  test('displays semantic score as percentage', () => {
    render(<ScoreCard score={BASE_SCORE} />);
    expect(screen.getByTestId('semantic-score')).toHaveTextContent('79%');
  });

  test('displays rubric score as percentage', () => {
    render(<ScoreCard score={BASE_SCORE} />);
    expect(screen.getByTestId('rubric-score')).toHaveTextContent('84%');
  });

  test('shows 0% when final_score is 0 (gate fail)', () => {
    render(<ScoreCard score={{ ...BASE_SCORE, final_score: 0.0, gate_outcome: 'fail' }} />);
    expect(screen.getByTestId('final-score')).toHaveTextContent('0%');
  });

  test('has score-card aria-label', () => {
    render(<ScoreCard score={BASE_SCORE} />);
    expect(screen.getByRole('region', { name: /score card/i })).toBeInTheDocument();
  });
});
