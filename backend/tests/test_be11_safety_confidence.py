from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import Claim, ClaimReferenceLink, Citation, Document, EvidencePackage, RagRetrievalResult, Reference, SafetyCheck, VerificationResult
from app.models.enums import CacheSource, DocumentStatus, DoiStatus, EvidenceAvailability, MappingStatus, MetadataStatus, RetrievalStatus, SupportStatus, UploadType
from app.services.safety_policy import SafetyPolicyService

client = TestClient(app)


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert payload["success"] is success
    assert "data" in payload
    assert isinstance(payload["errors"], list)
    assert payload["request_id"].startswith("req_")


def _seed_safety_case(
    *,
    doi_status: str = DoiStatus.VALID.value,
    metadata_status: str = MetadataStatus.LOOKUP_SUCCEEDED.value,
    evidence_availability: str = EvidenceAvailability.ABSTRACT_AVAILABLE.value,
    support_status: str = SupportStatus.SUPPORTED.value,
    confidence: float = 0.88,
    similarity: float | None = 0.86,
    evidence_used: list[str] | None = None,
    top_chunks: list[dict] | None = None,
    cache_source: str = CacheSource.NEW_VERIFICATION.value,
) -> tuple[str, str, str, str, str, str]:
    with SessionLocal() as db:
        doc = Document(
            filename="be11.txt",
            title="BE11 Safety Demo",
            upload_type=UploadType.TEXT.value,
            status=DocumentStatus.VERIFIED.value,
            cleaned_text="AI tools improve writing (Smith, 2023).",
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
            metadata_status=metadata_status,
        )
        claim = Claim(
            document_id=doc.id,
            claim_text="AI tools improve academic writing productivity.",
            claim_type="EMPIRICAL",
            section_name="Introduction",
            source_paragraph="AI tools improve academic writing productivity (Smith, 2023).",
            paragraph_index=1,
            sentence_index=0,
            extraction_confidence=0.9,
        )
        db.add_all([ref, claim])
        db.flush()
        citation = Citation(document_id=doc.id, claim_id=claim.id, raw_citation="(Smith, 2023)", citation_style="APA", sentence_text=claim.source_paragraph, mapped_reference_id=ref.id, mapping_confidence=0.95)
        db.add(citation)
        db.flush()
        db.add(ClaimReferenceLink(document_id=doc.id, claim_id=claim.id, citation_id=citation.id, reference_id=ref.id, mapping_status=MappingStatus.MAPPED.value, mapping_confidence=0.95))
        package = EvidencePackage(
            document_id=doc.id,
            claim_id=claim.id,
            reference_id=ref.id,
            citation_id=citation.id,
            citation_text=citation.raw_citation,
            doi=doi,
            doi_status=doi_status,
            metadata_json={"title": "AI Writing Assistants", "authors": ["Smith, J."], "year": 2023, "doi": doi},
            source_evidence_text="AI writing assistants reduced drafting time in a small study." if evidence_availability != EvidenceAvailability.SOURCE_UNAVAILABLE.value else None,
            source_url="https://doi.org/10.1234/demo" if doi else None,
            evidence_availability=evidence_availability,
            embedding_model_version="embedding-v1",
            prompt_version="verify-v1",
            verification_policy_version="policy-v1",
        )
        db.add(package)
        db.flush()
        chunks = top_chunks if top_chunks is not None else [{"chunk_id": "chunk_1", "chunk_text": "AI writing assistants reduced drafting time.", "similarity_score": similarity or 0.0}]
        retrieval = RagRetrievalResult(
            document_id=doc.id,
            claim_id=claim.id,
            reference_id=ref.id,
            evidence_package_id=package.id,
            retrieval_status=RetrievalStatus.SUCCEEDED.value,
            top_chunks_json=chunks,
            overall_similarity_score=similarity,
            retrieval_confidence=similarity,
        )
        db.add(retrieval)
        db.flush()
        result = VerificationResult(
            document_id=doc.id,
            claim_id=claim.id,
            reference_id=ref.id,
            support_status=support_status,
            confidence=confidence,
            explanation="Seeded result for BE-11 safety tests.",
            limitations="Before BE-11 safety evaluation.",
            human_review_required=False,
            evidence_used_json=evidence_used if evidence_used is not None else ["chunk_1"],
            evidence_availability=evidence_availability,
            evidence_used_count=len(evidence_used if evidence_used is not None else ["chunk_1"]),
            overall_similarity_score=similarity,
            verification_method="RAG_PLUS_GENAI",
            cache_source=cache_source,
        )
        db.add(result)
        db.commit()
        return doc.id, claim.id, ref.id, package.id, retrieval.id, result.id


def test_missing_doi_triggers_human_review_and_safety_check() -> None:
    *_ids, result_id = _seed_safety_case(doi_status=DoiStatus.MISSING.value, evidence_availability=EvidenceAvailability.METADATA_ONLY.value)
    with SessionLocal() as db:
        result = db.get(VerificationResult, result_id)
        decision = SafetyPolicyService().evaluate_and_apply(result, db)
        db.commit()
        assert decision.final_support_status == SupportStatus.NEEDS_HUMAN_REVIEW.value
        assert decision.final_confidence <= 0.50
        assert result.human_review_required is True
        checks = db.query(SafetyCheck).filter(SafetyCheck.verification_result_id == result_id).all()
        assert {item.backend_rule_triggered for item in checks} >= {"DOI_MISSING"}


def test_source_unavailable_becomes_insufficient_evidence_and_caps_confidence() -> None:
    *_ids, result_id = _seed_safety_case(evidence_availability=EvidenceAvailability.SOURCE_UNAVAILABLE.value, confidence=0.95, support_status=SupportStatus.SUPPORTED.value)
    with SessionLocal() as db:
        result = db.get(VerificationResult, result_id)
        decision = SafetyPolicyService().evaluate_and_apply(result, db)
        db.commit()
        assert decision.final_support_status == SupportStatus.INSUFFICIENT_EVIDENCE.value
        assert result.confidence <= 0.40
        assert result.human_review_required is True
        assert "SOURCE_UNAVAILABLE" in decision.rules_triggered


def test_metadata_only_supported_is_not_left_as_confident_supported() -> None:
    *_ids, result_id = _seed_safety_case(evidence_availability=EvidenceAvailability.METADATA_ONLY.value, confidence=0.93, support_status=SupportStatus.SUPPORTED.value)
    with SessionLocal() as db:
        result = db.get(VerificationResult, result_id)
        decision = SafetyPolicyService().evaluate_and_apply(result, db)
        db.commit()
        assert result.support_status == SupportStatus.NEEDS_HUMAN_REVIEW.value
        assert result.confidence <= 0.70
        assert "METADATA_ONLY_SUPPORTED" in decision.rules_triggered


def test_low_similarity_supported_result_is_overridden_and_capped() -> None:
    *_ids, result_id = _seed_safety_case(similarity=0.42, confidence=0.90, support_status=SupportStatus.SUPPORTED.value)
    with SessionLocal() as db:
        result = db.get(VerificationResult, result_id)
        decision = SafetyPolicyService().evaluate_and_apply(result, db)
        db.commit()
        assert result.support_status == SupportStatus.NEEDS_HUMAN_REVIEW.value
        assert result.confidence <= 0.55
        assert {"LOW_SIMILARITY", "GENAI_SUPPORTED_BUT_WEAK_EVIDENCE"} & set(decision.rules_triggered)


def test_low_genai_confidence_triggers_review_without_increasing_confidence() -> None:
    *_ids, result_id = _seed_safety_case(similarity=0.88, confidence=0.44, support_status=SupportStatus.PARTIALLY_SUPPORTED.value)
    with SessionLocal() as db:
        result = db.get(VerificationResult, result_id)
        before = result.confidence
        decision = SafetyPolicyService().evaluate_and_apply(result, db)
        db.commit()
        assert result.support_status == SupportStatus.NEEDS_HUMAN_REVIEW.value
        assert result.confidence <= before
        assert "LOW_GENAI_CONFIDENCE" in decision.rules_triggered


def test_evidence_used_mismatch_triggers_review() -> None:
    *_ids, result_id = _seed_safety_case(evidence_used=["invented_chunk"], confidence=0.82, support_status=SupportStatus.SUPPORTED.value)
    with SessionLocal() as db:
        result = db.get(VerificationResult, result_id)
        decision = SafetyPolicyService().evaluate_and_apply(result, db)
        db.commit()
        assert result.support_status == SupportStatus.NEEDS_HUMAN_REVIEW.value
        assert "EVIDENCE_USED_MISMATCH" in decision.rules_triggered


def test_safety_endpoints_expose_checks_and_summary() -> None:
    doc_id, *_rest, result_id = _seed_safety_case(similarity=0.40, confidence=0.95, support_status=SupportStatus.SUPPORTED.value)
    with SessionLocal() as db:
        SafetyPolicyService().evaluate_and_apply(db.get(VerificationResult, result_id), db)
        db.commit()
    detail = client.get(f"/api/v1/verification-results/{result_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert_wrapper(detail_payload)
    assert detail_payload["data"]["human_review_required"] is True
    assert detail_payload["data"]["safety_risk_level"] == "HIGH"
    assert detail_payload["data"]["safety_checks"]

    checks = client.get(f"/api/v1/verification-results/{result_id}/safety-checks")
    assert checks.status_code == 200
    assert_wrapper(checks.json())
    assert checks.json()["data"]["checks"]

    summary = client.get(f"/api/v1/documents/{doc_id}/safety-summary")
    assert summary.status_code == 200
    data = summary.json()["data"]
    assert data["total_results"] == 1
    assert data["high_risk"] == 1
    assert data["human_review_required"] == 1
