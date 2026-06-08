from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/qa_real_pdf_test.db")
os.environ.setdefault("FILE_STORAGE_DIR", "./data/qa_real_pdf_uploads")
os.environ.setdefault("ENABLE_RAW_TEXT_DEBUG_ENDPOINT", "true")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.init_db import drop_db_for_tests_only, init_db  # noqa: E402
from app.main import app  # noqa: E402


def run_pdf_flow(pdf_path: Path) -> dict:
    client = TestClient(app)
    with pdf_path.open("rb") as file_handle:
        upload = client.post(
            "/api/v1/documents/upload",
            files={"file": (pdf_path.name, file_handle.read(), "application/pdf")},
            data={"document_title": pdf_path.stem},
        )
    upload_payload = upload.json()
    document_id = upload_payload.get("data", {}).get("document_id")
    result: dict = {
        "pdf": pdf_path.name,
        "upload_status_code": upload.status_code,
        "upload": upload_payload,
    }
    if not document_id:
        return result

    sections = client.get(f"/api/v1/documents/{document_id}/sections", params={"include_text": True})
    extract = client.post(f"/api/v1/documents/{document_id}/extract-references")
    refs = client.get(f"/api/v1/documents/{document_id}/references", params={"page_size": 200})
    found = client.get(f"/api/v1/documents/{document_id}/references", params={"doi_status": "FOUND", "page_size": 200})
    missing = client.get(f"/api/v1/documents/{document_id}/references", params={"doi_status": "MISSING", "page_size": 200})
    malformed = client.get(f"/api/v1/documents/{document_id}/references", params={"doi_status": "MALFORMED", "page_size": 200})

    refs_payload = refs.json()
    references = refs_payload.get("data", {}).get("references", [])
    section_payload = sections.json().get("data", {}).get("sections", [])
    result.update(
        {
            "document_id": document_id,
            "sections_status_code": sections.status_code,
            "sections_summary": [
                {"name": item.get("name"), "chars": len(item.get("text") or "")} for item in section_payload
            ],
            "extract_status_code": extract.status_code,
            "extract": extract.json(),
            "references_status_code": refs.status_code,
            "references_total": refs_payload.get("data", {}).get("total"),
            "doi_found_total": found.json().get("data", {}).get("total") if found.status_code == 200 else None,
            "doi_missing_total": missing.json().get("data", {}).get("total") if missing.status_code == 200 else None,
            "doi_malformed_total": malformed.json().get("data", {}).get("total") if malformed.status_code == 200 else None,
            "bad_marker_references": [
                ref.get("raw_reference")
                for ref in references
                if any(
                    marker in (ref.get("raw_reference") or "").lower()
                    for marker in ("employment status", "welcome to the study", "test510", "journalpedia.com/1/index.php/jsti")
                )
            ],
            "bad_found_dois": [
                ref.get("extracted_doi")
                for ref in references
                if ref.get("doi_status") == "FOUND" and str(ref.get("extracted_doi") or "").endswith("-")
            ],
            "first_references": references[:5],
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
