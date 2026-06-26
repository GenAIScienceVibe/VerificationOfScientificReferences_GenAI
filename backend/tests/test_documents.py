from __future__ import annotations

from io import BytesIO

import fitz
from testsupport.api_client import ApiTestClient as TestClient

from app.main import app

client = TestClient(app)

SAMPLE_TEXT = """Demo Scientific Paper

Abstract
Generative AI tools can improve academic writing productivity (Smith, 2023). The DOI 10.1234/demo.2023 remains visible.

Introduction
This paragraph introduces the research context and keeps APA citations (Smith, 2023).

References
Smith, J. (2023). Demo paper. https://doi.org/10.1234/demo.2023
"""


def make_sample_pdf_bytes(text: str = SAMPLE_TEXT) -> bytes:
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    stream = pdf.write()
    pdf.close()
    return stream


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert payload["success"] is success
    assert "data" in payload
    assert "message" in payload
    assert isinstance(payload["errors"], list)
    assert payload["request_id"].startswith("req_")


def test_text_submission_processes_text_and_sections() -> None:
    response = client.post("/api/v1/documents/text", json={"title": "Demo Paper", "text": SAMPLE_TEXT})
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    document_id = payload["data"]["document_id"]
    assert payload["data"]["upload_type"] == "TEXT"
    assert payload["data"]["status"] == "TEXT_EXTRACTED"
    assert payload["data"]["is_stub"] is False
    assert payload["data"]["sections_count"] >= 3

    metadata_response = client.get(f"/api/v1/documents/{document_id}")
    assert metadata_response.status_code == 200
    metadata = metadata_response.json()
    assert_wrapper(metadata)
    assert metadata["data"]["document_id"] == document_id
    assert metadata["data"]["claims_count"] == 0
    assert metadata["data"]["references_count"] == 0
    assert metadata["data"]["phase"] == "BE-3"

    status_response = client.get(f"/api/v1/documents/{document_id}/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert_wrapper(status_payload)
    assert status_payload["data"]["current_step"] == "COMPLETED"
    assert status_payload["data"]["progress_percentage"] == 30

    sections_response = client.get(f"/api/v1/documents/{document_id}/sections")
    assert sections_response.status_code == 200
    sections_payload = sections_response.json()
    assert_wrapper(sections_payload)
    section_names = {section["name"] for section in sections_payload["data"]["sections"]}
    assert "Abstract" in section_names
    assert "References" in section_names

    raw_text_response = client.get(f"/api/v1/documents/{document_id}/raw-text")
    assert raw_text_response.status_code == 200
    raw_payload = raw_text_response.json()
    assert_wrapper(raw_payload)
    assert "10.1234/demo.2023" in raw_payload["data"]["cleaned_text"]
    assert "(Smith, 2023)" in raw_payload["data"]["cleaned_text"]


def test_pdf_upload_success_extracts_text_and_does_not_expose_storage_path() -> None:
    files = {"file": ("paper.pdf", make_sample_pdf_bytes(), "application/pdf")}
    response = client.post("/api/v1/documents/upload", files=files, data={"document_title": "PDF Demo"})
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    document_id = payload["data"]["document_id"]
    assert payload["data"]["filename"] == "paper.pdf"
    assert payload["data"]["title"] == "PDF Demo"
    assert payload["data"]["upload_type"] == "PDF"
    assert payload["data"]["status"] == "TEXT_EXTRACTED"
    assert payload["data"]["pages_count"] == 1
    assert "file_storage_path" not in payload["data"]

    raw_text_response = client.get(f"/api/v1/documents/{document_id}/raw-text")
    assert raw_text_response.status_code == 200
    assert "Generative AI tools" in raw_text_response.json()["data"]["cleaned_text"]


def test_upload_missing_file_returns_file_required() -> None:
    response = client.post("/api/v1/documents/upload")
    assert response.status_code == 400
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "FILE_REQUIRED"


def test_upload_rejects_non_pdf_file() -> None:
    files = {"file": ("paper.txt", b"not a pdf", "text/plain")}
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 415
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "INVALID_FILE_TYPE"
    assert payload["errors"][0]["field"] == "file"


def test_upload_rejects_corrupted_pdf() -> None:
    files = {"file": ("broken.pdf", b"%PDF-1.4 broken", "application/pdf")}
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 422
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] in {"PDF_READ_FAILED", "TEXT_EXTRACTION_FAILED"}


def test_text_submission_empty_text_returns_project_error() -> None:
    response = client.post("/api/v1/documents/text", json={"title": "Empty", "text": "   "})
    assert response.status_code == 400
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "TEXT_REQUIRED"


def test_text_submission_too_short_returns_project_error() -> None:
    response = client.post("/api/v1/documents/text", json={"title": "Short", "text": "Too short"})
    assert response.status_code == 400
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "TEXT_TOO_SHORT"


def test_unknown_document_returns_error_wrapper() -> None:
    response = client.get("/api/v1/documents/doc_missing/status")
    assert response.status_code == 404
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "DOCUMENT_NOT_FOUND"
