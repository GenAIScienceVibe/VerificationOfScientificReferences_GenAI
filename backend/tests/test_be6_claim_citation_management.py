from __future__ import annotations

import pytest
from testsupport.api_client import ApiTestClient as TestClient

from app.main import app
from app.models import Document, Reference
from app.models.enums import DocumentStatus, DoiStatus, MappingStatus, MetadataStatus, UploadType
from app.db.session import SessionLocal
from app.services.citation_mapping import CitationReferenceMapper
from app.services.claim_preparation import ClaimPreparationService, CitationDetectionService
from app.services.genai_claim_extraction import ClaimExtractionValidator

client = TestClient(app)


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert payload["success"] is success
    assert "data" in payload
    assert isinstance(payload["errors"], list)
    assert payload["request_id"].startswith("req_")


def test_citation_detection_patterns() -> None:
    detector = CitationDetectionService()
    text = "Smith (2023) and Lee (2022) show benefits (Smith et al., 2023; Lee & Kim, 2022), also [1], [2, 3], and [1-3]."
    citations = detector.detect(text)
    values = [item.citation_text for item in citations]
    assert "Smith (2023)" in values
    assert "(Smith et al., 2023; Lee & Kim, 2022)" in values
    assert "[1]" in values
    assert "[2, 3]" in values
    assert "[1-3]" in values


def test_claim_preparation_excludes_references_section_and_preserves_citations() -> None:
    with SessionLocal() as db:
        document = Document(filename="claim.txt", title="Claim Prep", upload_type=UploadType.TEXT.value, status=DocumentStatus.REFERENCES_EXTRACTED.value, cleaned_text="unused")
        db.add(document)
        db.flush()
        from app.models import DocumentSection
        db.add_all([
            DocumentSection(document_id=document.id, name="Introduction", order_index=1, text="AI improves writing outcomes (Smith, 2023). This has no citation."),
            DocumentSection(document_id=document.id, name="References", order_index=2, text="Smith, J. (2023). Reference should not become claim."),
        ])
        db.commit()
        db.refresh(document)
        prepared = ClaimPreparationService().prepare(document, document.sections)
        assert len(prepared) == 1
        assert prepared[0].section_name == "Introduction"
        assert prepared[0].detected_citations[0].citation_text == "(Smith, 2023)"
        assert "Reference should not become claim" not in prepared[0].sentence_text


def test_genai_output_validation_rejects_invalid_and_invented_citations() -> None:
    prepared = ClaimPreparationService()._split_sentences("AI improves writing outcomes (Smith, 2023).")
    # Build a prepared sentence through the public prepare path to avoid constructing internals manually.
    with SessionLocal() as db:
        document = Document(filename="claim.txt", title="Claim Prep", upload_type=UploadType.TEXT.value, status=DocumentStatus.REFERENCES_EXTRACTED.value, cleaned_text="AI improves writing outcomes (Smith, 2023).")
        db.add(document)
        db.flush()
        from app.models import DocumentSection
        section = DocumentSection(document_id=document.id, name="Introduction", order_index=1, text="AI improves writing outcomes (Smith, 2023).")
        db.add(section)
        db.commit()
        db.refresh(document)
        sentence = ClaimPreparationService().prepare(document, document.sections)[0]
    validator = ClaimExtractionValidator()
    with pytest.raises(Exception):
        validator.validate("not-json", sentence)
    with pytest.raises(Exception):
        validator.validate({"claims": [{"claim_text": "AI improves writing outcomes.", "citation_text": "(Invented, 2099)", "claim_type": "EMPIRICAL", "confidence": 0.8}]}, sentence)


def test_citation_mapping_apa_and_numbered() -> None:
    with SessionLocal() as db:
        doc = Document(filename="map.txt", title="Map", upload_type=UploadType.TEXT.value, status=DocumentStatus.REFERENCES_EXTRACTED.value)
        db.add(doc)
        db.flush()
        r1 = Reference(document_id=doc.id, raw_reference="Smith, J. (2023). AI Writing.", extracted_authors="Smith, J.", extracted_year=2023, doi_status=DoiStatus.MISSING.value, metadata_status=MetadataStatus.NOT_LOOKED_UP.value)
        r2 = Reference(document_id=doc.id, raw_reference="Lee, A. (2022). AI Trust.", extracted_authors="Lee, A.", extracted_year=2022, doi_status=DoiStatus.MISSING.value, metadata_status=MetadataStatus.NOT_LOOKED_UP.value)
        db.add_all([r1, r2])
        db.flush()
        refs = [r1, r2]
        mapper = CitationReferenceMapper()
        assert mapper.map_citation("(Smith, 2023)", refs)[0].reference_id == r1.id
        numbered = mapper.map_citation("[1-2]", refs)
        assert [item.reference_id for item in numbered] == [r1.id, r2.id]
        assert mapper.map_citation("(Unknown, 2020)", refs)[0].mapping_status == MappingStatus.NO_MATCH.value


def test_extract_claims_api_success_and_related_endpoints() -> None:
    text = """
Demo Paper

Abstract
Generative AI tools can improve academic writing productivity (Smith, 2023).

Introduction
Trust shapes students' adoption of AI tools (Lee, 2022; Smith, 2023).

References
Smith, J. (2023). AI Writing Assistants and Student Productivity. https://doi.org/10.1234/demo.smith
Lee, A. (2022). Trust in AI tools. https://doi.org/10.1234/demo.lee
"""
    response = client.post("/api/v1/documents/text", json={"title": "Demo Paper", "text": text})
    assert response.status_code == 200
    document_id = response.json()["data"]["document_id"]
    ref_response = client.post(f"/api/v1/documents/{document_id}/extract-references")
    assert ref_response.status_code == 200
    claim_response = client.post(f"/api/v1/documents/{document_id}/extract-claims", json={"mode": "citation_linked_only"})
    assert claim_response.status_code == 200
    payload = claim_response.json()
    assert_wrapper(payload)
    assert payload["data"]["claims_count"] >= 2
    assert payload["data"]["citations_count"] >= 2
    assert payload["data"]["mapped_links_count"] >= 2

    claims = client.get(f"/api/v1/documents/{document_id}/claims").json()["data"]
    assert claims["total"] >= 2
    claim_id = claims["claims"][0]["claim_id"]
    assert client.get(f"/api/v1/claims/{claim_id}").status_code == 200

    citations = client.get(f"/api/v1/documents/{document_id}/citations").json()["data"]
    assert citations["total"] >= 2

    links = client.get(f"/api/v1/documents/{document_id}/claim-reference-links").json()["data"]
    assert links["total"] >= 2
    link_id = links["links"][0]["link_id"]
    assert client.get(f"/api/v1/claim-reference-links/{link_id}").status_code == 200
    assert client.get(f"/api/v1/documents/{document_id}/claim-reference-map").status_code == 200

    # Rerun should replace existing BE-6 data instead of duplicating claims endlessly.
    rerun = client.post(f"/api/v1/documents/{document_id}/extract-claims", json={"mode": "citation_linked_only"})
    assert rerun.status_code == 200
    claims_after = client.get(f"/api/v1/documents/{document_id}/claims").json()["data"]
    assert claims_after["total"] == claims["total"]


def test_extract_claims_missing_document_and_no_references_errors() -> None:
    missing = client.post("/api/v1/documents/doc_missing/extract-claims", json={"mode": "citation_linked_only"})
    assert missing.status_code == 404
    assert missing.json()["errors"][0]["code"] == "DOCUMENT_NOT_FOUND"

    response = client.post("/api/v1/documents/text", json={"title": "No References Yet", "text": "Abstract\nAI helps learning (Smith, 2023).\n"})
    document_id = response.json()["data"]["document_id"]
    no_refs = client.post(f"/api/v1/documents/{document_id}/extract-claims", json={"mode": "citation_linked_only"})
    assert no_refs.status_code == 409
    assert no_refs.json()["errors"][0]["code"] == "REFERENCES_NOT_FOUND"
