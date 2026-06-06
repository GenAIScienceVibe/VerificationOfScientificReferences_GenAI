from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert payload["success"] is success
    assert "data" in payload
    assert "message" in payload
    assert isinstance(payload["errors"], list)
    assert payload["request_id"].startswith("req_")


def test_text_submission_and_document_status_database_stub() -> None:
    response = client.post("/api/v1/documents/text", json={"title": "Demo Paper", "text": "This is a test."})
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    document_id = payload["data"]["document_id"]
    assert payload["data"]["upload_type"] == "TEXT"
    assert payload["data"]["status"] == "UPLOADED"
    assert payload["data"]["is_stub"] is True

    metadata_response = client.get(f"/api/v1/documents/{document_id}")
    assert metadata_response.status_code == 200
    metadata = metadata_response.json()
    assert_wrapper(metadata)
    assert metadata["data"]["document_id"] == document_id
    assert metadata["data"]["claims_count"] == 0
    assert metadata["data"]["phase"] == "BE-2"

    status_response = client.get(f"/api/v1/documents/{document_id}/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert_wrapper(status_payload)
    assert status_payload["data"]["latest_pipeline_run_id"] == "not_started_be2_db_stub"


def test_pdf_upload_stub_success() -> None:
    files = {"file": ("paper.pdf", b"%PDF-1.4\n%stub", "application/pdf")}
    response = client.post("/api/v1/documents/upload", files=files, data={"document_title": "PDF Demo"})
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    assert payload["data"]["filename"] == "paper.pdf"
    assert payload["data"]["upload_type"] == "PDF"
    assert payload["data"]["status"] == "UPLOADED"
    assert payload["data"]["file_size_bytes"] > 0


def test_upload_rejects_non_pdf_file() -> None:
    files = {"file": ("paper.txt", b"not a pdf", "text/plain")}
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 415
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "INVALID_FILE_TYPE"
    assert payload["errors"][0]["field"] == "file"


def test_unknown_document_returns_error_wrapper() -> None:
    response = client.get("/api/v1/documents/doc_missing/status")
    assert response.status_code == 404
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "DOCUMENT_NOT_FOUND"
