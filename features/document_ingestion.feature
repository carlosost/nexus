Feature: Resume Document Ingestion & Parsing — Milestone 0.5
  As a pipeline operator
  I want raw PDF resume files converted to structured, section-labelled JSON
  So that every downstream stage receives clean, consistent input

  Background:
    Given the document ingestion pipeline is initialized
    And the observability sink is fresh

  # ---------------------------------------------------------------------------
  # Primary path — PyMuPDF extraction
  # ---------------------------------------------------------------------------

  Scenario: Extract plain text from a standard single-page PDF using PyMuPDF
    Given a PDF file "resume_plain.pdf" containing at least 200 characters of readable text
    When I parse the document
    Then the parse result status is "ok"
    And the raw text contains at least 200 characters
    And the parser used is "pymupdf"
    And a "document_parsed" audit event is emitted
    And a latency record exists for stage "document_ingestion"

  Scenario: Parse result includes correct page count
    Given a PDF file "resume_two_pages.pdf" with 2 pages
    When I parse the document
    Then the page count is 2

  Scenario: char_count reflects the length of raw_text
    Given a PDF file "resume_plain.pdf" containing at least 200 characters of readable text
    When I parse the document
    Then the char_count equals the length of raw_text

  # ---------------------------------------------------------------------------
  # Section detection — spaCy NLP with Gherkin Data Tables
  #
  # Data Tables eliminate per-key Then assertions. All section variations are
  # expressed as rows; the step iterates them. Adding a new header synonym
  # requires only a new row — zero scenario or step-definition changes.
  # ---------------------------------------------------------------------------

  Scenario: Detect canonical sections from a structured multi-section resume
    Given the resume text is built from the following section table:
      | header_text      | canonical_key | sample_content                                          |
      | Experience       | experience    | Senior Python Engineer at Acme Corp 2019 to 2024        |
      | Technical Skills | skills        | Python Django PostgreSQL Docker Redis                   |
      | Education        | education     | BSc Computer Science University of California 2018      |
    When I detect sections in the text
    Then each canonical_key from the table is present in the detected sections
    And each section content from the table is stored under its canonical_key

  Scenario: Detect optional sections when present in the resume
    Given the resume text is built from the following section table:
      | header_text    | canonical_key  | sample_content                                             |
      | Certifications | certifications | AWS Solutions Architect Professional certified 2022        |
      | Projects       | projects       | Built distributed task queue handling 50k events per hour  |
      | Summary        | summary        | Experienced backend engineer specialising in distributed systems |
    When I detect sections in the text
    Then each canonical_key from the table is present in the detected sections

  Scenario: Section detector normalizes mixed-case and stylised headers to canonical keys
    Given the resume text is built from the following section table:
      | header_text       | canonical_key | sample_content                                    |
      | EXPERIENCE        | experience    | Principal Engineer at FooBar Technologies 2020    |
      | technical skills  | skills        | Python Rust Go TypeScript PostgreSQL              |
      | Education         | education     | MSc Software Engineering Imperial College 2019    |
    When I detect sections in the text
    Then each canonical_key from the table is present in the detected sections

  Scenario: Section detector maps known header synonyms to canonical keys
    Given the resume text is built from the following section table:
      | header_text         | canonical_key | sample_content                                     |
      | Work History        | experience    | Lead Engineer at StartupX 2021 to 2024             |
      | Core Competencies   | skills        | Distributed systems event sourcing CQRS Kafka      |
      | Academic Background | education     | BEng Electrical Engineering University of York     |
    When I detect sections in the text
    Then each canonical_key from the table is present in the detected sections

  Scenario: Section detector returns empty dict for unstructured text
    Given a text block with no recognisable section headers
    When I detect sections in the text
    Then the detected sections are empty
    And no exception is raised

  # ---------------------------------------------------------------------------
  # Fallback path — pdfplumber for complex layouts
  # ---------------------------------------------------------------------------

  Scenario: Fall back to pdfplumber when PyMuPDF yields fewer than 50 characters
    Given a PDF file "resume_multicolumn.pdf" that PyMuPDF extracts as fewer than 50 characters
    When I parse the document
    Then the parse result status is "fallback_used"
    And the parser used is "pdfplumber"
    And the raw text contains at least 50 characters
    And a "parser_fallback" audit event is emitted
    And the fallback audit event records primary "pymupdf" and fallback "pdfplumber"

  Scenario: Fallback result still triggers section detection
    Given a PDF file "resume_multicolumn.pdf" that PyMuPDF extracts as fewer than 50 characters
    And the pdfplumber extraction contains section header "Experience"
    When I parse the document
    Then the detected sections contain key "experience"

  # ---------------------------------------------------------------------------
  # Failure handling — no exceptions propagate
  # ---------------------------------------------------------------------------

  Scenario: Corrupted PDF returns failed status without raising an exception
    Given a corrupted file "resume_corrupt.pdf" that cannot be parsed
    When I parse the document
    Then the parse result status is "failed"
    And the raw text is empty
    And the detected sections are empty
    And no exception is raised
    And a "document_parse_failed" audit event is emitted

  Scenario: Non-existent file returns failed status without raising an exception
    Given a file path "resume_nonexistent.pdf" that does not exist
    When I parse the document
    Then the parse result status is "failed"
    And no exception is raised
    And a "document_parse_failed" audit event is emitted

  # ---------------------------------------------------------------------------
  # Observability contract
  # ---------------------------------------------------------------------------

  Scenario: Observability records latency for every parse call
    Given a PDF file "resume_plain.pdf" containing at least 200 characters of readable text
    When I parse the document
    Then a latency record exists for stage "document_ingestion"
    And the recorded latency is greater than 0 milliseconds

  Scenario: Observability records latency even when parse fails
    Given a corrupted file "resume_corrupt.pdf" that cannot be parsed
    When I parse the document
    Then a latency record exists for stage "document_ingestion"

  Scenario: Audit log emits stage_started before stage_completed
    Given a PDF file "resume_plain.pdf" containing at least 200 characters of readable text
    When I parse the document
    Then a "document_ingestion_started" audit event is emitted before "document_parsed"
