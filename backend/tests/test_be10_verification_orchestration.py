from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.main import app
from app.models import Citation, Claim, ClaimReferenceLink, Document, EvidencePackage, Reference, SafetyCheck, SourceMetadata, VerificationResult
from app.models.enums import CacheSource, DocumentStatus, DoiStatus, EvidenceAvailability, MappingStatus, MetadataStatus, SupportStatus, UploadType
from app.services.evidence_package_builder import EvidencePackageBuilder
from app.services.genai_verification import GenAiVerificationResponseValidator
from app.services.verification_cache import VerificationCacheService

client = TestClient(app)


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert payload["success"] is success
    assert "data" in payload
    assert isinstance(payload["errors"], list)
    assert payload["request_id"].startswith("req_")


def _create_be10_document(*, doi_status: str = DoiStatus.VALID.value, abstract: str | None = "AI assistants reduced drafting time in the study.") -> tuple[str, str, str, str]:
    with SessionLocal() as db:
        doc = Document(
            filename="be10.txt",
            title="BE10 Demo",
            upload_type=UploadType.TEXT.value,
            status=DocumentStatus.EVIDENCE_READY.value,
            cleaned_text="Introduction\nAI tools improve academic writing productivity (Smith, 2023).\n\nReferences\nSmith, J. (2023). AI Writing Assistants. https://doi.org/10.1234/demo",
            references_count=1,
            claims_count=1,
        )
        db.add(doc)
        db.flush()
        doi = "10.1234/demo" if doi_status != DoiStatus.MISSING.value else None
        ref = Reference(
            document_id=doc.id,
            reference_key="Smith_2023",
            raw_reference="Smith, J. (2023). AI Writing Assistants. https://doi.org/10.1234/demo",
            extracted_title="AI Writing Assistants",
            extracted_authors="Smith, J.",
            extracted_year=2023,
            extracted_doi=doi,
            doi_status=doi_status,
            metadata_status=MetadataStatus.LOOKUP_SUCCEEDED.value if abstract else MetadataStatus.NOT_LOOKED_UP.value,
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
        citation = Citation(document_id=doc.id, claim_id=claim.id, raw_citation="(Smith, 2023)", citation_style="APA", sentence_text=claim.source_paragraph, mapped_reference_id=ref.id, mapping_confidence=0.95)
        db.add(citation)
        db.flush()
        db.add(ClaimReferenceLink(document_id=doc.id, claim_id=claim.id, citation_id=citation.id, reference_id=ref.id, mapping_status=MappingStatus.MAPPED.value, mapping_confidence=0.95))
        if abstract:
            db.add(
                SourceMetadata(
                    reference_id=ref.id,
                    doi=doi,
                    title="AI Writing Assistants and Student Productivity",
                    authors="Smith, J.",
                    year=2023,
                    venue="Journal of AI Education",
                    publisher="Example Publisher",
                    abstract=abstract,
                    url="https://doi.org/10.1234/demo" if doi else None,
                    lookup_source="crossref",
                    lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
                )
            )
        db.commit()
        EvidencePackageBuilder().prepare_evidence_for_document(doc.id, db)
        package = db.query(EvidencePackage).filter(EvidencePackage.document_id == doc.id).one()
        return doc.id, claim.id, ref.id, package.id


def test_pipeline_run_happy_path_creates_verification_result_and_steps() -> None:
    doc_id, claim_id, ref_id, _package_id = _create_be10_document()
    response = client.post(f"/api/v1/documents/{doc_id}/pipeline-runs", json={"mode": "FULL_VERIFICATION", "use_cache": True, "use_rag": True, "generate_report": False})
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    run = payload["data"]
    assert run["document_id"] == doc_id
    assert run["status"] in {"SUCCEEDED", "PARTIAL_FAILED"}
    assert run["progress_percentage"] == 100

    results = client.get(f"/api/v1/documents/{doc_id}/verification-results").json()["data"]
    assert results["summary"]["verification_results"] == 1
    result = results["results"][0]
    assert result["claim_id"] == claim_id
    assert result["reference_id"] == ref_id
    assert result["support_status"] in {SupportStatus.PARTIALLY_SUPPORTED.value, SupportStatus.NEEDS_HUMAN_REVIEW.value, SupportStatus.INSUFFICIENT_EVIDENCE.value}
    assert result["verification_method"] == "RAG_PLUS_GENAI"
    assert result["cache_source"] == CacheSource.NEW_VERIFICATION.value

    steps = client.get(f"/api/v1/pipeline-runs/{run['pipeline_run_id']}/steps")
    assert steps.status_code == 200
    step_names = {item["step_name"] for item in steps.json()["data"]["steps"]}
    assert {"CACHE_CHECK", "RAG_RETRIEVAL", "GENAI_VERIFICATION", "BASIC_SAFETY_CHECK", "RESULT_STORAGE"}.issubset(step_names)


def test_compatibility_run_verification_endpoint_and_single_result_details() -> None:
    doc_id, _claim_id, _ref_id, _package_id = _create_be10_document()
    run_response = client.post(f"/api/v1/documents/{doc_id}/run-verification", json={"use_cache": False, "use_rag": True})
    assert run_response.status_code == 200
    results = client.get(f"/api/v1/documents/{doc_id}/verification-results").json()["data"]["results"]
    detail_response = client.get(f"/api/v1/verification-results/{results[0]['result_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["verification"]["support_status"] == detail["support_status"]
    assert "retrieved_evidence" in detail


def test_exact_cache_hit_skips_new_rag_genai_and_creates_cache_only_result() -> None:
    doc_id, claim_id, ref_id, _package_id = _create_be10_document()
    with SessionLocal() as db:
        source = VerificationResult(
            document_id=doc_id,
            claim_id=claim_id,
            reference_id=ref_id,
            support_status=SupportStatus.SUPPORTED.value,
            confidence=0.91,
            explanation="Seeded cached result for BE-10 cache-hit test.",
            limitations="Demo cache result.",
            human_review_required=False,
            evidence_used_json=["cached_chunk_1"],
            evidence_availability=EvidenceAvailability.ABSTRACT_AVAILABLE.value,
            evidence_used_count=1,
            overall_similarity_score=0.89,
            verification_method="RAG_PLUS_GENAI",
            cache_source=CacheSource.NEW_VERIFICATION.value,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        VerificationCacheService().index_verification_result(source.id, db)
        db.commit()
    run_response = client.post(f"/api/v1/documents/{doc_id}/pipeline-runs", json={"use_cache": True, "use_rag": True})
    assert run_response.status_code == 200
    results = client.get(f"/api/v1/documents/{doc_id}/verification-results?cache_source=EXACT_CACHE").json()["data"]["results"]
    assert len(results) == 1
    assert results[0]["verification_method"] == "CACHE_ONLY"
    assert results[0]["cache_source"] == CacheSource.EXACT_CACHE.value
    assert "Reused cached verification result" in results[0]["explanation"]


def test_missing_doi_triggers_safety_fallback_and_human_review() -> None:
    doc_id, claim_id, _ref_id, _package_id = _create_be10_document(doi_status=DoiStatus.MISSING.value, abstract=None)
    response = client.post(f"/api/v1/documents/{doc_id}/pipeline-runs", json={"use_cache": True, "use_rag": True})
    assert response.status_code == 200
    results = client.get(f"/api/v1/documents/{doc_id}/verification-results").json()["data"]["results"]
    assert results[0]["claim_id"] == claim_id
    assert results[0]["support_status"] == SupportStatus.NEEDS_HUMAN_REVIEW.value
    assert results[0]["human_review_required"] is True
    assert results[0]["verification_method"] == "FALLBACK_NEEDS_REVIEW"
    with SessionLocal() as db:
        safety = db.query(SafetyCheck).one()
        assert safety.backend_rule_triggered in {"DOI_NOT_VALID", "SOURCE_UNAVAILABLE"}


def test_missing_document_pipeline_error_uses_standard_wrapper() -> None:
    response = client.post("/api/v1/documents/doc_missing/pipeline-runs", json={"use_cache": True})
    assert response.status_code == 404
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "DOCUMENT_NOT_FOUND"


def test_genai_validator_rejects_unknown_chunk_and_bad_status() -> None:
    validator = GenAiVerificationResponseValidator()
    chunks = [{"chunk_id": "chunk_1", "chunk_text": "Evidence", "similarity_score": 0.8}]
    good = validator.validate(
        {"support_status": "SUPPORTED", "confidence": 0.8, "explanation": "OK", "evidence_used": ["chunk_1"], "limitations": "None", "human_review_required": False},
        retrieved_chunks=chunks,
    )
    assert good["support_status"] == "SUPPORTED"
    import pytest

    with pytest.raises(ValueError, match="Unsupported support_status"):
        validator.validate({"support_status": "HALLUCINATED", "confidence": 0.8, "explanation": "bad", "evidence_used": [], "human_review_required": False}, retrieved_chunks=chunks)
    with pytest.raises(ValueError, match="unknown chunk_id"):
        validator.validate({"support_status": "SUPPORTED", "confidence": 0.8, "explanation": "bad", "evidence_used": ["invented"], "human_review_required": False}, retrieved_chunks=chunks)
