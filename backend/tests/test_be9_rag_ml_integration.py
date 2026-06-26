from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppException, ErrorCode
from app.db.session import SessionLocal
from app.main import app
from app.models import Citation, Claim, ClaimReferenceLink, Document, EvidencePackage, RagRetrievalResult, Reference, SourceMetadata
from app.models.enums import DocumentStatus, DoiStatus, EvidenceAvailability, MappingStatus, MetadataStatus, RetrievalStatus, UploadType
from app.services.evidence_package_builder import EvidencePackageBuilder
from app.services.rag_ml_integration import RagClientResult, RagRequestBuilder, RagResponseValidator, RagRetrievalService

client = TestClient(app)


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert payload["success"] is success
    assert "data" in payload
    assert isinstance(payload["errors"], list)
    assert payload["request_id"].startswith("req_")


def _create_claim_reference_with_package(*, abstract: str | None = "Official abstract text.", with_metadata: bool = True, source_unavailable: bool = False):
    with SessionLocal() as db:
        doc = Document(filename="rag.txt", title="RAG Demo", upload_type=UploadType.TEXT.value, status=DocumentStatus.EVIDENCE_READY.value)
        db.add(doc)
        db.flush()
        ref = Reference(
            document_id=doc.id,
            reference_key="Smith_2023",
            raw_reference="Smith, J. (2023). AI Writing Assistants. https://doi.org/10.1234/demo",
            extracted_title=None if source_unavailable else "AI Writing Assistants",
            extracted_authors=None if source_unavailable else "Smith, J.",
            extracted_year=None if source_unavailable else 2023,
            extracted_doi=None if source_unavailable else "10.1234/demo",
            doi_status=DoiStatus.MISSING.value if source_unavailable else DoiStatus.VALID.value,
            metadata_status=MetadataStatus.LOOKUP_SUCCEEDED.value if with_metadata and not source_unavailable else MetadataStatus.NOT_LOOKED_UP.value,
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
        citation = Citation(document_id=doc.id, claim_id=claim.id, raw_citation="(Smith, 2023)", citation_style="APA", sentence_text=claim.source_paragraph, mapped_reference_id=ref.id)
        db.add(citation)
        db.flush()
        db.add(ClaimReferenceLink(document_id=doc.id, claim_id=claim.id, citation_id=citation.id, reference_id=ref.id, mapping_status=MappingStatus.MAPPED.value, mapping_confidence=0.95))
        if with_metadata and not source_unavailable:
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
                )
            )
        db.commit()
        prepared = EvidencePackageBuilder().prepare_evidence_for_document(doc.id, db)
        package = db.query(EvidencePackage).filter(EvidencePackage.document_id == doc.id).one()
        return doc.id, claim.id, ref.id, package.id, prepared


def test_request_builder_uses_evidence_package_contract_and_no_file_paths() -> None:
    _doc_id, claim_id, ref_id, package_id, _ = _create_claim_reference_with_package()
    with SessionLocal() as db:
        package = db.get(EvidencePackage, package_id)
        request_payload = RagRequestBuilder().build(package, top_k=3)
    assert request_payload["claim_id"] == claim_id
    assert request_payload["reference_id"] == ref_id
    assert request_payload["evidence_package_id"] == package_id
    assert request_payload["metadata"]["title"] == "AI Writing Assistants and Student Productivity"
    assert request_payload["source_evidence"]["evidence_availability"] == EvidenceAvailability.ABSTRACT_AVAILABLE.value
    assert request_payload["retrieval_options"]["top_k"] == 3
    assert "file_storage_path" not in str(request_payload)


def test_retrieve_evidence_api_success_with_mock_abstract_chunk() -> None:
    _doc_id, claim_id, ref_id, package_id, _ = _create_claim_reference_with_package()
    response = client.post(f"/api/v1/claims/{claim_id}/retrieve-evidence", json={"reference_id": ref_id, "evidence_package_id": package_id, "top_k": 5, "use_mock": True})
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    data = payload["data"]
    assert data["retrieval_status"] == RetrievalStatus.SUCCEEDED.value
    assert data["overall_similarity_score"] == 0.82
    assert data["retrieval_confidence"] == pytest.approx(0.79)
    assert data["top_chunks"][0]["evidence_type"] == "ABSTRACT"
    assert data["top_chunks"][0]["source"] == "metadata_abstract"
    with SessionLocal() as db:
        stored = db.query(RagRetrievalResult).filter(RagRetrievalResult.claim_id == claim_id).one()
        assert stored.evidence_package_id == package_id
        assert stored.response_payload_json["mock_mode"] is True


def test_retrieval_results_endpoint_returns_latest_result() -> None:
    _doc_id, claim_id, _ref_id, package_id, _ = _create_claim_reference_with_package()
    assert client.post(f"/api/v1/claims/{claim_id}/retrieve-evidence", json={"evidence_package_id": package_id, "use_mock": True}).status_code == 200
    response = client.get(f"/api/v1/claims/{claim_id}/retrieval-results")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["retrieval_results"][0]["retrieval_status"] == RetrievalStatus.SUCCEEDED.value


def test_metadata_only_package_returns_metadata_chunk() -> None:
    _doc_id, claim_id, _ref_id, package_id, _ = _create_claim_reference_with_package(abstract=None)
    response = client.post(f"/api/v1/claims/{claim_id}/retrieve-evidence", json={"evidence_package_id": package_id, "use_mock": True})
    assert response.status_code == 200
    chunk = response.json()["data"]["top_chunks"][0]
    assert chunk["evidence_type"] == "METADATA"
    assert "AI Writing Assistants" in chunk["chunk_text"]


def test_source_unavailable_package_skips_rag_call_and_stores_no_evidence_result() -> None:
    _doc_id, claim_id, _ref_id, package_id, prepared = _create_claim_reference_with_package(with_metadata=False, source_unavailable=True)
    assert prepared["source_unavailable"] == 1
    response = client.post(f"/api/v1/claims/{claim_id}/retrieve-evidence", json={"evidence_package_id": package_id, "use_mock": True})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["retrieval_status"] == RetrievalStatus.NO_RELEVANT_EVIDENCE_FOUND.value
    assert data["top_chunks"] == []
    with SessionLocal() as db:
        stored = db.query(RagRetrievalResult).filter(RagRetrievalResult.claim_id == claim_id).one()
        assert stored.error_message.startswith("Evidence package has SOURCE_UNAVAILABLE")


def test_missing_claim_and_missing_package_errors_use_standard_wrapper() -> None:
    missing = client.post("/api/v1/claims/claim_missing/retrieve-evidence", json={"use_mock": True})
    assert missing.status_code == 404
    assert missing.json()["errors"][0]["code"] == "CLAIM_NOT_FOUND"

    with SessionLocal() as db:
        doc = Document(filename="no-package.txt", title="No package", upload_type=UploadType.TEXT.value, status=DocumentStatus.CLAIMS_EXTRACTED.value)
        db.add(doc)
        db.flush()
        claim = Claim(document_id=doc.id, claim_text="A claim with no evidence package.", claim_type="UNKNOWN")
        db.add(claim)
        db.commit()
        claim_id = claim.id
    no_package = client.post(f"/api/v1/claims/{claim_id}/retrieve-evidence", json={"use_mock": True})
    assert no_package.status_code == 404
    assert no_package.json()["errors"][0]["code"] == "EVIDENCE_PACKAGE_NOT_FOUND"


def test_rag_response_validator_rejects_wrong_claim_id_and_bad_scores() -> None:
    validator = RagResponseValidator()
    with pytest.raises(ValueError, match="claim_id"):
        validator.validate({"claim_id": "other", "reference_id": "ref_1", "retrieval_status": "SUCCEEDED", "top_chunks": []}, claim_id="claim_1", reference_id="ref_1")
    with pytest.raises(ValueError, match="similarity_score"):
        validator.validate({"claim_id": "claim_1", "reference_id": "ref_1", "retrieval_status": "SUCCEEDED", "top_chunks": [{"chunk_text": "Bad", "similarity_score": 1.5}]}, claim_id="claim_1", reference_id="ref_1")
    with pytest.raises(ValueError, match="support_status"):
        validator.validate({"claim_id": "claim_1", "reference_id": "ref_1", "retrieval_status": "SUCCEEDED", "support_status": "SUPPORTED", "top_chunks": []}, claim_id="claim_1", reference_id="ref_1")


class InvalidRagClient:
    def retrieve(self, request_payload: dict, *, use_mock: bool | None = None) -> RagClientResult:
        return RagClientResult(payload={"claim_id": request_payload["claim_id"], "reference_id": "wrong", "retrieval_status": "SUCCEEDED", "top_chunks": []}, mock_mode=True)


class TimeoutRagClient:
    def retrieve(self, request_payload: dict, *, use_mock: bool | None = None) -> RagClientResult:
        raise AppException(status_code=504, code=ErrorCode.RAG_SERVICE_TIMEOUT, field="claim_id", detail="RAG evidence retrieval timed out.", message="RAG service timeout")


class SemanticRagClient:
    def retrieve(self, request_payload: dict, *, use_mock: bool | None = None) -> RagClientResult:
        return RagClientResult(
            payload={
                "claim_id": request_payload["claim_id"],
                "reference_id": request_payload["reference_id"],
                "retrieval_status": RetrievalStatus.SUCCEEDED.value,
                "top_chunks": [{"chunk_id": "chunk_1", "chunk_text": "Aligned evidence text.", "similarity_score": 0.91, "evidence_type": "ABSTRACT", "source": "mock"}],
                "overall_similarity_score": 0.91,
                "retrieval_confidence": 0.9,
                "semantic_cache_match": {"matched": True, "cached_result_id": "result_123", "similarity": 0.94},
            },
            mock_mode=True,
        )


def test_invalid_rag_response_is_not_stored_as_success_and_returns_error() -> None:
    _doc_id, claim_id, _ref_id, package_id, _ = _create_claim_reference_with_package()
    with SessionLocal() as db:
        service = RagRetrievalService(rag_client=InvalidRagClient())
        with pytest.raises(AppException) as exc:
            service.retrieve_evidence_for_claim(claim_id, db, evidence_package_id=package_id, use_mock=True)
        assert exc.value.error.code == "RAG_INVALID_RESPONSE"
        failures = db.query(RagRetrievalResult).filter(RagRetrievalResult.claim_id == claim_id).all()
        assert len(failures) == 1
        assert failures[0].retrieval_status == RetrievalStatus.FAILED.value


def test_timeout_is_stored_safely_as_timeout_result() -> None:
    _doc_id, claim_id, _ref_id, package_id, _ = _create_claim_reference_with_package()
    with SessionLocal() as db:
        service = RagRetrievalService(rag_client=TimeoutRagClient())
        with pytest.raises(AppException) as exc:
            service.retrieve_evidence_for_claim(claim_id, db, evidence_package_id=package_id, use_mock=False)
        assert exc.value.error.code == "RAG_SERVICE_TIMEOUT"
        stored = db.query(RagRetrievalResult).filter(RagRetrievalResult.claim_id == claim_id).one()
        assert stored.retrieval_status == RetrievalStatus.TIMEOUT.value
        assert "timed out" in stored.error_message


def test_semantic_cache_match_from_rag_is_validated_and_stored() -> None:
    _doc_id, claim_id, _ref_id, package_id, _ = _create_claim_reference_with_package()
    with SessionLocal() as db:
        result = RagRetrievalService(rag_client=SemanticRagClient()).retrieve_evidence_for_claim(claim_id, db, evidence_package_id=package_id, use_mock=True)
        assert result["semantic_cache_match"]["matched"] is True
        stored = db.query(RagRetrievalResult).filter(RagRetrievalResult.claim_id == claim_id).one()
        assert stored.semantic_cache_match_json["cached_result_id"] == "result_123"


def test_retrieval_repository_can_return_multiple_attempts_when_requested() -> None:
    _doc_id, claim_id, _ref_id, package_id, _ = _create_claim_reference_with_package()
    assert client.post(f"/api/v1/claims/{claim_id}/retrieve-evidence", json={"evidence_package_id": package_id, "use_mock": True}).status_code == 200
    assert client.post(f"/api/v1/claims/{claim_id}/retrieve-evidence", json={"evidence_package_id": package_id, "use_mock": True}).status_code == 200
    latest = client.get(f"/api/v1/claims/{claim_id}/retrieval-results?latest_only=true").json()["data"]
    all_attempts = client.get(f"/api/v1/claims/{claim_id}/retrieval-results?latest_only=false").json()["data"]
    assert latest["total"] == 1
    assert all_attempts["total"] == 2
