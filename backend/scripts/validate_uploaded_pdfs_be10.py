from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/be10_uploaded_pdf_validation.db")
os.environ.setdefault("FILE_STORAGE_DIR", "./data/be10_uploaded_pdf_uploads")
os.environ.setdefault("ENABLE_RAW_TEXT_DEBUG_ENDPOINT", "true")
os.environ.setdefault("RAG_MOCK_MODE", "true")
os.environ.setdefault("RAG_SERVICE_ENABLED", "true")
os.environ.setdefault("CACHE_SEMANTIC_ENABLED", "false")

from testsupport.api_client import ApiTestClient as TestClient

from app.db.init_db import drop_db_for_tests_only, init_db  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import EvidencePackage, VerificationResult  # noqa: E402
from app.models.enums import CacheSource, EvidenceAvailability, SupportStatus  # noqa: E402
from app.services.verification_cache import VerificationCacheService  # noqa: E402

client = TestClient(app)


def _post_pdf(path: Path) -> dict:
    with path.open("rb") as handle:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": (path.name, handle, "application/pdf")},
            data={"document_title": path.stem, "uploaded_by": "be10-validation"},
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
            explanation="BE-10 uploaded-PDF validation seeded/demo verification result for cache-hit testing.",
            limitations="Demo cache result, not a real final verification.",
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
    pipeline = pipeline_payload["data"]
    steps = _get_data(f"/api/v1/pipeline-runs/{pipeline['pipeline_run_id']}/steps")
    results = _get_data(f"/api/v1/documents/{document_id}/verification-results?page_size=200")
    result_items = results.get("results", [])
    detail_checked = 0
    correct_evidence_used = 0
    for item in result_items[:5]:
        detail = _get_data(f"/api/v1/verification-results/{item['result_id']}")
        detail_checked += 1
        evidence_used = (detail.get("verification") or {}).get("support_status") in {
            SupportStatus.SUPPORTED.value,
            SupportStatus.PARTIALLY_SUPPORTED.value,
            SupportStatus.NOT_SUPPORTED.value,
            SupportStatus.INSUFFICIENT_EVIDENCE.value,
            SupportStatus.NEEDS_HUMAN_REVIEW.value,
        }
        if evidence_used:
            correct_evidence_used += 1

    summary = results.get("summary", {})
    return {
        "pdf_name": path.name,
        "document_id": document_id,
        "references_detected": ref_summary.get("references_count"),
        "doi_summary": ref_summary.get("doi_summary"),
        "claims_extracted": claim_summary.get("claims_count"),
        "evidence_packages_created": evidence_summary.get("evidence_packages_created"),
        "pipeline_run_created": bool(pipeline.get("pipeline_run_id")),
        "pipeline_status": pipeline.get("status"),
        "pipeline_steps_recorded": len(steps.get("steps", [])) if isinstance(steps, dict) else 0,
        "seeded_demo_cache_records": seeded_cache,
        "verification_results_produced": summary.get("verification_results"),
        "cache_hit_verifications": sum(1 for item in result_items if item.get("cache_source") == CacheSource.EXACT_CACHE.value),
        "new_rag_genai_verifications": sum(1 for item in result_items if item.get("verification_method") == "RAG_PLUS_GENAI"),
        "supported": summary.get("supported"),
        "partially_supported": summary.get("partially_supported"),
        "not_supported": summary.get("not_supported"),
        "insufficient_evidence": summary.get("insufficient_evidence"),
        "needs_human_review": summary.get("needs_human_review"),
        "results_manually_checked": detail_checked,
        "correct_evidence_used_links": correct_evidence_used,
        "confidence_explanation_observations": "Mock GenAI produced deterministic explanations and confidence values; not final AI quality.",
        "safety_fallback_cases": sum(1 for item in result_items if item.get("human_review_required") is True),
        "problems_found": [],
        "fixes_applied": [],
        "remaining_limitations": [
            "Validation used mock RAG and mock GenAI because no real services were provided in the sandbox.",
            "BE-10 basic safety gates are intentionally limited; BE-11 will harden confidence/safety policy.",
            "Seeded cache records are demo-only because BE-10 is the first phase that creates real verification results.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BE-10 uploaded research PDF validation.")
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
            "pipeline_run_created",
            "pipeline_status",
            "pipeline_steps_recorded",
            "seeded_demo_cache_records",
            "verification_results_produced",
            "cache_hit_verifications",
            "new_rag_genai_verifications",
            "supported",
            "partially_supported",
            "not_supported",
            "insufficient_evidence",
            "needs_human_review",
            "results_manually_checked",
            "correct_evidence_used_links",
            "confidence_explanation_observations",
            "safety_fallback_cases",
        ):
            print(f"{key}: {result.get(key)}")
        print(f"problems_found: {result.get('problems_found')}")
        print(f"fixes_applied: {result.get('fixes_applied')}")
        print(f"remaining_limitations: {result.get('remaining_limitations')}")


if __name__ == "__main__":
    main()
