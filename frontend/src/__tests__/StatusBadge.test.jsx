/**
 * Unit tests for StatusBadge.
 *
 * Covers all status enum values, unknown status fallback, and the
 * processing spinner that renders only for status="processing".
 */

import { vi, describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusBadge from '../components/StatusBadge.jsx';

describe('StatusBadge', () => {
  test.each([
    ['pending',      'Pending'],
    ['processing',   'Processing…'],
    ['gate_failed',  'Gate Failed'],
    ['gate_unknown', 'Gate Unknown'],
    ['gate_passed',  'Gate Passed'],
    ['scored',       'Scored'],
    ['under_review', 'Under Review'],
    ['approved',     'Approved'],
    ['rejected',     'Rejected'],
  ])('status="%s" renders label "%s"', (status, label) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByTestId('status-badge')).toHaveTextContent(label);
  });

  test('unknown status falls back to the raw value', () => {
    render(<StatusBadge status="some_new_state" />);
    expect(screen.getByTestId('status-badge')).toHaveTextContent('some_new_state');
  });

  test('processing status renders a spinner element', () => {
    render(<StatusBadge status="processing" />);
    expect(document.querySelector('.status-badge__spinner')).toBeInTheDocument();
  });

  test('non-processing status does not render a spinner', () => {
    render(<StatusBadge status="scored" />);
    expect(document.querySelector('.status-badge__spinner')).not.toBeInTheDocument();
  });

  test('badge has the status-specific CSS modifier class', () => {
    render(<StatusBadge status="approved" />);
    expect(screen.getByTestId('status-badge')).toHaveClass('status-badge--approved');
  });
});
