"""Shared fixtures: a real export case built from the real demo PDFs."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.schemas import (
    CaseProfile,
    DocumentEvidence,
    DocumentType,
    ExporterInfo,
    ExportCase,
    ShipmentInfo,
)
from modules import documents as document_intelligence
from modules.corpus import load_corpus
from modules.profile import build_profile
from modules.requirements import build_requirements

FIXTURES = Path(__file__).resolve().parent.parent / "data" / "fixtures"

INVOICE_500 = FIXTURES / "invoice_500.pdf"
PACKING_450 = FIXTURES / "packing_list_450.pdf"
PACKING_500 = FIXTURES / "packing_list_500.pdf"
CERTIFICATE = FIXTURES / "certificate_of_origin.pdf"
SCANNED = FIXTURES / "scanned_no_text.pdf"


@pytest.fixture(scope="session")
def corpus():
    return load_corpus()


@pytest.fixture
def profile() -> CaseProfile:
    """The golden-path case profile, with product understanding applied."""
    profile = CaseProfile(
        product_raw="Handmade full-grain leather shoulder bags",
        destination="Germany",
        exporter=ExporterInfo(
            name="Sialkot Leather Crafts (Pvt) Ltd",
            address="Plot 14, Small Industrial Estate, Sialkot, Pakistan",
        ),
        shipment=ShipmentInfo(
            buyer_name="Hoffmann Lederwaren GmbH",
            invoice_number="INV-2026-0412",
            declared_quantity="500",
        ),
    )
    build_profile(profile, use_ai=False)
    return profile


#: Stands in for the Streamlit file store when the pipeline runs in a test.
FILE_STORE: dict[str, bytes] = {}


def attach(case: ExportCase, path: Path, document_type: DocumentType) -> DocumentEvidence:
    """Attach a fixture PDF to a case and read it, as the app does."""
    evidence = DocumentEvidence(
        document_id=f"DOC-{len(case.documents) + 1:03d}",
        filename=path.name,
        document_type=document_type,
        size_bytes=path.stat().st_size,
    )
    data = path.read_bytes()
    FILE_STORE[evidence.document_id] = data
    document_intelligence.read_document(evidence, data, use_ai=False)
    case.documents.append(evidence)
    return evidence


@pytest.fixture
def run_context():
    """A RunContext wired to the test file store, with the LLM switched off."""
    from core.orchestrator import RunContext

    return RunContext(
        use_ai=False,
        file_provider=FILE_STORE.get,
        text_sink=lambda document_id, text: None,
    )


@pytest.fixture(autouse=True)
def _clean_file_store():
    FILE_STORE.clear()
    yield
    FILE_STORE.clear()


@pytest.fixture(autouse=True)
def _offline_by_default(request, monkeypatch):
    """No test reaches the network unless it says it means to.

    Without this, simply having GROQ_API_KEY in the environment changes what
    the suite tests: the workflow tests start making real calls, take minutes,
    and fail on rate limits. A test suite whose result depends on whether a
    key happens to be exported is not telling anyone anything.

    It removes the KEY, not the code that looks for it: `api_key()` still runs
    for real and simply finds nothing, so the tests that exercise key
    detection itself keep working by setting their own.

    Three ways past it, all explicit:
      * mark a test `live` — tests/test_llm_live.py does, and really does call
        Groq;
      * set GROQ_API_KEY yourself with monkeypatch.setenv, as the gateway
        detection tests do;
      * install a fake client, as the interpretation, agent and activity tests
        do. All of these run after this fixture and win.
    """
    if request.node.get_closest_marker("live"):
        return
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    # Stops the real .env being read back in behind the delenv.
    monkeypatch.setattr("core.llm._dotenv_loaded", True)


def build_case(profile: CaseProfile, corpus, *attachments) -> ExportCase:
    """A case with requirements loaded and the given documents read."""
    case = ExportCase(case_id="BA-001", profile=profile)
    result = build_requirements(profile, corpus=corpus, use_ai=False)
    case.requirements = result.payload["requirements"]
    for path, document_type in attachments:
        attach(case, path, document_type)
    return case


@pytest.fixture
def full_case(profile, corpus) -> ExportCase:
    """The golden demo's starting point: invoice 500 vs packing list 450."""
    return build_case(
        profile,
        corpus,
        (INVOICE_500, DocumentType.COMMERCIAL_INVOICE),
        (PACKING_450, DocumentType.PACKING_LIST),
        (CERTIFICATE, DocumentType.CERTIFICATE_OF_ORIGIN),
    )


@pytest.fixture
def fixed_case(profile, corpus) -> ExportCase:
    """The same case after the exporter corrects the packing list to 500."""
    return build_case(
        profile,
        corpus,
        (INVOICE_500, DocumentType.COMMERCIAL_INVOICE),
        (PACKING_500, DocumentType.PACKING_LIST),
        (CERTIFICATE, DocumentType.CERTIFICATE_OF_ORIGIN),
    )
