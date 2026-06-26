from __future__ import annotations

from testsupport.api_client import ApiTestClient as TestClient
from fastapi import FastAPI

from app.main import app
from app.models.enums import DocumentStatus, PipelineStatus, PipelineStepStatus, SupportStatus

client = TestClient(app)


def assert_error_wrapper(payload: dict) -> None:
    assert payload["success"] is False
    assert payload["data"] is None
    assert payload["request_id"].startswith("req_")
    assert isinstance(payload["errors"], list)
    assert payload["errors"]
    assert "code" in payload["errors"][0]


def test_openapi_contains_final_backend_public_endpoints() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    required = [
        ("/api/v1/health", "get"),
        ("/api/v1/health/readiness", "get"),
        ("/api/v1/documents/upload", "post"),
        ("/api/v1/documents/text", "post"),
        ("/api/v1/documents/{document_id}/extract-references", "post"),
        ("/api/v1/documents/{document_id}/verify-dois", "post"),
        ("/api/v1/documents/{document_id}/extract-claims", "post"),
        ("/api/v1/documents/{document_id}/prepare-evidence", "post"),
        ("/api/v1/claims/{claim_id}/check-cache", "post"),
        ("/api/v1/claims/{claim_id}/retrieve-evidence", "post"),
        ("/api/v1/documents/{document_id}/pipeline-runs", "post"),
        ("/api/v1/documents/{document_id}/verification-results", "get"),
        ("/api/v1/documents/{document_id}/summary", "get"),
        ("/api/v1/documents/{document_id}/reports", "post"),
        ("/api/v1/reports/{report_id}", "get"),
        ("/api/v1/uat/surveys", "post"),
    ]
    missing = [f"{method.upper()} {path}" for path, method in required if path not in paths or method not in paths[path]]
    assert missing == []


def test_core_enums_remain_demo_safe_and_frontend_compatible() -> None:
    assert {item.value for item in SupportStatus} == {
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "NOT_SUPPORTED",
        "INSUFFICIENT_EVIDENCE",
        "NEEDS_HUMAN_REVIEW",
    }
    assert "REPORT_GENERATED" in {item.value for item in DocumentStatus}
    assert {"QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "PARTIAL_FAILED", "CANCELLED"}.issubset({item.value for item in PipelineStatus})
    assert {"PENDING", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "SKIPPED", "PARTIAL_FAILED"}.issubset({item.value for item in PipelineStepStatus})


def test_error_wrappers_for_missing_resources_are_consistent() -> None:
    endpoints = [
        ("/api/v1/documents/doc_missing", "get"),
        ("/api/v1/references/ref_missing", "get"),
        ("/api/v1/claims/claim_missing", "get"),
        ("/api/v1/reports/report_missing", "get"),
        ("/api/v1/verification-results/result_missing", "get"),
    ]
    for path, method in endpoints:
        response = getattr(client, method)(path)
        assert response.status_code in {400, 404, 422}
        assert_error_wrapper(response.json())


def test_api_test_client_handles_sync_routes_without_threadpool_hang() -> None:
    sync_app = FastAPI()

    @sync_app.get("/sync")
    def sync_route() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(sync_app).get("/sync")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_invalid_support_status_filter_uses_standard_validation_error_wrapper() -> None:
    response = client.get("/api/v1/documents/doc_missing/verification-results?support_status=HALLUCINATED")
    payload = response.json()
    assert response.status_code == 422
    assert_error_wrapper(payload)
    assert payload["errors"][0]["code"] == "VALIDATION_ERROR"
    assert payload["errors"][0]["field"] == "support_status"


def test_readiness_exposes_demo_and_mock_service_statuses() -> None:
    response = client.get("/api/v1/health/readiness")
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    for key in ["application", "database", "file_storage", "metadata_lookup", "rag_service", "genai_service", "phase"]:
        assert key in data
    assert data["phase"] == "BE-13"
