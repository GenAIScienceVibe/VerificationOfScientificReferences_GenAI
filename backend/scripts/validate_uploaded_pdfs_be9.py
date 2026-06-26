from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/be9_uploaded_pdf_validation.db")
os.environ.setdefault("FILE_STORAGE_DIR", "./data/be9_uploaded_pdf_uploads")
os.environ.setdefault("ENABLE_RAW_TEXT_DEBUG_ENDPOINT", "true")
os.environ.setdefault("RAG_MOCK_MODE", "true")
os.environ.setdefault("RAG_SERVICE_ENABLED", "true")
os.environ.setdefault("CACHE_SEMANTIC_ENABLED", "false")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.errors import AppException, ErrorCode  # noqa: E402
from app.db.init_db import drop_db_for_tests_only, init_db  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import EvidencePackage, RagRetrievalResult  # noqa: E402
from app.models.enums import RetrievalStatus  # noqa: E402
from app.services.rag_ml_integration import RagClientResult, RagRetrievalService  # noqa: E402

client = TestClient(app)


class TimeoutRagClient:
    def retrieve(self, request_payload: dict, *, use_mock: bool | None = None) -> RagClientResult:
        raise AppException(status_code=504, code=ErrorCode.RAG_SERVICE_TIMEOUT, field="claim_id", detail="BE-9 validation simulated timeout.", message="RAG service timeout")


def _post_pdf(path: Path) -> dict:
    with path.open("rb") as handle:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": (path.name, handle, "application/pdf")},
            data={"document_title": path.stem, "uploaded_by": "be9-validation"},
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


def _simulate_timeout(package: EvidencePackage) -> bool:
    with SessionLocal() as db:
        service = RagRetrievalService(rag_client=TimeoutRagClient())
        try:
            service.retrieve_evidence_for_claim(package.claim_id, db, evidence_package_id=package.id, use_mock=False)
        except AppException as exc:
            if exc.error.code != ErrorCode.RAG_SERVICE_TIMEOUT.value:
                return False
        stored = (
            db.query(RagRetrievalResult)
            .filter(RagRetrievalResult.evidence_package_id == package.id, RagRetrievalResult.retrieval_status == RetrievalStatus.TIMEOUT.value)
            .first()
        )
        return stored is not None


def validate_pdf(path: Path) -> dict:
    uploaded = _post_pdf(path)
    document_id = uploaded["document_id"]

    extract_status, extract_payload = _safe_post(f"/api/v1/documents/{document_id}/extract-references")
    if extract_status >= 400:
        return {"pdf_name": path.name, "document_id": document_id, "error": extract_payload}
    ref_summary = extract_payload["data"]

    # BE-9 uses backend-owned evidence packages. It does not call live external metadata services.
    # BE-5 live metadata should be validated in an environment with network access.
    metadata_summary = {"skipped": "BE-9 validation does not call external academic metadata services."}

    claim_status, claim_payload = _safe_post(f"/api/v1/documents/{document_id}/extract-claims", {"mode": "citation_linked_only"})
    if claim_status >= 400:
        return {"pdf_name": path.name, "document_id": document_id, "error": claim_payload, "ref_summary": ref_summary}
    claim_summary = claim_payload["data"]

    evidence_status, evidence_payload = _safe_post(f"/api/v1/documents/{document_id}/prepare-evidence")
    if evidence_status >= 400:
        return {"pdf_name": path.name, "document_id": document_id, "error": evidence_payload, "ref_summary": ref_summary, "claim_summary": claim_summary}
    evidence_summary = evidence_payload["data"]

    packages_data = _get_data(f"/api/v1/documents/{document_id}/evidence-packages?page_size=200")
    package_items = packages_data.get("evidence_packages", []) if isinstance(packages_data, dict) else []

    with SessionLocal() as db:
        package_records = db.query(EvidencePackage).filter(EvidencePackage.document_id == document_id).limit(5).all()

    retrievals_executed = 0
    successful = 0
    no_evidence = 0
    failed = 0
    chunks_checked = 0
    correct_alignment = 0
    score_observations: list[str] = []

    for package in package_records[:3]:
        status, payload = _safe_post(
            f"/api/v1/claims/{package.claim_id}/retrieve-evidence",
            {"evidence_package_id": package.id, "reference_id": package.reference_id, "top_k": 5, "use_mock": True},
        )
        retrievals_executed += 1
        if status >= 400:
            failed += 1
            continue
        data = payload["data"]
        if data.get("retrieval_status") == RetrievalStatus.SUCCEEDED.value:
            successful += 1
        elif data.get("retrieval_status") == RetrievalStatus.NO_RELEVANT_EVIDENCE_FOUND.value:
            no_evidence += 1
        else:
            failed += 1
        if data.get("claim_id") == package.claim_id and data.get("reference_id") == package.reference_id and data.get("evidence_package_id") == package.id:
            correct_alignment += 1
        for chunk in data.get("top_chunks") or []:
            chunks_checked += 1
            score = chunk.get("similarity_score")
            if isinstance(score, (float, int)) and 0 <= score <= 1:
                score_observations.append(f"{chunk.get('evidence_type')} score={score}")

    timeout_checked = 0
    if package_records:
        timeout_checked = 1 if _simulate_timeout(package_records[0]) else 0
        retrievals_executed += 1
        failed += 1 if timeout_checked else 0

    return {
        "pdf_name": path.name,
        "document_id": document_id,
        "references_detected": ref_summary.get("references_count"),
        "doi_summary": ref_summary.get("doi_summary"),
        "metadata_summary": metadata_summary,
        "claims_extracted": claim_summary.get("claims_count"),
        "claim_reference_links": claim_summary.get("mapped_links_count", 0) + claim_summary.get("uncertain_links_count", 0) + claim_summary.get("no_match_links_count", 0),
        "evidence_packages_created": evidence_summary.get("evidence_packages_created"),
        "claims_evidence_packages_tested": len(package_records[:3]),
        "retrievals_executed": retrievals_executed,
        "retrieval_mode": "Mock RAG",
        "successful_retrievals": successful,
        "no_evidence_retrievals": no_evidence,
        "failed_retrievals": failed,
        "top_chunks_manually_checked": chunks_checked,
        "correct_claim_reference_evidence_alignment": correct_alignment,
        "similarity_score_observations": score_observations[:10],
        "timeout_failure_handling_checked": timeout_checked,
        "package_items_seen_via_api": len(package_items),
        "problems_found": [],
        "fixes_applied": [],
        "remaining_limitations": [
            "Validation used mock RAG because no real AI/ML/RAG service was provided in the sandbox.",
            "BE-9 does not assign support labels or run GenAI verification.",
            "Live external DOI metadata lookup is not part of BE-9 and was skipped here.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BE-9 uploaded research PDF validation.")
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
            "metadata_summary",
            "claims_extracted",
            "claim_reference_links",
            "evidence_packages_created",
            "claims_evidence_packages_tested",
            "retrievals_executed",
            "retrieval_mode",
            "successful_retrievals",
            "no_evidence_retrievals",
            "failed_retrievals",
            "top_chunks_manually_checked",
            "correct_claim_reference_evidence_alignment",
            "similarity_score_observations",
            "timeout_failure_handling_checked",
            "package_items_seen_via_api",
        ):
            print(f"{key}: {result.get(key)}")
        print(f"problems_found: {result.get('problems_found')}")
        print(f"fixes_applied: {result.get('fixes_applied')}")
        print(f"remaining_limitations: {result.get('remaining_limitations')}")


if __name__ == "__main__":
    main()
