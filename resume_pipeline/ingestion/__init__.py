"""
resume_pipeline.ingestion — M0.5 Document Ingestion Pipeline.

Public API::

    from resume_pipeline.ingestion.parser import ResumeParser, ParsedDocument, ParseStatus
    from resume_pipeline.ingestion.section_detector import SectionDetector
    from resume_pipeline.ingestion.backends.pymupdf_backend import PyMuPDFBackend
    from resume_pipeline.ingestion.backends.pdfplumber_backend import PdfplumberBackend
"""
