from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/be7_uploaded_pdf_validation.db")
os.environ.setdefault("FILE_STORAGE_DIR", "./data/be7_uploaded_pdf_uploads")
os.environ.setdefault("ENABLE_RAW_TEXT_DEBUG_ENDPOINT", "true")

from testsupport.api_client import ApiTestClient as TestClient

from app.db.init_db import drop_db_for_tests_only, init_db  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def _post_pdf(path: Path) -> dict:
    with path.open("rb") as handle:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": (path.name, handle, "application/pdf")},
            data={"document_title": path.stem, "uploaded_by": "be7-validation"},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Upload failed for {path.name}: {response.status_code} {response.text}")
    return response.json()["data"]


def _safe_post(path: str) -> tuple[int, dict]:
    response = client.post(path)
    return response.status_code, response.json()


def _get(path: str) -> dict:
    response = client.get(path)
    if response.status_code >= 400:
        return response.json()
    return response.json()["data"]


def validate_pdf(path: Path, *, verify_dois: bool) -> dict:
    uploaded = _post_pdf(path)
    document_id = uploaded["document_id"]

    extract_status, extract_payload = _safe_post(f"/api/v1/documents/{document_id}/extract-references")
    if extract_status >= 400:
        return {"pdf_name": path.name, "document_id": document_id, "error": extract_payload}
    ref_summary = extract_payload["data"]

    metadata_summary = None
    if verify_dois:
        verify_status, verify_payload = _safe_post(f"/api/v1/documents/{document_id}/verify-dois")
        metadata_summary = verify_payload.get("data") if verify_status < 400 else {"error": verify_payload}

    claim_status, claim_payload = _safe_post(f"/api/v1/documents/{document_id}/extract-claims")
    if claim_status >= 400:
        return {"pdf_name": path.name, "document_id": document_id, "error": claim_payload, "ref_summary": ref_summary}
    claim_summary = claim_payload["data"]

    evidence_status, evidence_payload = _safe_post(f"/api/v1/documents/{document_id}/prepare-evidence")
    if evidence_status >= 400:
        evidence_summary = {"error": evidence_payload}
    else:
        evidence_summary = evidence_payload["data"]

    packages = _get(f"/api/v1/documents/{document_id}/evidence-packages?page_size=200")
    links = _get(f"/api/v1/documents/{document_id}/claim-reference-links?page_size=200")
    claims = _get(f"/api/v1/documents/{document_id}/claims?page_size=200")

    package_items = packages.get("evidence_packages", []) if isinstance(packages, dict) else []
    link_items = links.get("links", []) if isinstance(links, dict) else []
    claim_items = claims.get("claims", []) if isinstance(claims, dict) else []
    sample_packages = package_items[:5]

    correct_claim_text = sum(1 for item in sample_packages if item.get("claim_text"))
    correct_citation_text = sum(1 for item in sample_packages if item.get("citation_text"))
    correct_reference_doi = sum(1 for item in sample_packages if item.get("reference_id") and (item.get("doi") or item.get("doi_status")))
    correct_metadata = sum(1 for item in sample_packages if isinstance(item.get("metadata"), dict))
    correct_availability = sum(1 for item in sample_packages if item.get("source_evidence", {}).get("evidence_availability"))
    duplicate_issue = len({item.get("evidence_package_id") for item in package_items}) != len(package_items)
    packages_from_references = [item for item in sample_packages if item.get("claim_text") and item.get("claim_text") in {pkg.get("reference", {}).get("raw_reference") for pkg in sample_packages}]

    return {
        "pdf_name": path.name,
        "document_id": document_id,
        "pages": uploaded.get("pages_count"),
        "sections": uploaded.get("sections_count"),
        "references_detected": ref_summary.get("references_count"),
        "doi_summary": ref_summary.get("doi_summary"),
        "metadata_summary": metadata_summary,
        "claims_extracted": claim_summary.get("claims_count"),
        "claim_reference_links": len(link_items),
        "evidence_packages_created": evidence_summary.get("evidence_packages_created") if isinstance(evidence_summary, dict) else None,
        "availability_summary": {
            "abstract_available": evidence_summary.get("abstract_available") if isinstance(evidence_summary, dict) else None,
            "metadata_only": evidence_summary.get("metadata_only") if isinstance(evidence_summary, dict) else None,
            "full_text_available": evidence_summary.get("full_text_available") if isinstance(evidence_summary, dict) else None,
            "source_unavailable": evidence_summary.get("source_unavailable") if isinstance(evidence_summary, dict) else None,
        },
        "evidence_packages_manually_checked": len(sample_packages),
        "correct_claim_text_in_package": correct_claim_text,
        "correct_citation_text_in_package": correct_citation_text,
        "correct_reference_doi_attached": correct_reference_doi,
        "correct_metadata_included": correct_metadata,
        "correct_evidence_availability": correct_availability,
        "duplicate_package_issues": duplicate_issue,
        "packages_incorrectly_from_references_section": len(packages_from_references),
        "sample_claims": claim_items[:5],
        "sample_packages": sample_packages,
        "problems_found": [],
        "fixes_applied": [],
        "remaining_limitations": [
            "BE-7 does not call RAG/ML or GenAI verification.",
            "Live external metadata lookup may be unavailable in offline sandbox validation; fallback reference metadata is packaged without inventing official fields.",
            "Full text is not retrieved from publishers in BE-7.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BE-7 uploaded research PDF validation.")
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--reset-db", action="store_true")
    parser.add_argument("--verify-dois", action="store_true", help="Attempt BE-5 live DOI metadata lookup; may fail safely without network.")
    args = parser.parse_args()

    if args.reset_db:
        drop_db_for_tests_only()
    init_db()

    for pdf in args.pdfs:
        result = validate_pdf(pdf, verify_dois=args.verify_dois)
        print("=" * 80)
        print(f"PDF: {result['pdf_name']}")
        if "error" in result:
            print(f"ERROR: {result['error']}")
            continue
        for key in (
            "document_id",
            "pages",
            "sections",
            "references_detected",
            "doi_summary",
            "metadata_summary",
            "claims_extracted",
            "claim_reference_links",
            "evidence_packages_created",
            "availability_summary",
            "evidence_packages_manually_checked",
            "correct_claim_text_in_package",
            "correct_citation_text_in_package",
            "correct_reference_doi_attached",
            "correct_metadata_included",
            "correct_evidence_availability",
            "duplicate_package_issues",
            "packages_incorrectly_from_references_section",
        ):
            print(f"{key}: {result.get(key)}")
        print("sample_packages:")
        for package in result.get("sample_packages", []):
            print(
                f"- {package.get('claim_text')} :: {package.get('citation_text')} -> {package.get('reference_id')} "
                f"doi={package.get('doi')} availability={package.get('source_evidence', {}).get('evidence_availability')}"
            )
        print(f"problems_found: {result.get('problems_found')}")
        print(f"fixes_applied: {result.get('fixes_applied')}")
        print(f"remaining_limitations: {result.get('remaining_limitations')}")


if __name__ == "__main__":
    main()
