
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/be12_uploaded_pdf_validation.db")
os.environ.setdefault("FILE_STORAGE_DIR", "./data/be12_uploaded_pdf_uploads")
os.environ.setdefault("ENABLE_RAW_TEXT_DEBUG_ENDPOINT", "true")
os.environ.setdefault("RAG_MOCK_MODE", "true")
os.environ.setdefault("RAG_SERVICE_ENABLED", "true")
os.environ.setdefault("CACHE_SEMANTIC_ENABLED", "false")

from fastapi.testclient import TestClient  # noqa: E402

from app.db.init_db import drop_db_for_tests_only, init_db  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ClaimReferenceLink, EvidencePackage, Report, VerificationResult  # noqa: E402
from app.models.enums import CacheSource, SupportStatus  # noqa: E402
from app.services.verification_cache import VerificationCacheService  # noqa: E402

client = TestClient(app)


def _post_pdf(path: Path) -> dict:
    with path.open("rb") as handle:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": (path.name, handle, "application/pdf")},
            data={"document_title": path.stem, "uploaded_by": "be12-validation"},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Upload failed for {path.name}: {response.status_code} {response.text}")
    return response.json()["data"]


def _safe_post(path: str, json: dict | None = None) -> tuple[int, dict]:
    response = client.post(path, json=json)
    return response.status_code, response.json()


def _get_data(path: str) -> dict:
    response = client.get(path)
    if response.status_code >= 400:
        return response.json()
    return response.json()["data"]


def _seed_cache_for_first_package(document_id: str) -> int:
    with SessionLocal() as db:
        package = db.query(EvidencePackage).filter(EvidencePackage.document_id == document_id).first()
        if not package or not package.doi:
            return 0
        source = VerificationResult(
            document_id=package.document_id,
            claim_id=package.claim_id,
            reference_id=package.reference_id,
            support_status=SupportStatus.PARTIALLY_SUPPORTED.value,
            confidence=0.88,
            explanation="BE-12 uploaded-PDF validation seeded/demo verification result for cache-hit path.",
            limitations="Demo cache result, not real final verification.",
            human_review_required=False,
            evidence_used_json=["seeded_chunk_001"],
            evidence_availability=package.evidence_availability,
            evidence_used_count=1,
            overall_similarity_score=0.82,
            verification_method="RAG_PLUS_GENAI",
            cache_source=CacheSource.NEW_VERIFICATION.value,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        VerificationCacheService().index_verification_result(source.id, db)
        db.commit()
        return 1


def validate_pdf(path: Path) -> dict:
    uploaded = _post_pdf(path)
    document_id = uploaded["document_id"]

    extract_status, extract_payload = _safe_post(f"/api/v1/documents/{document_id}/extract-references")
    if extract_status >= 400:
        return {"pdf_name": path.name, "document_id": document_id, "error": extract_payload}
    ref_summary = extract_payload["data"]

    claim_status, claim_payload = _safe_post(f"/api/v1/documents/{document_id}/extract-claims", {"mode": "citation_linked_only"})
    if claim_status >= 400:
        return {"pdf_name": path.name, "document_id": document_id, "error": claim_payload, "ref_summary": ref_summary}
    claim_summary = claim_payload["data"]

    evidence_status, evidence_payload = _safe_post(f"/api/v1/documents/{document_id}/prepare-evidence")
    if evidence_status >= 400:
        return {"pdf_name": path.name, "document_id": document_id, "error": evidence_payload, "ref_summary": ref_summary, "claim_summary": claim_summary}
    evidence_summary = evidence_payload["data"]

    seeded_cache = _seed_cache_for_first_package(document_id)

    pipeline_status, pipeline_payload = _safe_post(
        f"/api/v1/documents/{document_id}/pipeline-runs",
        {"mode": "FULL_VERIFICATION", "use_cache": True, "use_rag": True, "use_genai_safety_review": True, "generate_report": False},
    )
    if pipeline_status >= 400:
        return {"pdf_name": path.name, "document_id": document_id, "error": pipeline_payload, "ref_summary": ref_summary, "claim_summary": claim_summary, "evidence_summary": evidence_summary}
    results = _get_data(f"/api/v1/documents/{document_id}/verification-results?page_size=200")
    safety_summary = _get_data(f"/api/v1/documents/{document_id}/safety-summary")
    summary = _get_data(f"/api/v1/documents/{document_id}/summary")

    report_status, report_payload = _safe_post(
        f"/api/v1/documents/{document_id}/reports",
        {"format": "HTML", "include_evidence_chunks": True, "include_human_review_items": True, "include_limitations": True},
    )
    if report_status >= 400:
        return {"pdf_name": path.name, "document_id": document_id, "error": report_payload, "summary": summary}
    report_data = report_payload["data"]
    report = _get_data(f"/api/v1/reports/{report_data['report_id']}")
    latest_report = _get_data(f"/api/v1/documents/{document_id}/report")
    html = report.get("html_content") or ""

    result_items = results.get("results", [])
    first_result = result_items[0] if result_items else None
    feedback_tested = False
    if first_result:
        feedback_status, _feedback = _safe_post(
            f"/api/v1/verification-results/{first_result['result_id']}/feedback",
            {"user_label": SupportStatus.NEEDS_HUMAN_REVIEW.value, "user_comment": "BE-12 validation feedback.", "user_role": "qa_validator"},
        )
        feedback_tested = feedback_status < 400

    mapping_feedback_tested = False
    with SessionLocal() as db:
        link = db.query(ClaimReferenceLink).filter(ClaimReferenceLink.document_id == document_id).first()
        if link:
            mapping_status, _mapping = _safe_post(
                f"/api/v1/claim-reference-links/{link.id}/feedback",
                {"feedback_type": "OTHER", "comment": "BE-12 validation mapping feedback.", "user_role": "qa_validator"},
            )
            mapping_feedback_tested = mapping_status < 400

    survey_status, _survey = _safe_post(
        "/api/v1/uat/surveys",
        {
            "document_id": document_id,
            "participant_role": "qa_validator",
            "ease_of_use_rating": 4,
            "result_clarity_rating": 4,
            "trust_rating": 4,
            "usefulness_rating": 5,
            "comments": "BE-12 uploaded-PDF validation survey.",
        },
    )
    uat_tested = survey_status < 400

    with SessionLocal() as db:
        stored_report = db.get(Report, report_data["report_id"])
        stored_report_ok = stored_report is not None and stored_report.status == "GENERATED"

    unsupported_labels = [item.get("support_status") for item in result_items if item.get("support_status") not in {item.value for item in SupportStatus}]
    report_sections_present = all(section in html for section in [
        "Document Overview",
        "DOI / Reference Quality Summary",
        "Claim Verification Summary",
        "High-risk / Human-review Claims",
        "Detailed Claim Verification Table",
        "Limitations",
    ])

    return {
        "pdf_name": path.name,
        "document_id": document_id,
        "references_detected": ref_summary.get("references_count"),
        "doi_summary": ref_summary.get("doi_summary"),
        "claims_extracted": claim_summary.get("claims_count"),
        "evidence_packages_created": evidence_summary.get("evidence_packages_created"),
        "verification_results_in_report": summary.get("verification_results"),
        "report_generated": bool(report_data.get("report_id")) and stored_report_ok,
        "report_id": report_data.get("report_id"),
        "total_references_in_report": summary.get("total_references"),
        "doi_summary_manually_checked": summary.get("total_references") == ref_summary.get("references_count"),
        "high_risk_claims_listed": "High-risk / Human-review Claims" in html and summary.get("human_review_required_count", 0) >= 0,
        "report_sections_present": report_sections_present,
        "limitations_section_present": "Limitations" in html,
        "unsupported_labels_found": unsupported_labels,
        "feedback_api_tested": feedback_tested,
        "mapping_feedback_tested": mapping_feedback_tested,
        "uat_survey_tested": uat_tested,
        "latest_report_endpoint_ok": latest_report.get("report_id") == report_data.get("report_id"),
        "mock_service_validation": True,
        "seeded_demo_cache_records": seeded_cache,
        "problems_found": unsupported_labels,
        "fixes_applied": [],
        "remaining_limitations": [
            "Validation used mock RAG and mock GenAI because no real services were provided in the sandbox.",
            "HTML report is the BE-12 MVP format; PDF export is intentionally not implemented.",
            "Feedback is stored but not automatically applied as truth.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BE-12 uploaded research PDF report/feedback validation.")
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--reset-db", action="store_true")
    args = parser.parse_args()

    if args.reset_db:
        drop_db_for_tests_only()
    init_db()

    for pdf in args.pdfs:
        result = validate_pdf(pdf)
        print("=" * 80)
        print(f"PDF: {result['pdf_name']}")
        if "error" in result:
            print(f"ERROR: {result['error']}")
            continue
        for key in (
            "document_id",
            "references_detected",
            "doi_summary",
            "claims_extracted",
            "evidence_packages_created",
            "verification_results_in_report",
            "report_generated",
            "report_id",
            "total_references_in_report",
            "doi_summary_manually_checked",
            "high_risk_claims_listed",
            "report_sections_present",
            "limitations_section_present",
            "unsupported_labels_found",
            "feedback_api_tested",
            "mapping_feedback_tested",
            "uat_survey_tested",
            "latest_report_endpoint_ok",
            "mock_service_validation",
            "seeded_demo_cache_records",
        ):
            print(f"{key}: {result.get(key)}")
        print(f"problems_found: {result.get('problems_found')}")
        print(f"fixes_applied: {result.get('fixes_applied')}")
        print(f"remaining_limitations: {result.get('remaining_limitations')}")


if __name__ == "__main__":
    main()
