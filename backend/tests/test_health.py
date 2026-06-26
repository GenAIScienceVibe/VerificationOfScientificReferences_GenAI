from testsupport.api_client import ApiTestClient as TestClient

from app.main import app

client = TestClient(app)


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert set(["success", "data", "message", "errors", "request_id"]).issubset(payload.keys())
    assert payload["success"] is success
    assert isinstance(payload["errors"], list)
    assert payload["request_id"].startswith("req_")


def test_health_endpoint_returns_standard_wrapper() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    assert payload["data"]["status"] == "OK"
    assert payload["data"]["service"] == "refcheck-backend"
    assert payload["message"] == "Backend is healthy"


def test_readiness_endpoint_returns_dependency_statuses() -> None:
    response = client.get("/api/v1/health/readiness")
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    data = payload["data"]
    for key in ["application", "database", "file_storage", "metadata_lookup", "rag_service", "genai_service"]:
        assert key in data
    assert data["database"].startswith("ready")
    assert data["file_storage"] == "ready"
