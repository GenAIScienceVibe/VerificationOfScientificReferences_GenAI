from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.db.init_db import drop_db_for_tests_only, init_db
from app.main import app


def validate_pdf(path: Path, client: TestClient, *, attempt_live_metadata: bool) -> dict:
    with path.open("rb") as handle:
        upload = client.post(
            "/api/v1/documents/upload",
            files={"file": (path.name, handle, "application/pdf")},
            data={"document_title": path.name},
        )
    result: dict = {"pdf_name": path.name, "upload_status_code": upload.status_code}
    if upload.status_code != 200:
        result["upload_error"] = upload.json()
        return result

    document_id = upload.json()["data"]["document_id"]
    result["document_id"] = document_id
    result["pages_count"] = upload.json()["data"].get("pages_count")
    result["sections_count"] = upload.json()["data"].get("sections_count")

    extraction = client.post(f"/api/v1/documents/{document_id}/extract-references")
    result["reference_extraction_status_code"] = extraction.status_code
    if extraction.status_code != 200:
        result["reference_extraction_error"] = extraction.json()
        return result

    extraction_data = extraction.json()["data"]
    result.update(
        {
            "references_count": extraction_data.get("references_count"),
            "doi_summary": extraction_data.get("doi_summary"),
            "doi_coverage": extraction_data.get("doi_coverage"),
            "quality_warnings": extraction_data.get("quality_warnings"),
        }
    )

    references = client.get(f"/api/v1/documents/{document_id}/references", params={"page_size": 200}).json()["data"]["references"]
    result["doi_status_counts"] = dict(Counter(ref["doi_status"] for ref in references))
    result["sample_references"] = [
        {
            "reference_key": ref["reference_key"],
            "doi_status": ref["doi_status"],
            "extracted_doi": ref["extracted_doi"],
            "raw_reference_preview": ref["raw_reference"][:260],
        }
        for ref in references[:8]
    ]

    if attempt_live_metadata:
        first_with_doi = next((ref for ref in references if ref.get("extracted_doi")), None)
        if first_with_doi:
            metadata = client.post(f"/api/v1/references/{first_with_doi['reference_id']}/verify-doi")
            result["live_metadata_sample_status_code"] = metadata.status_code
            result["live_metadata_sample"] = metadata.json().get("data") if metadata.status_code == 200 else metadata.json()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BE-3, BE4.2, and BE-5 smoke validation on local PDFs.")
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--reset-db", action="store_true")
    parser.add_argument("--attempt-live-metadata", action="store_true")
    args = parser.parse_args()

    if args.reset_db:
        drop_db_for_tests_only()
    init_db()

    client = TestClient(app)
    for pdf in args.pdfs:
        print(validate_pdf(pdf, client, attempt_live_metadata=args.attempt_live_metadata))


if __name__ == "__main__":
    os.environ.setdefault("ENABLE_RAW_TEXT_DEBUG_ENDPOINT", "true")
    main()
