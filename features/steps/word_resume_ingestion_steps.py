"""
Step definitions for features/word_resume_ingestion.feature — M8 outer BDD loop.

Strategy mirrors features/steps/job_lifecycle_steps.py: drive the real view
(`CandidateListCreateView`) through `APIRequestFactory`, with the ORM
(`Candidate`) replaced by an in-memory fake store so no real database is
needed for the outer loop. The only thing genuinely mocked beyond the ORM
is `convert_word_to_pdf` — its real implementation shells out to a real
LibreOffice binary, which these scenarios stand in for via
`ctx["conversion_outcome"]` (success / error / timeout).

ResumeParser itself is NOT mocked: it is designed to degrade gracefully on
unparseable bytes (see features/document_ingestion.feature), so feeding it
fake "%PDF-..." bytes after a successful conversion exercises the real,
already-tested parsing path with empty-but-valid results.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from pytest_bdd import given, parsers, scenarios, then, when
from rest_framework.test import APIRequestFactory

pytestmark = pytest.mark.bdd

scenarios("word_resume_ingestion.feature")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx() -> dict:
    return {}


# ---------------------------------------------------------------------------
# In-memory fake Candidate ORM — no real database required
# ---------------------------------------------------------------------------

class _FakeQuerySet:
    def __init__(self, items: list) -> None:
        self._items = items

    def exists(self) -> bool:
        return len(self._items) > 0


class _FakeCandidateManager:
    """Stands in for Candidate.objects against ctx["candidate_store"]."""

    def __init__(self, store: list) -> None:
        self._store = store

    def filter(self, **kwargs):
        email = kwargs.get("email")
        return _FakeQuerySet([c for c in self._store if c.email == email])

    def create(self, **kwargs):
        candidate = MagicMock()
        candidate.id = uuid.uuid4()
        candidate.name = kwargs.get("name")
        candidate.email = kwargs.get("email")
        candidate.resume_raw = kwargs.get("resume_raw")
        candidate.resume_parsed = kwargs.get("resume_parsed")
        # Explicit string (not an auto-generated MagicMock attribute) so
        # DRF's DateTimeField.to_representation() — which passes strings
        # through unchanged — can serialize it without a real datetime.
        candidate.created_at = "2026-06-16T00:00:00Z"
        self._store.append(candidate)
        return candidate


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

@given("the candidate ingestion endpoint is initialized")
def init_endpoint(ctx: dict) -> None:
    ctx["candidate_store"] = []
    ctx["converter_calls"] = []
    ctx["conversion_outcome"] = ("success", b"%PDF-1.4 default fake content")
    ctx["upload_size"] = 1024


@given("the database is empty of Candidate records")
def empty_db(ctx: dict) -> None:
    ctx["candidate_store"] = []


# ---------------------------------------------------------------------------
# Given — upload fixtures
# ---------------------------------------------------------------------------

@given(parsers.parse(
    'a candidate upload named "{filename}" with content type "{content_type}"'
))
def upload_named(ctx: dict, filename: str, content_type: str) -> None:
    ctx["upload_filename"] = filename
    ctx["upload_content_type"] = content_type


@given(parsers.parse(
    'a candidate upload named "{filename}" with content type "{content_type}" '
    "and size {size:d} bytes"
))
def upload_named_with_size(ctx: dict, filename: str, content_type: str, size: int) -> None:
    ctx["upload_filename"] = filename
    ctx["upload_content_type"] = content_type
    ctx["upload_size"] = size


@given("LibreOffice conversion of this file succeeds and produces a valid PDF")
def conversion_succeeds(ctx: dict) -> None:
    ctx["conversion_outcome"] = ("success", b"%PDF-1.4 converted content")


@given(parsers.parse('LibreOffice conversion of this file fails with "{message}"'))
def conversion_fails(ctx: dict, message: str) -> None:
    ctx["conversion_outcome"] = ("error", message)


@given("LibreOffice conversion of this file times out")
def conversion_times_out(ctx: dict) -> None:
    ctx["conversion_outcome"] = ("timeout", "Conversion timed out after 30s.")


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------

@when(parsers.parse('I POST the candidate "{name}" with email "{email}" to "{path}"'))
def post_candidate(ctx: dict, name: str, email: str, path: str) -> None:
    from resume_pipeline.ingestion.word_converter import WordConversionError
    from resume_pipeline.views import CandidateListCreateView

    size = ctx.get("upload_size", 1024)
    content = b"x" * size
    upload = SimpleUploadedFile(
        ctx["upload_filename"], content, content_type=ctx["upload_content_type"]
    )

    converter_calls = ctx["converter_calls"]

    def fake_convert(file_bytes, original_filename):
        converter_calls.append((file_bytes, original_filename))
        kind, payload = ctx["conversion_outcome"]
        if kind == "success":
            return payload
        if kind in ("error", "timeout"):
            raise WordConversionError(payload)
        raise AssertionError(f"Unknown conversion outcome kind: {kind}")

    store = ctx["candidate_store"]
    fake_manager = _FakeCandidateManager(store)

    factory = APIRequestFactory()
    request = factory.post(
        path,
        data={"name": name, "email": email, "resume_pdf": upload},
        format="multipart",
    )

    with patch("resume_pipeline.views.convert_word_to_pdf", side_effect=fake_convert), \
         patch("resume_pipeline.views.Candidate") as MockViewCandidate, \
         patch("resume_pipeline.serializers.Candidate") as MockSerializerCandidate:
        MockViewCandidate.objects = fake_manager
        MockSerializerCandidate.objects.filter.side_effect = (
            lambda **kw: _FakeQuerySet([c for c in store if c.email == kw.get("email")])
        )
        view = CandidateListCreateView.as_view()
        ctx["response"] = view(request)


# ---------------------------------------------------------------------------
# Then — response assertions
# ---------------------------------------------------------------------------

@then(parsers.parse("the response status is {code:d}"))
def assert_status(ctx: dict, code: int) -> None:
    assert ctx["response"].status_code == code, (
        f"Expected {code}, got {ctx['response'].status_code}. "
        f"Body: {getattr(ctx['response'], 'data', '(no data)')}"
    )


@then(parsers.parse('the response body contains field "{field}"'))
def assert_response_has_field(ctx: dict, field: str) -> None:
    data = ctx["response"].data
    assert field in data, f"Field '{field}' missing from response: {data}"


# ---------------------------------------------------------------------------
# Then — Candidate store assertions
# ---------------------------------------------------------------------------

@then(parsers.parse('a Candidate record exists with email "{email}"'))
def assert_candidate_exists(ctx: dict, email: str) -> None:
    store = ctx["candidate_store"]
    assert any(c.email == email for c in store), (
        f"No candidate with email '{email}'. Store emails: {[c.email for c in store]}"
    )


@then(parsers.parse('no Candidate record exists with email "{email}"'))
def assert_candidate_absent(ctx: dict, email: str) -> None:
    store = ctx["candidate_store"]
    assert not any(c.email == email for c in store), (
        f"Unexpected candidate with email '{email}' found in store."
    )


# ---------------------------------------------------------------------------
# Then — Word converter invocation assertions
# ---------------------------------------------------------------------------

@then("the Word-to-PDF converter was invoked exactly once")
def assert_converter_invoked_once(ctx: dict) -> None:
    calls = ctx["converter_calls"]
    assert len(calls) == 1, f"Expected exactly 1 conversion call, got {len(calls)}"


@then("the Word-to-PDF converter was never invoked")
def assert_converter_never_invoked(ctx: dict) -> None:
    calls = ctx["converter_calls"]
    assert len(calls) == 0, f"Expected 0 conversion calls, got {len(calls)}: {calls}"
