from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_unknown_route_uses_error_wrapper() -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["data"] is None
    assert payload["errors"]
    assert payload["request_id"].startswith("req_")


def test_validation_error_uses_error_wrapper() -> None:
    response = client.post("/api/v1/documents/text", json={"title": "", "text": ""})
    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["data"] is None
    assert payload["errors"][0]["code"] == "VALIDATION_ERROR"
    assert payload["request_id"].startswith("req_")
