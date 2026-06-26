from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import SupportStatus

client = TestClient(app)

DEMO_TEXT = """Demo AI Education Paper

Abstract
AI writing assistants may reduce drafting time for students (Smith, 2023).

Introduction
Prior research suggests that AI writing assistants can improve drafting speed (Smith, 2023). However, broad claims about learning outcomes need careful review (Lee, 2022).

Discussion
Transparent AI feedback can increase trust in learning technologies (Garcia, 2024).

References
Smith, J. (2023). AI Writing Assistants and Drafting Speed. Journal of AI Education. https://doi.org/10.1234/demo.ai.2023
Lee, A. (2022). Learning Outcomes Without DOI. Academic Press.
Garcia, M. (2024). Transparent AI Feedback in Education. Computers and Education. https://doi.org/10.5678/transparent.feedback.2024
"""


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert payload["success"] is success
    assert "request_id" in payload
    assert isinstance(payload["errors"], list)
    assert "data" in payload


def post(path: str, payload: dict | None = None) -> dict:
    response = client.post(path, json=payload, headers={"X-Request-ID": "req_be13_integration"})
    assert response.headers.get("x-request-id") == "req_be13_integration"
    body = response.json()
    assert_wrapper(body)
    return body["data"]


def get(path: str) -> dict:
    response = client.get(path, headers={"X-Request-ID": "req_be13_integration"})
    assert response.headers.get("x-request-id") == "req_be13_integration"
    body = response.json()
    assert_wrapper(body)
    return body["data"]


def test_be13_full_demo_pipeline_from_text_to_report_and_feedback() -> None:
    uploaded = post("/api/v1/documents/text", {"title": "BE13 Demo", "text": DEMO_TEXT})
    document_id = uploaded["document_id"]

    refs = post(f"/api/v1/documents/{document_id}/extract-references")
    assert refs["references_count"] >= 2
    assert refs["doi_summary"]["found"] >= 1

    claims = post(f"/api/v1/documents/{document_id}/extract-claims", {"mode": "citation_linked_only"})
    assert claims["claims_count"] >= 2

    evidence = post(f"/api/v1/documents/{document_id}/prepare-evidence")
    assert evidence["evidence_packages_created"] >= 1

    pipeline = post(
        f"/api/v1/documents/{document_id}/pipeline-runs",
        {"mode": "FULL_VERIFICATION", "use_cache": True, "use_rag": True, "use_genai_safety_review": True, "generate_report": False},
    )
    assert pipeline["status"] in {"SUCCEEDED", "PARTIAL_FAILED"}
    assert pipeline["progress_percentage"] == 100

    steps = get(f"/api/v1/pipeline-runs/{pipeline['pipeline_run_id']}/steps")
    assert len(steps["steps"]) == 10

    results = get(f"/api/v1/documents/{document_id}/verification-results")
    assert results["total"] >= 1
    allowed = {item.value for item in SupportStatus}
    assert all(item["support_status"] in allowed for item in results["results"])

    report = post(
        f"/api/v1/documents/{document_id}/reports",
        {"format": "HTML", "include_evidence_chunks": True, "include_human_review_items": True, "include_limitations": True},
    )
    report_data = get(f"/api/v1/reports/{report['report_id']}")
    html = report_data["html_content"]
    assert "Document Overview" in html
    assert "Limitations" in html
    assert "Hallucinated" not in html

    result_id = results["results"][0]["result_id"]
    feedback = post(
        f"/api/v1/verification-results/{result_id}/feedback",
        {"user_label": "NEEDS_HUMAN_REVIEW", "user_comment": "BE-13 integration feedback", "user_role": "qa"},
    )
    assert feedback["feedback_id"].startswith("feedback_")

    survey = post(
        "/api/v1/uat/surveys",
        {"document_id": document_id, "participant_role": "qa", "ease_of_use_rating": 4, "result_clarity_rating": 4, "trust_rating": 4, "usefulness_rating": 5},
    )
    assert survey["survey_id"].startswith("survey_")
