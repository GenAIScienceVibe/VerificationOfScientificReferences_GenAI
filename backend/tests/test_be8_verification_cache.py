from __future__ import annotations

from datetime import UTC, datetime, timedelta

from testsupport.api_client import ApiTestClient as TestClient

from app.core.config import Settings
from app.db.session import SessionLocal
from app.main import app
from app.models import Claim, ClaimCacheIndex, ClaimReferenceLink, Citation, Document, EvidencePackage, Reference, VerificationResult
from app.models.enums import CacheSource, DocumentStatus, DoiStatus, EvidenceAvailability, MappingStatus, SupportStatus, UploadType
from app.services.verification_cache import VerificationCacheService, build_cache_key, normalize_claim_text, normalize_doi_for_cache

client = TestClient(app)


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert payload["success"] is success
    assert "data" in payload
    assert isinstance(payload["errors"], list)
    assert payload["request_id"].startswith("req_")


def _create_cache_ready_records(
    *,
    claim_text: str = "AI tools improve academic writing productivity.",
    doi: str | None = "10.1234/demo",
    support_status: str = SupportStatus.SUPPORTED.value,
    confidence: float | None = 0.91,
    index: bool = True,
    cache_source: str = CacheSource.NEW_VERIFICATION.value,
    created_at: datetime | None = None,
    policy_version: str = "policy-v1",
) -> tuple[str, str, str, str | None, str | None]:
    settings = Settings(VERIFICATION_POLICY_VERSION=policy_version)
    with SessionLocal() as db:
        doc = Document(filename="cache.txt", title="Cache Demo", upload_type=UploadType.TEXT.value, status=DocumentStatus.EVIDENCE_READY.value)
        db.add(doc)
        db.flush()
        ref = Reference(
            document_id=doc.id,
            reference_key="Smith_2023",
            raw_reference="Smith, J. (2023). AI Writing Assistants. https://doi.org/10.1234/demo",
            extracted_title="AI Writing Assistants",
            extracted_authors="Smith, J.",
            extracted_year=2023,
            extracted_doi=doi,
            doi_status=DoiStatus.VALID.value if doi else DoiStatus.MISSING.value,
        )
        claim = Claim(document_id=doc.id, claim_text=claim_text, claim_type="EMPIRICAL", section_name="Introduction")
        db.add_all([ref, claim])
        db.flush()
        citation = Citation(document_id=doc.id, claim_id=claim.id, raw_citation="(Smith, 2023)", citation_style="APA", mapped_reference_id=ref.id)
        db.add(citation)
        db.flush()
        link = ClaimReferenceLink(document_id=doc.id, claim_id=claim.id, citation_id=citation.id, reference_id=ref.id, mapping_status=MappingStatus.MAPPED.value, mapping_confidence=0.95)
        package = EvidencePackage(
            document_id=doc.id,
            claim_id=claim.id,
            reference_id=ref.id,
            citation_id=citation.id,
            link_id=link.id,
            citation_text="(Smith, 2023)",
            doi=doi,
            doi_status=DoiStatus.VALID.value if doi else DoiStatus.MISSING.value,
            metadata_json={"title": "AI Writing Assistants"},
            source_evidence_text="Metadata only.",
            source_url=f"https://doi.org/{doi}" if doi else None,
            evidence_availability=EvidenceAvailability.METADATA_ONLY.value,
            embedding_model_version="embedding-v1",
            prompt_version="verify-v1",
            verification_policy_version=policy_version,
        )
        result = VerificationResult(
            document_id=doc.id,
            claim_id=claim.id,
            reference_id=ref.id,
            support_status=support_status,
            confidence=confidence,
            explanation="Demo verification result for cache tests.",
            human_review_required=support_status == SupportStatus.NEEDS_HUMAN_REVIEW.value,
            evidence_availability=EvidenceAvailability.METADATA_ONLY.value,
            evidence_used_count=1,
            verification_method="DEMO_SEEDED_BE8_TEST_ONLY",
            cache_source=cache_source,
        )
        db.add_all([link, package, result])
        db.commit()
        db.refresh(result)
        cache = None
        if index and doi:
            service = VerificationCacheService(settings=settings)
            cache = service.index_verification_result(result.id, db, cache_source=cache_source)
            if created_at is not None:
                cache.created_at = created_at
                db.commit()
                db.refresh(cache)
        return doc.id, claim.id, ref.id, result.id, cache.id if cache else None


def test_claim_and_doi_normalization_preserve_meaning_critical_content() -> None:
    a = normalize_claim_text(" AI tools   improve productivity! ")
    b = normalize_claim_text("AI tools improve productivity")
    assert a == b
    assert build_cache_key("AI tools improve productivity.", "https://doi.org/10.1234/ABC.").normalized_doi == "10.1234/abc"
    assert normalize_doi_for_cache("DOI: 10.5555/Test.2024)") == "10.5555/test.2024"
    assert normalize_claim_text("AI tools do not improve scores by 20% in 2024") != normalize_claim_text("AI tools improve scores by 20% in 2024")
    assert "20%" in normalize_claim_text("AI tools improve scores by 20% in 2024")


def test_exact_cache_hit_same_claim_and_doi_api() -> None:
    _doc_id, claim_id, ref_id, result_id, cache_id = _create_cache_ready_records()
    response = client.post(f"/api/v1/claims/{claim_id}/check-cache", json={"reference_id": ref_id})
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    data = payload["data"]
    assert data["cache_hit"] is True
    assert data["cache_source"] == CacheSource.EXACT_CACHE.value
    assert data["recommended_action"] == "REUSE_VERIFICATION"
    assert data["matched_cache_id"] == cache_id
    assert data["matched_result_id"] == result_id
    assert data["similarity_score"] == 1.0


def test_same_claim_different_doi_is_not_reused() -> None:
    _doc_id, _claim_id, _ref_id, _result_id, _cache_id = _create_cache_ready_records(doi="10.1234/original")
    _doc2, claim2, ref2, _result2, _cache2 = _create_cache_ready_records(doi="10.1234/different", index=False)
    response = client.post(f"/api/v1/claims/{claim2}/check-cache", json={"reference_id": ref2})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["cache_hit"] is False
    assert data["cache_source"] == CacheSource.NEW_VERIFICATION.value
    assert data["recommended_action"] == "RUN_NEW_VERIFICATION"


def test_low_confidence_and_expired_cache_are_not_reused() -> None:
    _doc_id, claim_id, ref_id, _result_id, _cache_id = _create_cache_ready_records(confidence=0.55)
    low = client.post(f"/api/v1/claims/{claim_id}/check-cache", json={"reference_id": ref_id}).json()["data"]
    assert low["cache_hit"] is False or low["recommended_action"] != "REUSE_VERIFICATION"

    old_date = datetime.now(UTC) - timedelta(days=365)
    _doc2, claim2, ref2, _result2, _cache2 = _create_cache_ready_records(claim_text="AI assistants increase drafting speed.", created_at=old_date)
    expired = client.post(f"/api/v1/claims/{claim2}/check-cache", json={"reference_id": ref2}).json()["data"]
    assert expired["cache_hit"] is False or expired["recommended_action"] != "REUSE_VERIFICATION"


def test_human_review_cache_is_not_presented_as_confident_answer() -> None:
    _doc_id, claim_id, ref_id, _result_id, _cache_id = _create_cache_ready_records(support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value, confidence=0.95)
    data = client.post(f"/api/v1/claims/{claim_id}/check-cache", json={"reference_id": ref_id}).json()["data"]
    assert data["cache_hit"] is True
    assert data["recommended_action"] == "NEEDS_HUMAN_REVIEW"
    assert data["reusable"] is False


def test_policy_version_mismatch_returns_no_exact_cache_when_required() -> None:
    _doc_id, _claim_id, _ref_id, _result_id, _cache_id = _create_cache_ready_records(policy_version="old-policy")
    _doc2, claim2, ref2, _result2, _cache2 = _create_cache_ready_records(claim_text="AI feedback improves revision quality.", index=False)
    data = client.post(f"/api/v1/claims/{claim2}/check-cache", json={"reference_id": ref2}).json()["data"]
    assert data["cache_hit"] is False
    assert data["policy"]["verification_policy_version"] == "policy-v1"


def test_missing_claim_and_missing_doi_errors_or_safe_decisions() -> None:
    missing = client.post("/api/v1/claims/claim_missing/check-cache", json={})
    assert missing.status_code == 404
    assert missing.json()["errors"][0]["code"] == "CLAIM_NOT_FOUND"

    _doc_id, claim_id, ref_id, _result_id, _cache_id = _create_cache_ready_records(doi=None, index=False)
    data = client.post(f"/api/v1/claims/{claim_id}/check-cache", json={"reference_id": ref_id}).json()["data"]
    assert data["cache_hit"] is False
    assert data["recommended_action"] == "NEEDS_HUMAN_REVIEW"
    assert data["doi"] is None


def test_index_verification_result_is_idempotent() -> None:
    _doc_id, _claim_id, _ref_id, result_id, _cache_id = _create_cache_ready_records(index=False)
    with SessionLocal() as db:
        service = VerificationCacheService()
        first = service.index_verification_result(result_id, db)
        second = service.index_verification_result(result_id, db)
        assert first.id == second.id
        rows = db.query(ClaimCacheIndex).filter(ClaimCacheIndex.verification_result_id == result_id).all()
        assert len(rows) == 1
        assert rows[0].normalized_claim_hash
        assert rows[0].doi == "10.1234/demo"
        assert rows[0].support_status == SupportStatus.SUPPORTED.value


def test_cache_result_endpoint_computes_current_decision() -> None:
    _doc_id, claim_id, _ref_id, _result_id, _cache_id = _create_cache_ready_records()
    response = client.get(f"/api/v1/claims/{claim_id}/cache-result")
    assert response.status_code == 200
    assert_wrapper(response.json())
    assert response.json()["data"]["cache_source"] in {CacheSource.EXACT_CACHE.value, CacheSource.NEW_VERIFICATION.value}


def test_semantic_cache_mock_high_and_medium_similarity() -> None:
    _doc_id, _claim_id, _ref_id, _result_id, _cache_id = _create_cache_ready_records(claim_text="AI tools improve student writing productivity.")
    _doc2, claim2, ref2, _result2, _cache2 = _create_cache_ready_records(claim_text="AI tools improve writing productivity for students.", index=False)
    with SessionLocal() as db:
        settings = Settings(CACHE_SEMANTIC_ENABLED=True, CACHE_REQUIRE_SAME_REFERENCE=False)
        service = VerificationCacheService(settings=settings)
        high = service.check_claim_cache(claim2, db, reference_id=ref2, use_semantic_cache=True)
        assert high["cache_source"] in {CacheSource.SEMANTIC_CACHE.value, CacheSource.NEW_VERIFICATION.value}
        assert high["doi"] == "10.1234/demo"

    _doc3, claim3, ref3, _result3, _cache3 = _create_cache_ready_records(claim_text="Completely unrelated onboarding stress claim.", index=False)
    with SessionLocal() as db:
        settings = Settings(CACHE_SEMANTIC_ENABLED=True, CACHE_HIGH_SIMILARITY_THRESHOLD=0.99, CACHE_MEDIUM_SIMILARITY_THRESHOLD=0.1, CACHE_REQUIRE_SAME_REFERENCE=False)
        service = VerificationCacheService(settings=settings)
        medium = service.check_claim_cache(claim3, db, reference_id=ref3, use_semantic_cache=True)
        assert medium["recommended_action"] in {"RERUN_VERIFICATION", "RUN_NEW_VERIFICATION"}
