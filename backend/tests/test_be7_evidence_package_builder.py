from __future__ import annotations

from testsupport.api_client import ApiTestClient as TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import Citation, Claim, ClaimReferenceLink, Document, EvidencePackage, Reference, SourceMetadata
from app.models.enums import (
    DocumentStatus,
    DoiStatus,
    EvidenceAvailability,
    MappingStatus,
    MetadataStatus,
    UploadType,
)
from app.services.evidence_package_builder import EvidencePackageBuilder

client = TestClient(app)


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert payload["success"] is success
    assert "data" in payload
    assert isinstance(payload["errors"], list)
    assert payload["request_id"].startswith("req_")


def _create_evidence_ready_records(*, with_metadata: bool = True, abstract: str | None = "Official abstract text.", mapping_status: str = MappingStatus.MAPPED.value):
    with SessionLocal() as db:
        doc = Document(filename="evidence.txt", title="Evidence Demo", upload_type=UploadType.TEXT.value, status=DocumentStatus.CLAIMS_EXTRACTED.value)
        db.add(doc)
        db.flush()
        ref = Reference(
            document_id=doc.id,
            reference_key="Smith_2023",
            raw_reference="Smith, J. (2023). AI Writing Assistants. https://doi.org/10.1234/demo",
            extracted_title="AI Writing Assistants",
            extracted_authors="Smith, J.",
            extracted_year=2023,
            extracted_doi="10.1234/demo",
            doi_status=DoiStatus.VALID.value,
            metadata_status=MetadataStatus.LOOKUP_SUCCEEDED.value if with_metadata else MetadataStatus.NOT_LOOKED_UP.value,
            metadata_match_score=0.91 if with_metadata else None,
        )
        claim = Claim(
            document_id=doc.id,
            claim_text="AI tools improve academic writing productivity.",
            claim_type="EMPIRICAL",
            section_name="Introduction",
            source_paragraph="AI tools improve academic writing productivity (Smith, 2023).",
            paragraph_index=1,
            sentence_index=0,
            extraction_confidence=0.88,
        )
        db.add_all([ref, claim])
        db.flush()
        citation = Citation(
            document_id=doc.id,
            claim_id=claim.id,
            raw_citation="(Smith, 2023)",
            citation_style="APA",
            sentence_text="AI tools improve academic writing productivity (Smith, 2023).",
            paragraph_index=1,
            mapped_reference_id=ref.id,
            mapping_confidence=0.95,
        )
        db.add(citation)
        db.flush()
        link = ClaimReferenceLink(
            document_id=doc.id,
            claim_id=claim.id,
            citation_id=citation.id,
            reference_id=ref.id,
            mapping_status=mapping_status,
            mapping_confidence=0.95 if mapping_status == MappingStatus.MAPPED.value else 0.52,
            mapping_reason="Author and year match.",
        )
        db.add(link)
        if with_metadata:
            db.add(
                SourceMetadata(
                    reference_id=ref.id,
                    doi="10.1234/demo",
                    title="AI Writing Assistants and Student Productivity",
                    authors="Smith, J.",
                    year=2023,
                    venue="Journal of AI Education",
                    publisher="Example Publisher",
                    abstract=abstract,
                    url="https://doi.org/10.1234/demo",
                    lookup_source="crossref",
                    lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
                    metadata_match_score=0.93,
                    title_match=0.9,
                    author_match=1.0,
                    year_match=True,
                    doi_match=True,
                )
            )
        db.commit()
        return doc.id, claim.id, ref.id, link.id


def test_prepare_evidence_api_creates_abstract_available_package() -> None:
    document_id, claim_id, _ref_id, _link_id = _create_evidence_ready_records()
    response = client.post(f"/api/v1/documents/{document_id}/prepare-evidence")
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    assert payload["data"]["evidence_packages_created"] == 1
    assert payload["data"]["abstract_available"] == 1
    assert payload["data"]["status"] == DocumentStatus.EVIDENCE_READY.value

    claim_response = client.get(f"/api/v1/claims/{claim_id}/evidence-package")
    assert claim_response.status_code == 200
    package = claim_response.json()["data"]["evidence_packages"][0]
    assert package["claim_text"] == "AI tools improve academic writing productivity."
    assert package["citation_text"] == "(Smith, 2023)"
    assert package["doi"] == "10.1234/demo"
    assert package["metadata"]["title"] == "AI Writing Assistants and Student Productivity"
    assert package["source_evidence"]["evidence_availability"] == EvidenceAvailability.ABSTRACT_AVAILABLE.value
    assert package["source_evidence"]["text"] == "Official abstract text."
    assert package["policy"]["embedding_model_version"] == "embedding-v1"
    assert package["policy"]["prompt_version"] == "verify-v1"
    assert package["policy"]["verification_policy_version"] == "policy-v1"


def test_metadata_without_abstract_becomes_metadata_only() -> None:
    document_id, _claim_id, _ref_id, _link_id = _create_evidence_ready_records(abstract=None)
    assert client.post(f"/api/v1/documents/{document_id}/prepare-evidence").status_code == 200
    packages = client.get(f"/api/v1/documents/{document_id}/evidence-packages").json()["data"]
    package = packages["evidence_packages"][0]
    assert package["source_evidence"]["evidence_availability"] == EvidenceAvailability.METADATA_ONLY.value
    assert package["source_evidence"]["text"] is None


def test_reference_without_metadata_uses_fallback_and_warning() -> None:
    document_id, claim_id, _ref_id, _link_id = _create_evidence_ready_records(with_metadata=False)
    assert client.post(f"/api/v1/documents/{document_id}/prepare-evidence").status_code == 200
    package = client.get(f"/api/v1/claims/{claim_id}/evidence-package").json()["data"]["evidence_packages"][0]
    assert package["metadata"]["source"] == "reference_extracted_fields"
    assert package["source_evidence"]["evidence_availability"] == EvidenceAvailability.METADATA_ONLY.value
    assert any(item["code"] == "METADATA_UNAVAILABLE" for item in package["warnings"])


def test_uncertain_mapping_package_contains_warning() -> None:
    document_id, claim_id, _ref_id, _link_id = _create_evidence_ready_records(mapping_status=MappingStatus.UNCERTAIN.value)
    assert client.post(f"/api/v1/documents/{document_id}/prepare-evidence").status_code == 200
    package = client.get(f"/api/v1/claims/{claim_id}/evidence-package").json()["data"]["evidence_packages"][0]
    assert package["mapping"]["mapping_status"] == MappingStatus.UNCERTAIN.value
    assert any(item["code"] == "UNCERTAIN_MAPPING" for item in package["warnings"])


def test_prepare_evidence_is_idempotent() -> None:
    document_id, _claim_id, _ref_id, _link_id = _create_evidence_ready_records()
    first = client.post(f"/api/v1/documents/{document_id}/prepare-evidence")
    second = client.post(f"/api/v1/documents/{document_id}/prepare-evidence")
    assert first.status_code == 200
    assert second.status_code == 200
    with SessionLocal() as db:
        packages = db.query(EvidencePackage).filter(EvidencePackage.document_id == document_id).all()
        assert len(packages) == 1


def test_prepare_evidence_missing_document_and_no_claims_errors() -> None:
    missing = client.post("/api/v1/documents/doc_missing/prepare-evidence")
    assert missing.status_code == 404
    assert missing.json()["errors"][0]["code"] == "DOCUMENT_NOT_FOUND"

    with SessionLocal() as db:
        doc = Document(filename="empty.txt", title="Empty", upload_type=UploadType.TEXT.value, status=DocumentStatus.CLAIMS_EXTRACTED.value)
        db.add(doc)
        db.commit()
        document_id = doc.id
    no_claims = client.post(f"/api/v1/documents/{document_id}/prepare-evidence")
    assert no_claims.status_code == 409
    assert no_claims.json()["errors"][0]["code"] == "CLAIM_NOT_FOUND"


def test_get_evidence_package_for_missing_claim_or_unbuilt_package() -> None:
    missing = client.get("/api/v1/claims/claim_missing/evidence-package")
    assert missing.status_code == 404
    assert missing.json()["errors"][0]["code"] == "CLAIM_NOT_FOUND"

    document_id, claim_id, _ref_id, _link_id = _create_evidence_ready_records()
    unbuilt = client.get(f"/api/v1/claims/{claim_id}/evidence-package")
    assert unbuilt.status_code == 404
    assert unbuilt.json()["errors"][0]["code"] == "EVIDENCE_PACKAGE_NOT_FOUND"


def test_ssrn_doi_becomes_preprint_available() -> None:
    """A reference with a 10.2139/ssrn.* DOI is classified as PREPRINT_AVAILABLE."""
    with SessionLocal() as db:
        doc = Document(filename="ssrn.txt", title="SSRN Demo", upload_type=UploadType.TEXT.value, status=DocumentStatus.CLAIMS_EXTRACTED.value)
        db.add(doc)
        db.flush()
        ref = Reference(
            document_id=doc.id,
            reference_key="Zhu_2016",
            raw_reference="Zhu, D.H. & Shen, W. (2016). An SSRN working paper.",
            extracted_title="An SSRN working paper",
            extracted_authors="Zhu, D.H.",
            extracted_year=2016,
            extracted_doi="10.2139/ssrn.2803610",
            doi_status=DoiStatus.VALID.value,
            metadata_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            metadata_match_score=0.90,
        )
        claim = Claim(
            document_id=doc.id,
            claim_text="CEOs engage in more acquisitions after peer firms do.",
            claim_type="EMPIRICAL",
            section_name="Introduction",
            source_paragraph="CEOs engage in more acquisitions after peer firms do (Zhu & Shen, 2016).",
            paragraph_index=1,
            sentence_index=0,
            extraction_confidence=0.85,
        )
        db.add_all([ref, claim])
        db.flush()
        citation = Citation(document_id=doc.id, claim_id=claim.id, raw_citation="(Zhu & Shen, 2016)", citation_style="APA", sentence_text=claim.source_paragraph, mapped_reference_id=ref.id, mapping_confidence=0.91)
        db.add(citation)
        db.flush()
        db.add(ClaimReferenceLink(document_id=doc.id, claim_id=claim.id, citation_id=citation.id, reference_id=ref.id, mapping_status=MappingStatus.MAPPED.value, mapping_confidence=0.91, mapping_reason="Author and year match."))
        db.add(SourceMetadata(
            reference_id=ref.id,
            doi="10.2139/ssrn.2803610",
            title="An SSRN working paper",
            authors="Zhu, D.H.",
            year=2016,
            abstract="This paper examines CEO peer effects in acquisition decisions.",
            url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2803610",
            lookup_source="CrossRef",
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            metadata_match_score=0.90,
        ))
        db.commit()
        result = EvidencePackageBuilder().prepare_evidence_for_document(doc.id, db)
        assert result["preprint_available"] == 1
        assert result["abstract_available"] == 0
        package = db.query(EvidencePackage).filter(EvidencePackage.document_id == doc.id).one()
        assert package.evidence_availability == EvidenceAvailability.PREPRINT_AVAILABLE.value
        assert any(item["code"] == "PREPRINT_SOURCE" for item in (package.package_warnings_json or []))


def test_direct_builder_source_unavailable_when_no_metadata_and_no_fields() -> None:
    with SessionLocal() as db:
        doc = Document(filename="source-unavailable.txt", title="Source unavailable", upload_type=UploadType.TEXT.value, status=DocumentStatus.CLAIMS_EXTRACTED.value)
        db.add(doc)
        db.flush()
        ref = Reference(document_id=doc.id, raw_reference="Unknown source without DOI", doi_status=DoiStatus.MISSING.value, metadata_status=MetadataStatus.METADATA_UNAVAILABLE.value)
        claim = Claim(document_id=doc.id, claim_text="A weakly sourced claim.", claim_type="UNKNOWN", section_name="Body")
        db.add_all([ref, claim])
        db.flush()
        citation = Citation(document_id=doc.id, claim_id=claim.id, raw_citation="(Unknown, 2020)", citation_style="APA")
        db.add(citation)
        db.flush()
        db.add(ClaimReferenceLink(document_id=doc.id, claim_id=claim.id, citation_id=citation.id, reference_id=ref.id, mapping_status=MappingStatus.NEEDS_HUMAN_REVIEW.value, mapping_confidence=0.2))
        db.commit()
        result = EvidencePackageBuilder().prepare_evidence_for_document(doc.id, db)
        assert result["source_unavailable"] == 1
        package = db.query(EvidencePackage).filter(EvidencePackage.document_id == doc.id).one()
        assert package.evidence_availability == EvidenceAvailability.SOURCE_UNAVAILABLE.value
