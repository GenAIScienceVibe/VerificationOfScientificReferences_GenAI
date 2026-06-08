from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/qa_real_pdf_test.db")
os.environ.setdefault("FILE_STORAGE_DIR", "./data/qa_real_pdf_uploads")
os.environ.setdefault("ENABLE_RAW_TEXT_DEBUG_ENDPOINT", "true")
os.environ.setdefault("LOG_LEVEL", "ERROR")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.init_db import drop_db_for_tests_only, init_db  # noqa: E402
from app.main import app  # noqa: E402


def _extract_references(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload.get("data", {}).get("references", []) or []


def _is_standalone_doi_reference(raw: str) -> bool:
    stripped = raw.strip()
    return bool(re.fullmatch(r"(?:https?://(?:dx\.)?doi\.org/|doi\s*[: ]\s*)?10\.\d{4,9}/\S+", stripped, re.IGNORECASE))


def _has_author_contaminated_doi(doi: str | None) -> bool:
    value = (doi or "").lower()
    return any(marker in value for marker in ("-preacher", "-mitschelen", "-olafsen", "-soulami", "-tausendpfund"))


def _looks_like_continuation_fragment(raw: str) -> bool:
    lowered = raw.lower().strip()
    if re.match(r"^(organizational psychology|psychology|artificial intelligence|health|information and learning technology),", lowered):
        return True
    if re.match(r"^[a-z\s]+,\s*\d+[,\.]\s+https?://", lowered):
        return True
    return False


def run_pdf_flow(pdf_path: Path) -> dict[str, Any]:
    client = TestClient(app)
    with pdf_path.open("rb") as file_handle:
        upload = client.post(
            "/api/v1/documents/upload",
            files={"file": (pdf_path.name, file_handle.read(), "application/pdf")},
            data={"document_title": pdf_path.stem},
        )
    upload_payload = upload.json()
    document_id = upload_payload.get("data", {}).get("document_id")
    result: dict[str, Any] = {
        "pdf": pdf_path.name,
        "upload_status_code": upload.status_code,
        "upload": upload_payload,
    }
    if not document_id:
        result["qa_pass"] = False
        result["qa_failures"] = ["UPLOAD_FAILED"]
        return result

    sections = client.get(f"/api/v1/documents/{document_id}/sections", params={"include_text": True})
    extract = client.post(f"/api/v1/documents/{document_id}/extract-references")
    refs = client.get(f"/api/v1/documents/{document_id}/references", params={"page_size": 200})
    found = client.get(f"/api/v1/documents/{document_id}/references", params={"doi_status": "FOUND", "page_size": 200})
    missing = client.get(f"/api/v1/documents/{document_id}/references", params={"doi_status": "MISSING", "page_size": 200})
    malformed = client.get(f"/api/v1/documents/{document_id}/references", params={"doi_status": "MALFORMED", "page_size": 200})
    invalid_filter = client.get(f"/api/v1/documents/{document_id}/references", params={"doi_status": "BAD_STATUS"})

    refs_payload = refs.json()
    references = _extract_references(refs_payload)
    section_payload = sections.json().get("data", {}).get("sections", [])
    extract_payload = extract.json()
    extract_data = extract_payload.get("data", {}) or {}
    doi_coverage = extract_data.get("doi_coverage", {}) or {}

    bad_marker_references = [
        ref.get("raw_reference")
        for ref in references
        if any(
            marker in (ref.get("raw_reference") or "").lower()
            for marker in (
                "employment status",
                "welcome to the study",
                "test510",
                "journalpedia.com/1/index.php/jsti",
            )
        )
    ]
    bad_found_dois = [
        ref.get("extracted_doi")
        for ref in references
        if ref.get("doi_status") == "FOUND"
        and (str(ref.get("extracted_doi") or "").endswith("-") or _has_author_contaminated_doi(ref.get("extracted_doi")))
    ]
    standalone_doi_references = [ref.get("raw_reference") for ref in references if _is_standalone_doi_reference(ref.get("raw_reference") or "")]
    continuation_fragment_references = [ref.get("raw_reference") for ref in references if _looks_like_continuation_fragment(ref.get("raw_reference") or "")]

    failures: list[str] = []
    if upload.status_code != 200:
        failures.append("UPLOAD_NOT_200")
    if sections.status_code != 200:
        failures.append("SECTIONS_NOT_200")
    if extract.status_code != 200:
        failures.append("EXTRACT_NOT_200")
    if refs.status_code != 200:
        failures.append("REFERENCES_NOT_200")
    if invalid_filter.status_code not in (400, 422):
        failures.append("INVALID_FILTER_NOT_REJECTED")
    if bad_marker_references:
        failures.append("BAD_MARKER_REFERENCES")
    if bad_found_dois:
        failures.append("BAD_FOUND_DOIS")
    if standalone_doi_references:
        failures.append("STANDALONE_DOI_REFERENCES")
    if continuation_fragment_references:
        failures.append("CONTINUATION_FRAGMENT_REFERENCES")
    if doi_coverage.get("source_doi_count", 0) >= 5 and doi_coverage.get("coverage_ratio", 0) < 0.85:
        failures.append("LOW_DOI_COVERAGE")

    result.update(
        {
            "document_id": document_id,
            "sections_status_code": sections.status_code,
            "sections_summary": [
                {"name": item.get("name"), "chars": len(item.get("text") or "")} for item in section_payload
            ],
            "extract_status_code": extract.status_code,
            "extract": extract_payload,
            "references_status_code": refs.status_code,
            "references_total": refs_payload.get("data", {}).get("total"),
            "doi_found_total": found.json().get("data", {}).get("total") if found.status_code == 200 else None,
            "doi_missing_total": missing.json().get("data", {}).get("total") if missing.status_code == 200 else None,
            "doi_malformed_total": malformed.json().get("data", {}).get("total") if malformed.status_code == 200 else None,
            "source_doi_count": doi_coverage.get("source_doi_count"),
            "extracted_doi_count": doi_coverage.get("extracted_doi_count"),
            "matched_doi_count": doi_coverage.get("matched_doi_count"),
            "doi_coverage_ratio": doi_coverage.get("coverage_ratio"),
            "missing_from_extracted": doi_coverage.get("missing_from_extracted", []),
            "unexpected_extracted": doi_coverage.get("unexpected_extracted", []),
            "bad_marker_references": bad_marker_references,
            "bad_found_dois": bad_found_dois,
            "standalone_doi_references": standalone_doi_references,
            "continuation_fragment_references": continuation_fragment_references,
            "invalid_filter_status_code": invalid_filter.status_code,
            "first_references": references[:5],
            "qa_pass": not failures,
            "qa_failures": failures,
        }
    )
    return result


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/qa_real_pdf_api_test.py <pdf1> [<pdf2> ...]")
    get_settings.cache_clear()
    drop_db_for_tests_only()
    init_db()
    upload_dir = ROOT / "data" / "qa_real_pdf_uploads"
    shutil.rmtree(upload_dir, ignore_errors=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    results = [run_pdf_flow(Path(arg)) for arg in sys.argv[1:]]
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
