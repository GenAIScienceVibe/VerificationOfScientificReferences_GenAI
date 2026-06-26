
from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Claim,
    ClaimReferenceLink,
    Citation,
    Document,
    EvidencePackage,
    RagRetrievalResult,
    Reference,
    Report,
    SafetyCheck,
    SourceMetadata,
    UatSurvey,
    UserFeedback,
    VerificationResult,
)
from app.models.enums import (
    CacheSource,
    DocumentStatus,
    DoiStatus,
    EvidenceAvailability,
    MappingStatus,
    MetadataStatus,
    RetrievalStatus,
    SafetyRiskLevel,
    SupportStatus,
    UploadType,
)

client = TestClient(app)


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert payload["success"] is success
    assert "data" in payload
    assert isinstance(payload["errors"], list)
    assert payload["request_id"].startswith("req_")


def _seed_report_ready_document() -> dict[str, str]:
    with SessionLocal() as db:
        doc = Document(
            filename="be12.txt",
            title="BE12 Report Demo",
            upload_type=UploadType.TEXT.value,
            status=DocumentStatus.VERIFIED.value,
            cleaned_text="AI tools improve writing (Smith, 2023). Some claims need review (Lee, 2022).",
            references_count=3,
            claims_count=2,
        )
        db.add(doc)
        db.flush()

        ref_valid = Reference(
            document_id=doc.id,
            reference_key="Smith_2023",
            raw_reference="Smith, J. (2023). AI Writing Assistants. https://doi.org/10.1234/demo",
            extracted_title="AI Writing Assistants",
            extracted_authors="Smith, J.",
            extracted_year=2023,
            extracted_doi="10.1234/demo",
            doi_status=DoiStatus.VALID.value,
            metadata_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            metadata_match_score=0.92,
        )
        ref_missing = Reference(
            document_id=doc.id,
            reference_key="Lee_2022",
            raw_reference="Lee, A. (2022). Manual Source Without DOI.",
            extracted_title="Manual Source Without DOI",
            extracted_authors="Lee, A.",
            extracted_year=2022,
            extracted_doi=None,
            doi_status=DoiStatus.MISSING.value,
            metadata_status=MetadataStatus.METADATA_UNAVAILABLE.value,
        )
        ref_malformed = Reference(
            document_id=doc.id,
            reference_key="Bad_2021",
            raw_reference="Bad, B. (2021). Broken DOI. doi:10.bad",
            extracted_title="Broken DOI",
            extracted_authors="Bad, B.",
            extracted_year=2021,
            extracted_doi="10.bad",
            doi_status=DoiStatus.MALFORMED.value,
            metadata_status=MetadataStatus.LOOKUP_FAILED.value,
        )
        db.add_all([ref_valid, ref_missing, ref_malformed])
        db.flush()
        db.add(SourceMetadata(reference_id=ref_valid.id, doi="10.1234/demo", title="AI Writing Assistants", authors="Smith, J.", year=2023, venue="Journal of AI Education", publisher="Example Publisher", abstract="AI writing assistants reduced drafting time.", url="https://doi.org/10.1234/demo", lookup_source="crossref", lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value, metadata_match_score=0.92))

        claim_supported = Claim(
            document_id=doc.id,
            claim_text="AI tools improve academic writing productivity.",
            claim_type="EMPIRICAL",
            section_name="Introduction",
            source_paragraph="AI tools improve academic writing productivity (Smith, 2023).",
            paragraph_index=1,
            sentence_index=0,
            extraction_confidence=0.90,
        )
        claim_review = Claim(
            document_id=doc.id,
            claim_text="Some cited claims require manual source inspection.",
            claim_type="BACKGROUND",
            section_name="Discussion",
            source_paragraph="Some cited claims require manual source inspection (Lee, 2022).",
            paragraph_index=2,
            sentence_index=0,
            extraction_confidence=0.84,
        )
        db.add_all([claim_supported, claim_review])
        db.flush()

        cit1 = Citation(document_id=doc.id, claim_id=claim_supported.id, raw_citation="(Smith, 2023)", citation_style="APA", sentence_text=claim_supported.source_paragraph, mapped_reference_id=ref_valid.id, mapping_confidence=0.95)
        cit2 = Citation(document_id=doc.id, claim_id=claim_review.id, raw_citation="(Lee, 2022)", citation_style="APA", sentence_text=claim_review.source_paragraph, mapped_reference_id=ref_missing.id, mapping_confidence=0.88)
        db.add_all([cit1, cit2])
        db.flush()
        link1 = ClaimReferenceLink(document_id=doc.id, claim_id=claim_supported.id, citation_id=cit1.id, reference_id=ref_valid.id, mapping_status=MappingStatus.MAPPED.value, mapping_confidence=0.95)
        link2 = ClaimReferenceLink(document_id=doc.id, claim_id=claim_review.id, citation_id=cit2.id, reference_id=ref_missing.id, mapping_status=MappingStatus.MAPPED.value, mapping_confidence=0.88)
        db.add_all([link1, link2])
        db.flush()

        ep1 = EvidencePackage(
            document_id=doc.id,
            claim_id=claim_supported.id,
            reference_id=ref_valid.id,
            citation_id=cit1.id,
            link_id=link1.id,
            citation_text=cit1.raw_citation,
            doi="10.1234/demo",
            doi_status=DoiStatus.VALID.value,
            metadata_json={"title": "AI Writing Assistants", "authors": ["Smith, J."], "year": 2023},
            source_evidence_text="AI writing assistants reduced drafting time.",
            source_url="https://doi.org/10.1234/demo",
            evidence_availability=EvidenceAvailability.ABSTRACT_AVAILABLE.value,
            embedding_model_version="embedding-v1",
            prompt_version="verify-v1",
            verification_policy_version="policy-v1",
        )
        ep2 = EvidencePackage(
            document_id=doc.id,
            claim_id=claim_review.id,
            reference_id=ref_missing.id,
            citation_id=cit2.id,
            link_id=link2.id,
            citation_text=cit2.raw_citation,
            doi=None,
            doi_status=DoiStatus.MISSING.value,
            metadata_json={"title": "Manual Source Without DOI", "authors": ["Lee, A."], "year": 2022},
            source_evidence_text=None,
            evidence_availability=EvidenceAvailability.SOURCE_UNAVAILABLE.value,
            embedding_model_version="embedding-v1",
            prompt_version="verify-v1",
            verification_policy_version="policy-v1",
        )
        db.add_all([ep1, ep2])
        db.flush()

        retrieval = RagRetrievalResult(document_id=doc.id, claim_id=claim_supported.id, reference_id=ref_valid.id, evidence_package_id=ep1.id, retrieval_status=RetrievalStatus.SUCCEEDED.value, top_chunks_json=[{"chunk_id": "chunk_1", "chunk_text": "AI writing assistants reduced drafting time.", "similarity_score": 0.86}], overall_similarity_score=0.86, retrieval_confidence=0.84)
        db.add(retrieval)
        db.flush()

        result_supported = VerificationResult(
            document_id=doc.id,
            claim_id=claim_supported.id,
            reference_id=ref_valid.id,
            support_status=SupportStatus.PARTIALLY_SUPPORTED.value,
            confidence=0.70,
            explanation="The abstract supports drafting-time improvement, but not every productivity dimension.",
            limitations="Only abstract-level evidence was available.",
            human_review_required=False,
            evidence_used_json=["chunk_1"],
            evidence_availability=EvidenceAvailability.ABSTRACT_AVAILABLE.value,
            evidence_used_count=1,
            overall_similarity_score=0.86,
            verification_method="RAG_PLUS_GENAI",
            cache_source=CacheSource.NEW_VERIFICATION.value,
        )
        result_review = VerificationResult(
            document_id=doc.id,
            claim_id=claim_review.id,
            reference_id=ref_missing.id,
            support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
            confidence=0.35,
            explanation="The cited source lacks a DOI and source evidence.",
            limitations="Manual source inspection is required.",
            human_review_required=True,
            evidence_used_json=[],
            evidence_availability=EvidenceAvailability.SOURCE_UNAVAILABLE.value,
            evidence_used_count=0,
            overall_similarity_score=0.20,
            verification_method="FALLBACK_NEEDS_REVIEW",
            cache_source=CacheSource.NEW_VERIFICATION.value,
        )
        db.add_all([result_supported, result_review])
        db.flush()
        safety = SafetyCheck(verification_result_id=result_review.id, safety_status="NEEDS_REVIEW", risk_level=SafetyRiskLevel.HIGH.value, issue="Missing DOI requires human review.", recommended_action="Human reviewer should manually inspect the cited source.", backend_rule_triggered="DOI_MISSING")
        db.add(safety)
        db.commit()
        return {
            "document_id": doc.id,
            "result_id": result_supported.id,
            "review_result_id": result_review.id,
            "link_id": link1.id,
            "other_link_id": link2.id,
            "reference_id": ref_valid.id,
            "other_reference_id": ref_missing.id,
        }


def test_document_summary_counts_doi_verification_and_risk() -> None:
    ids = _seed_report_ready_document()
    response = client.get(f"/api/v1/documents/{ids['document_id']}/summary")
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    data = payload["data"]
    assert data["total_references"] == 3
    assert data["valid_dois"] == 1
    assert data["missing_dois"] == 1
    assert data["malformed_dois"] == 1
    assert data["verification_results"] == 2
    assert data["partially_supported"] == 1
    assert data["needs_human_review"] == 1
    assert data["high_risk_count"] == 1
    assert data["overall_risk_level"] == "HIGH"
    assert data["report_ready"] is True


def test_report_generation_and_retrieval_contains_required_sections() -> None:
    ids = _seed_report_ready_document()
    response = client.post(
        f"/api/v1/documents/{ids['document_id']}/reports",
        json={"format": "HTML", "include_evidence_chunks": True, "include_human_review_items": True, "include_limitations": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    report_id = payload["data"]["report_id"]

    with SessionLocal() as db:
        report = db.get(Report, report_id)
        assert report is not None
        assert report.status == "GENERATED"
        assert "Limitations" in report.html_content
        assert "High-risk / Human-review Claims" in report.html_content
        assert "HALLUCINATED" not in report.html_content

    detail = client.get(f"/api/v1/reports/{report_id}")
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert "DOI / Reference Quality Summary" in data["html_content"]
    assert "Claim Verification Summary" in data["html_content"]

    latest = client.get(f"/api/v1/documents/{ids['document_id']}/report")
    assert latest.status_code == 200
    assert latest.json()["data"]["report_id"] == report_id


def test_report_generation_before_verification_returns_controlled_error() -> None:
    with SessionLocal() as db:
        doc = Document(filename="empty.txt", title="No Verification", upload_type=UploadType.TEXT.value, status=DocumentStatus.TEXT_EXTRACTED.value, cleaned_text="No verification yet.")
        db.add(doc)
        db.commit()
        doc_id = doc.id
    response = client.post(f"/api/v1/documents/{doc_id}/reports", json={"format": "HTML"})
    assert response.status_code == 422
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "VERIFICATION_NOT_COMPLETED"


def test_report_pdf_export_is_controlled_not_supported() -> None:
    ids = _seed_report_ready_document()
    generated = client.post(f"/api/v1/documents/{ids['document_id']}/reports", json={"format": "HTML"})
    report_id = generated.json()["data"]["report_id"]
    response = client.get(f"/api/v1/reports/{report_id}/download?format=PDF")
    assert response.status_code == 422
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "REPORT_EXPORT_NOT_SUPPORTED"


def test_verification_result_feedback_is_stored_without_overwriting_result() -> None:
    ids = _seed_report_ready_document()
    response = client.post(
        f"/api/v1/verification-results/{ids['result_id']}/feedback",
        json={"user_label": "SUPPORTED", "user_comment": "Looks stronger to me.", "user_role": "research_assistant"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    with SessionLocal() as db:
        feedback = db.get(UserFeedback, payload["data"]["feedback_id"])
        result = db.get(VerificationResult, ids["result_id"])
        assert feedback.result_id == ids["result_id"]
        assert feedback.user_label == "SUPPORTED"
        assert result.support_status == SupportStatus.PARTIALLY_SUPPORTED.value


def test_verification_feedback_invalid_label_rejected() -> None:
    ids = _seed_report_ready_document()
    response = client.post(f"/api/v1/verification-results/{ids['result_id']}/feedback", json={"user_label": "TRUE"})
    assert response.status_code == 422
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "INVALID_FEEDBACK_LABEL"


def test_mapping_feedback_validates_suggested_reference_same_document() -> None:
    ids = _seed_report_ready_document()
    response = client.post(
        f"/api/v1/claim-reference-links/{ids['link_id']}/feedback",
        json={"feedback_type": "WRONG_MAPPING", "suggested_reference_id": ids["other_reference_id"], "comment": "Use the other source.", "user_role": "reviewer"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    with SessionLocal() as db:
        feedback = db.get(UserFeedback, payload["data"]["feedback_id"])
        link = db.get(ClaimReferenceLink, ids["link_id"])
        assert feedback.link_id == link.id
        assert feedback.document_id == link.document_id
        assert feedback.suggested_reference_id == ids["other_reference_id"]

    with SessionLocal() as db:
        foreign_doc = Document(filename="foreign.txt", title="Foreign", upload_type=UploadType.TEXT.value, status=DocumentStatus.TEXT_EXTRACTED.value, cleaned_text="x")
        db.add(foreign_doc)
        db.flush()
        foreign_ref = Reference(document_id=foreign_doc.id, reference_key="Foreign_2024", raw_reference="Foreign", extracted_title="Foreign", extracted_authors="F", extracted_year=2024, doi_status=DoiStatus.MISSING.value, metadata_status=MetadataStatus.NOT_LOOKED_UP.value)
        db.add(foreign_ref)
        db.commit()
        foreign_ref_id = foreign_ref.id
    bad = client.post(f"/api/v1/claim-reference-links/{ids['link_id']}/feedback", json={"feedback_type": "WRONG_MAPPING", "suggested_reference_id": foreign_ref_id})
    assert bad.status_code == 422
    assert bad.json()["errors"][0]["code"] == "REFERENCE_NOT_FOUND"


def test_uat_survey_stored_and_invalid_rating_rejected() -> None:
    ids = _seed_report_ready_document()
    response = client.post(
        "/api/v1/uat/surveys",
        json={
            "document_id": ids["document_id"],
            "participant_role": "student",
            "ease_of_use_rating": 4,
            "result_clarity_rating": 5,
            "trust_rating": 4,
            "usefulness_rating": 5,
            "comments": "Clear report.",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    with SessionLocal() as db:
        survey = db.get(UatSurvey, payload["data"]["survey_id"])
        assert survey.document_id == ids["document_id"]
        assert survey.ease_of_use_rating == 4

    invalid = client.post(
        "/api/v1/uat/surveys",
        json={
            "document_id": ids["document_id"],
            "participant_role": "student",
            "ease_of_use_rating": 6,
            "result_clarity_rating": 5,
            "trust_rating": 4,
            "usefulness_rating": 5,
        },
    )
    assert invalid.status_code == 422
    assert_wrapper(invalid.json(), success=False)
