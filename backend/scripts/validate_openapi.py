from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

REQUIRED_PUBLIC_ENDPOINTS = [
    ("/api/v1/health", "GET"),
    ("/api/v1/health/readiness", "GET"),
    ("/api/v1/documents/upload", "POST"),
    ("/api/v1/documents/text", "POST"),
    ("/api/v1/documents/{document_id}/extract-references", "POST"),
    ("/api/v1/documents/{document_id}/verify-dois", "POST"),
    ("/api/v1/documents/{document_id}/extract-claims", "POST"),
    ("/api/v1/documents/{document_id}/prepare-evidence", "POST"),
    ("/api/v1/claims/{claim_id}/check-cache", "POST"),
    ("/api/v1/claims/{claim_id}/retrieve-evidence", "POST"),
    ("/api/v1/documents/{document_id}/pipeline-runs", "POST"),
    ("/api/v1/documents/{document_id}/verification-results", "GET"),
    ("/api/v1/documents/{document_id}/summary", "GET"),
    ("/api/v1/documents/{document_id}/reports", "POST"),
    ("/api/v1/reports/{report_id}", "GET"),
    ("/api/v1/uat/surveys", "POST"),
]


def main() -> int:
    schema = app.openapi()
    paths = schema.get("paths", {})
    missing: list[str] = []
    for endpoint, method in REQUIRED_PUBLIC_ENDPOINTS:
        if endpoint not in paths or method.lower() not in paths[endpoint]:
            missing.append(f"{method} {endpoint}")
    out = ROOT / "validation" / "openapi_be13_generated.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"OpenAPI title: {schema['info']['title']}")
    print(f"OpenAPI version: {schema['info']['version']}")
    print(f"OpenAPI path count: {len(paths)}")
    print(f"Required endpoint gaps: {missing}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
