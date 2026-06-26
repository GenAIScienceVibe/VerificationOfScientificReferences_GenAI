from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/refcheck_demo.db")
os.environ.setdefault("FILE_STORAGE_DIR", "./data/demo_uploads")
os.environ.setdefault("ENABLE_RAW_TEXT_DEBUG_ENDPOINT", "true")
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("RAG_MOCK_MODE", "true")
os.environ.setdefault("GENAI_MOCK_MODE", "true")
os.environ.setdefault("CACHE_SEMANTIC_ENABLED", "false")

from testsupport.api_client import ApiTestClient as TestClient
from app.db.init_db import init_db  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

DEMO_TEXT = """Demo AI Education Paper

Abstract
AI writing assistants may reduce drafting time for students (Smith, 2023).

Introduction
Prior research suggests that AI writing assistants can improve drafting speed (Smith, 2023). However, claims about overall learning outcomes need careful review (Lee, 2022).

Discussion
Students may trust AI tools when feedback is transparent (Garcia, 2024).

References
Smith, J. (2023). AI Writing Assistants and Drafting Speed. Journal of AI Education. https://doi.org/10.1234/demo.ai.2023
Lee, A. (2022). Learning Outcomes Without DOI. Academic Press.
Garcia, M. (2024). Transparent AI Feedback in Education. Computers and Education. https://doi.org/10.5678/transparent.feedback.2024
"""


def post(path: str, payload: dict | None = None) -> dict:
    response = client.post(path, json=payload)
    print(f"POST {path}: {response.status_code}")
    data = response.json()
    if response.status_code >= 400:
        raise RuntimeError(data)
    return data["data"]


def get(path: str) -> dict:
    response = client.get(path)
    print(f"GET {path}: {response.status_code}")
    data = response.json()
    if response.status_code >= 400:
        raise RuntimeError(data)
    return data["data"]


def main() -> int:
    init_db()
    uploaded = post("/api/v1/documents/text", {"title": "BE13 Demo Paper", "text": DEMO_TEXT})
    document_id = uploaded["document_id"]
    post(f"/api/v1/documents/{document_id}/extract-references")
    post(f"/api/v1/documents/{document_id}/extract-claims", {"mode": "citation_linked_only"})
    post(f"/api/v1/documents/{document_id}/prepare-evidence")
    run = post(
        f"/api/v1/documents/{document_id}/pipeline-runs",
        {"mode": "FULL_VERIFICATION", "use_cache": True, "use_rag": True, "use_genai_safety_review": True, "generate_report": False},
    )
    summary = get(f"/api/v1/documents/{document_id}/summary")
    report = post(
        f"/api/v1/documents/{document_id}/reports",
        {"format": "HTML", "include_evidence_chunks": True, "include_human_review_items": True, "include_limitations": True},
    )
    print("Demo complete")
    print(f"document_id={document_id}")
    print(f"pipeline_run_id={run['pipeline_run_id']}")
    print(f"report_id={report['report_id']}")
    print(f"summary={summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
