/**
 * Unit tests for the Candidate resume ingestion modal.
 *
 * BDD coverage:
 *   Given the modal is open → name/email/file fields are visible and empty
 *   When user submits empty form → inline validation errors shown
 *   When user selects a PDF / .docx / .doc file → accepted client-side
 *   When user selects an unsupported file type → inline error, no API call
 *   When user selects an oversized file → inline error, no API call
 *   When user submits a valid PDF or Word file → API called, onSuccess fires
 *   When API returns 400 with field errors (e.g. conversion failure) →
 *     inline field errors rendered
 *   When API returns 409 (duplicate email) → inline email error rendered
 *   When API returns a generic error → error banner rendered
 *
 * Tools: Vitest · @testing-library/react · vi.mock
 */

import { vi, describe, test, beforeEach, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CandidateIngestionModal from '../components/CandidateIngestionModal.jsx';
import * as client from '../api/client.js';

vi.mock('../api/client.js', () => ({
  createCandidate: vi.fn(),
}));

// ── Fixtures ──────────────────────────────────────────────────────────────

const VALID_CANDIDATE_RESPONSE = {
  id:         'candidate-uuid-001',
  name:       'Alice Chen',
  email:      'alice@example.com',
  created_at: '2026-06-16T00:00:00Z',
};

function apiError(body, message = 'HTTP error', status) {
  const err = new Error(message);
  err.body = body;
  if (status) err.status = status;
  return err;
}

function makeFile(name, { type = 'application/pdf', size = 1024 } = {}) {
  const file = new File([new Uint8Array(size)], name, { type });
  // jsdom's File doesn't always honor the byte-array length in `size`;
  // pin it explicitly so size-limit tests are deterministic.
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

function renderModal(props = {}) {
  const defaults = {
    open:      true,
    onClose:   vi.fn(),
    onSuccess: vi.fn(),
  };
  return render(<CandidateIngestionModal {...defaults} {...props} />);
}

function fillNameAndEmail(name = 'Alice Chen', email = 'alice@example.com') {
  fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: name } });
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: email } });
}

function selectFile(file) {
  const input = document.getElementById('cand-pdf');
  fireEvent.change(input, { target: { files: [file] } });
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: /upload resume/i }));
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe('CandidateIngestionModal', () => {

  beforeEach(() => {
    client.createCandidate.mockReset();
  });

  // ── Rendering ───────────────────────────────────────────────────────────

  test('renders name, email, and file fields when open', () => {
    renderModal();
    expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/resume \(pdf or word\)/i)).toBeInTheDocument();
  });

  test('modal is not rendered when open=false', () => {
    renderModal({ open: false });
    expect(screen.queryByLabelText(/full name/i)).not.toBeInTheDocument();
  });

  test('fields are empty on open', () => {
    renderModal();
    expect(screen.getByLabelText(/full name/i)).toHaveValue('');
    expect(screen.getByLabelText(/email address/i)).toHaveValue('');
  });

  test('file input accepts PDF and Word extensions', () => {
    renderModal();
    const input = document.getElementById('cand-pdf');
    expect(input.accept).toContain('.pdf');
    expect(input.accept).toContain('.doc');
    expect(input.accept).toContain('.docx');
  });

  test('drop-zone label mentions PDF or Word document', () => {
    renderModal();
    expect(screen.getByText(/choose or drag a pdf or word document/i)).toBeInTheDocument();
  });

  // ── Validation: required fields ────────────────────────────────────────

  test('inline errors shown when submitted empty', async () => {
    renderModal();
    submit();
    await waitFor(() => {
      expect(screen.getByText(/full name is required/i)).toBeInTheDocument();
      expect(screen.getByText(/email address is required/i)).toBeInTheDocument();
      expect(screen.getByText(/please select a resume file/i)).toBeInTheDocument();
    });
    expect(client.createCandidate).not.toHaveBeenCalled();
  });

  test('inline error shown for malformed email', async () => {
    renderModal();
    fillNameAndEmail('Alice Chen', 'not-an-email');
    selectFile(makeFile('resume.pdf'));
    submit();
    await waitFor(() =>
      expect(screen.getByText(/enter a valid email address/i)).toBeInTheDocument()
    );
    expect(client.createCandidate).not.toHaveBeenCalled();
  });

  // ── Validation: file type/size ─────────────────────────────────────────

  test('rejects an unsupported file type client-side', async () => {
    renderModal();
    fillNameAndEmail();
    selectFile(makeFile('resume.txt', { type: 'text/plain' }));
    submit();
    await waitFor(() =>
      expect(screen.getByText(/only pdf or word \(\.doc, \.docx\) files are accepted/i))
        .toBeInTheDocument()
    );
    expect(client.createCandidate).not.toHaveBeenCalled();
  });

  test('rejects an oversized file client-side', async () => {
    renderModal();
    fillNameAndEmail();
    selectFile(makeFile('resume.pdf', { size: 11 * 1024 * 1024 }));
    submit();
    await waitFor(() =>
      expect(screen.getByText(/file must be smaller than 10 mb/i)).toBeInTheDocument()
    );
    expect(client.createCandidate).not.toHaveBeenCalled();
  });

  test.each([
    ['resume.pdf', 'application/pdf'],
    ['resume.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
    ['resume.doc', 'application/msword'],
  ])('accepts %s as a valid resume file', async (filename, type) => {
    client.createCandidate.mockResolvedValue(VALID_CANDIDATE_RESPONSE);
    renderModal();
    fillNameAndEmail();
    selectFile(makeFile(filename, { type }));
    submit();
    await waitFor(() => expect(client.createCandidate).toHaveBeenCalledTimes(1));
  });

  test('accepts a .docx file by extension even with a generic content type', async () => {
    client.createCandidate.mockResolvedValue(VALID_CANDIDATE_RESPONSE);
    renderModal();
    fillNameAndEmail();
    selectFile(makeFile('resume.docx', { type: '' }));
    submit();
    await waitFor(() => expect(client.createCandidate).toHaveBeenCalledTimes(1));
  });

  // ── Submission payload ──────────────────────────────────────────────────

  test('createCandidate called with trimmed name/email and selected file', async () => {
    client.createCandidate.mockResolvedValue(VALID_CANDIDATE_RESPONSE);
    renderModal();
    fillNameAndEmail('  Alice Chen  ', '  alice@example.com  ');
    const file = makeFile('resume.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });
    selectFile(file);
    submit();
    await waitFor(() =>
      expect(client.createCandidate).toHaveBeenCalledWith({
        name:       'Alice Chen',
        email:      'alice@example.com',
        resume_pdf: file,
      })
    );
  });

  // ── Loading state ────────────────────────────────────────────────────────

  test('submit button shows loading label during submission', async () => {
    client.createCandidate.mockReturnValue(new Promise(() => {}));
    renderModal();
    fillNameAndEmail();
    selectFile(makeFile('resume.pdf'));
    submit();
    expect(screen.getByRole('button', { name: /uploading/i })).toBeInTheDocument();
  });

  test('inputs disabled during submission', async () => {
    client.createCandidate.mockReturnValue(new Promise(() => {}));
    renderModal();
    fillNameAndEmail();
    selectFile(makeFile('resume.pdf'));
    submit();
    expect(screen.getByLabelText(/full name/i)).toBeDisabled();
  });

  // ── Success path ─────────────────────────────────────────────────────────

  test('onSuccess called with candidate data on 201', async () => {
    const onSuccess = vi.fn();
    client.createCandidate.mockResolvedValue(VALID_CANDIDATE_RESPONSE);
    renderModal({ onSuccess });
    fillNameAndEmail();
    selectFile(makeFile('resume.pdf'));
    submit();
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(VALID_CANDIDATE_RESPONSE));
  });

  test('onClose called after successful submission', async () => {
    const onClose = vi.fn();
    client.createCandidate.mockResolvedValue(VALID_CANDIDATE_RESPONSE);
    renderModal({ onClose });
    fillNameAndEmail();
    selectFile(makeFile('resume.pdf'));
    submit();
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  // ── Server-side errors ──────────────────────────────────────────────────

  test('inline error shown when API rejects a Word file it could not convert', async () => {
    client.createCandidate.mockRejectedValue(
      apiError({ resume_pdf: ['Conversion timed out after 30s.'] })
    );
    renderModal();
    fillNameAndEmail();
    selectFile(makeFile('resume.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    }));
    submit();
    await waitFor(() =>
      expect(screen.getByText(/conversion timed out after 30s/i)).toBeInTheDocument()
    );
  });

  test('409 duplicate email response shows inline email error', async () => {
    client.createCandidate.mockRejectedValue(
      apiError({ email: ['A candidate with this email already exists.'] }, 'Conflict', 409)
    );
    renderModal();
    fillNameAndEmail();
    selectFile(makeFile('resume.pdf'));
    submit();
    await waitFor(() =>
      expect(screen.getByText(/already exists/i)).toBeInTheDocument()
    );
  });

  test('error banner shown when API returns a generic error', async () => {
    client.createCandidate.mockRejectedValue(new Error('Failed to upload resume. Please try again.'));
    renderModal();
    fillNameAndEmail();
    selectFile(makeFile('resume.pdf'));
    submit();
    await waitFor(() =>
      expect(screen.getByText(/failed to upload resume/i)).toBeInTheDocument()
    );
  });

  test('fields re-enabled after error — user can edit and retry', async () => {
    client.createCandidate.mockRejectedValue(new Error('Server error'));
    renderModal();
    fillNameAndEmail();
    selectFile(makeFile('resume.pdf'));
    submit();
    await waitFor(() => expect(screen.getByLabelText(/full name/i)).not.toBeDisabled());
  });
});
