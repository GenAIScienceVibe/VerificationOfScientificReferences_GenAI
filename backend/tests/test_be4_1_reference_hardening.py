from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.db.session import session_scope
from app.main import app
from app.models import SourceMetadata
from app.models.enums import MetadataStatus
from app.repositories import ReferenceRepository
from app.services.document_processing_service import create_text_document, get_document_raw_text
from app.services.reference_extraction import ReferenceExtractionService, extract_references_for_document
from app.services.text_processing import clean_text, detect_basic_sections, repair_doi_line_continuations

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures" / "real_pdf_text"


def test_doi_line_continuation_repair_and_validation() -> None:
    repaired = repair_doi_line_continuations("https://doi.org/10.1111/j.1467-\n9280.2007.01882.x")
    assert "10.1111/j.1467-9280.2007.01882.x" in repaired
    result = ReferenceExtractionService().extract_doi(repaired)
    assert result.doi_status == "FOUND"
    assert result.extracted_doi == "10.1111/j.1467-9280.2007.01882.x"

    malformed = ReferenceExtractionService().extract_doi("Broken DOI https://doi.org/10.1111/j.1467-")
    assert malformed.doi_status == "MALFORMED"


def test_pdf1_footer_noise_is_not_extracted_as_reference() -> None:
    text = clean_text((FIXTURES / "pdf1_reference_section_sample.txt").read_text())
    section = ReferenceExtractionService().find_reference_section(cleaned_text=text, sections=[])
    refs = ReferenceExtractionService().split_references(section.text)
    assert len(refs) >= 3
    joined = "\n".join(refs).lower()
    assert "tepian vol" not in joined
    assert "p-issn" not in joined
    assert "– 9 –" not in joined
    assert not any(ref.strip().startswith("https://journalpedia.com/1/index.php/jsti") for ref in refs)


def test_pdf2_references_stop_before_appendix_and_survey_content() -> None:
    text = clean_text((FIXTURES / "pdf2_reference_section_sample.txt").read_text())
    sections = detect_basic_sections(text)
    ref_section = next(section for section in sections if section.name == "References")
    lowered = ref_section.text.lower()
    assert "appendix a" not in lowered
    assert "welcome to the study" not in lowered
    assert "employment status" not in lowered

    refs = ReferenceExtractionService().split_references(ref_section.text)
    joined = "\n".join(refs).lower()
    assert "welcome to the study" not in joined
    assert "employment status" not in joined
    assert not any(ref.lower().startswith("health, 12") for ref in refs)


def test_invalid_reference_query_filters_return_validation_wrapper() -> None:
    created = client.post(
        "/api/v1/documents/text",
        json={
            "title": "Filter Validation",
            "text": "Paper\n\nReferences\nSmith, J. (2023). Demo reference. doi:10.1234/demo.ref",
        },
    ).json()["data"]
    document_id = created["document_id"]
    response = client.get(f"/api/v1/documents/{document_id}/references", params={"doi_status": "BAD_STATUS"})
    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["errors"][0]["code"] == "VALIDATION_ERROR"
    assert payload["errors"][0]["field"] == "doi_status"


def test_raw_text_debug_service_is_blocked_when_disabled() -> None:
    with session_scope() as db:
        doc = create_text_document(
            title="Raw Debug Gate",
            text="Paper\n\nAbstract\nThis is enough text for processing.\n\nReferences\nSmith, J. (2023). Demo.",
            db=db,
        )
        try:
            get_document_raw_text(doc["document_id"], db, enabled=False)
        except Exception as exc:
            assert getattr(exc, "error").code == "DEBUG_ENDPOINT_DISABLED"
        else:  # pragma: no cover
            raise AssertionError("Expected DEBUG_ENDPOINT_DISABLED")


def test_corrupted_pdf_error_exposes_failed_document_id_for_audit() -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("broken.pdf", b"%PDF-1.4 broken", "application/pdf")},
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["errors"][0]["code"] in {"PDF_READ_FAILED", "TEXT_EXTRACTION_FAILED"}
    assert "doc_" in payload["errors"][0]["detail"]


def test_re_extraction_blocked_when_downstream_metadata_exists() -> None:
    response = client.post(
        "/api/v1/documents/text",
        json={
            "title": "Re-extract Block",
            "text": "Paper\n\nReferences\nSmith, J. (2023). Demo reference. doi:10.1234/demo.ref",
        },
    )
    document_id = response.json()["data"]["document_id"]
    first = client.post(f"/api/v1/documents/{document_id}/extract-references")
    assert first.status_code == 200

    with session_scope() as db:
        reference = ReferenceRepository(db).list_for_document(document_id)[0]
        db.add(
            SourceMetadata(
                reference_id=reference.id,
                doi=reference.extracted_doi,
                title="Demo metadata",
                lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            )
        )

    second = client.post(f"/api/v1/documents/{document_id}/extract-references")
    assert second.status_code == 409
    payload = second.json()
    assert payload["success"] is False
    assert payload["errors"][0]["code"] == "REFERENCE_REEXTRACTION_BLOCKED"
