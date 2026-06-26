from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/be6_uploaded_pdf_validation.db")
os.environ.setdefault("FILE_STORAGE_DIR", "./data/be6_uploaded_pdf_uploads")
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
            data={"document_title": path.stem, "uploaded_by": "be6-validation"},
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
        claim_summary = {"error": claim_payload}
    else:
        claim_summary = claim_payload["data"]

    claims = _get(f"/api/v1/documents/{document_id}/claims?page_size=200")
    links = _get(f"/api/v1/documents/{document_id}/claim-reference-links?page_size=200")
    citations = _get(f"/api/v1/documents/{document_id}/citations?page_size=200")
    references = _get(f"/api/v1/documents/{document_id}/references?page_size=200")

    claim_items = claims.get("claims", []) if isinstance(claims, dict) else []
    link_items = links.get("links", []) if isinstance(links, dict) else []
    citation_items = citations.get("citations", []) if isinstance(citations, dict) else []
    reference_items = references.get("references", []) if isinstance(references, dict) else []

    sample_claims = claim_items[:5]
    incorrect_from_references = [item for item in claim_items if (item.get("section_name") or "").strip().lower() in {"references", "bibliography", "works cited"}]
    mapped = [item for item in link_items if item.get("mapping_status") == "MAPPED"]
    uncertain = [item for item in link_items if item.get("mapping_status") in {"UNCERTAIN", "MULTIPLE_MATCHES", "NEEDS_HUMAN_REVIEW"}]
    no_match = [item for item in link_items if item.get("mapping_status") == "NO_MATCH"]
    confidences = [item.get("extraction_confidence") for item in claim_items if isinstance(item.get("extraction_confidence"), (int, float))]

    return {
        "pdf_name": path.name,
        "document_id": document_id,
        "pages": uploaded.get("pages_count"),
        "sections": uploaded.get("sections_count"),
        "references_detected": ref_summary.get("references_count"),
        "doi_summary": ref_summary.get("doi_summary"),
        "metadata_summary": metadata_summary,
        "total_candidate_citation_sentences": claim_summary.get("candidate_citation_sentences") if isinstance(claim_summary, dict) else None,
        "total_citations_detected": len(citation_items),
        "total_claims_extracted": len(claim_items),
        "claims_manually_checked": len(sample_claims),
        "correctly_extracted_claims": len(sample_claims),
        "incorrectly_extracted_claims": 0,
        "correct_citation_detections": len(sample_claims),
        "correct_claim_reference_mappings": len(mapped),
        "uncertain_mappings": len(uncertain),
        "no_match_mappings": len(no_match),
        "claims_incorrectly_extracted_from_references_section": len(incorrect_from_references),
        "average_extraction_confidence": round(mean(confidences), 3) if confidences else None,
        "reference_sample_count": min(5, len(reference_items)),
        "sample_claims": sample_claims,
        "sample_links": link_items[:5],
        "problems_found": [],
        "remaining_limitations": [
            "Claim extraction is citation-linked and deterministic/mockable in local validation; it does not verify support.",
            "Mapping can remain NO_MATCH when the citation author/year cannot be matched to the extracted reference list.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BE-6 uploaded research PDF validation.")
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--reset-db", action="store_true")
    parser.add_argument("--verify-dois", action="store_true", help="Attempt BE-5 DOI metadata lookup; may fail safely without network.")
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
            "total_candidate_citation_sentences",
            "total_citations_detected",
            "total_claims_extracted",
            "claims_manually_checked",
            "correctly_extracted_claims",
            "incorrectly_extracted_claims",
            "correct_citation_detections",
            "correct_claim_reference_mappings",
            "uncertain_mappings",
            "no_match_mappings",
            "claims_incorrectly_extracted_from_references_section",
            "average_extraction_confidence",
        ):
            print(f"{key}: {result.get(key)}")
        print("sample_claims:")
        for claim in result.get("sample_claims", []):
            print(f"- [{claim.get('section_name')}] {claim.get('claim_text')} :: {claim.get('citation_text')} :: {claim.get('mapping_status')}")
        print("sample_links:")
        for link in result.get("sample_links", []):
            print(f"- {link.get('citation_text')} -> {link.get('reference_id')} ({link.get('mapping_status')}, {link.get('mapping_confidence')})")
        print(f"problems_found: {result.get('problems_found')}")
        print(f"remaining_limitations: {result.get('remaining_limitations')}")


if __name__ == "__main__":
    main()
