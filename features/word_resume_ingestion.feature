# features/word_resume_ingestion.feature
#
# Outer-loop BDD specification — M8: Word (.doc / .docx) Resume Ingestion.
#
# Business rules encoded here:
#   1. POST /api/candidates/ accepts resume_pdf as PDF, .doc, or .docx.
#   2. A Word upload is converted to PDF server-side (LibreOffice headless)
#      BEFORE it reaches ResumeParser — every downstream stage is unaware
#      the original file wasn't a PDF.
#   3. A Word file LibreOffice cannot convert returns 400 with a field-level
#      error on resume_pdf — no Candidate row is created.
#   4. A conversion subprocess timeout is handled the same way: 400, no
#      orphan Candidate row, no exception escapes the view.
#   5. The existing PDF-only upload path is completely unaffected.
#   6. Disallowed file types (e.g. .txt) are still rejected with 400.
#   7. Oversized Word files (> 10 MB) are rejected before conversion is
#      ever attempted — no subprocess is spawned for an oversized file.

Feature: Word Document Resume Ingestion
  As a recruiting operator
  I want to upload Word resumes (.doc / .docx) in addition to PDFs
  So that candidates aren't excluded just because of their file format

  Background:
    Given the candidate ingestion endpoint is initialized
    And the database is empty of Candidate records

  # ───────────────────────────────────────────────────────────────────────────
  # Scenario Group 1 — Successful Word conversion
  # ───────────────────────────────────────────────────────────────────────────

  Scenario: A valid .docx resume is converted to PDF and the candidate is created
    Given a candidate upload named "resume.docx" with content type "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    And LibreOffice conversion of this file succeeds and produces a valid PDF
    When I POST the candidate "Alice Johnson" with email "alice.word@example.com" to "/api/candidates/"
    Then the response status is 201
    And a Candidate record exists with email "alice.word@example.com"
    And the Word-to-PDF converter was invoked exactly once

  Scenario: A valid legacy .doc resume is converted to PDF and the candidate is created
    Given a candidate upload named "resume.doc" with content type "application/msword"
    And LibreOffice conversion of this file succeeds and produces a valid PDF
    When I POST the candidate "Bob Singh" with email "bob.word@example.com" to "/api/candidates/"
    Then the response status is 201
    And a Candidate record exists with email "bob.word@example.com"
    And the Word-to-PDF converter was invoked exactly once

  # ───────────────────────────────────────────────────────────────────────────
  # Scenario Group 2 — Conversion failure handling
  # ───────────────────────────────────────────────────────────────────────────

  Scenario: A Word file that LibreOffice cannot convert fails gracefully
    Given a candidate upload named "resume.docx" with content type "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    And LibreOffice conversion of this file fails with "soffice exited with code 1"
    When I POST the candidate "Carol Diaz" with email "carol.word@example.com" to "/api/candidates/"
    Then the response status is 400
    And the response body contains field "resume_pdf"
    And no Candidate record exists with email "carol.word@example.com"

  Scenario: A Word conversion subprocess timeout is handled gracefully
    Given a candidate upload named "resume.docx" with content type "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    And LibreOffice conversion of this file times out
    When I POST the candidate "Dana Lee" with email "dana.word@example.com" to "/api/candidates/"
    Then the response status is 400
    And the response body contains field "resume_pdf"
    And no Candidate record exists with email "dana.word@example.com"

  # ───────────────────────────────────────────────────────────────────────────
  # Scenario Group 3 — Regression and validation guards
  # ───────────────────────────────────────────────────────────────────────────

  Scenario: A PDF resume upload still works without invoking the Word converter
    Given a candidate upload named "resume.pdf" with content type "application/pdf"
    When I POST the candidate "Erin Walsh" with email "erin.pdf@example.com" to "/api/candidates/"
    Then the response status is 201
    And a Candidate record exists with email "erin.pdf@example.com"
    And the Word-to-PDF converter was never invoked

  Scenario: A disallowed file type is rejected with a 400 before conversion
    Given a candidate upload named "resume.txt" with content type "text/plain"
    When I POST the candidate "Frank Otieno" with email "frank.txt@example.com" to "/api/candidates/"
    Then the response status is 400
    And the response body contains field "resume_pdf"
    And the Word-to-PDF converter was never invoked

  Scenario: An oversized Word file is rejected before any conversion is attempted
    Given a candidate upload named "resume.docx" with content type "application/vnd.openxmlformats-officedocument.wordprocessingml.document" and size 11000000 bytes
    When I POST the candidate "Grace Kim" with email "grace.big@example.com" to "/api/candidates/"
    Then the response status is 400
    And the response body contains field "resume_pdf"
    And the Word-to-PDF converter was never invoked
