# BE-13 — Testing, Logging, and Demo Hardening

BE-13 is the final backend stabilization phase for the verifAI / RefCheck AI project. It does not add frontend UI or new AI/RAG algorithms. It hardens the existing BE-1 to BE-12 backend by improving validation scripts, demo mode, regression tests, setup documentation, OpenAPI checks, and observability.

## What BE-13 protects

- BE4.2 reference splitting and DOI attachment quality
- BE-5 DOI metadata lookup and safe failure behavior
- BE-6 claim/citation extraction and mapping
- BE-7 evidence package creation
- BE-8 verification cache safety
- BE-9 RAG/ML integration contract
- BE-10 verification orchestration
- BE-11 safety/confidence rules
- BE-12 report generation, feedback, and UAT APIs

## Demo mode

Use demo/mock mode when real external services are unavailable:

```env
DEMO_MODE=true
METADATA_MOCK_MODE=false
RAG_MOCK_MODE=true
GENAI_MOCK_MODE=true
```

Mock mode is intentionally deterministic. It validates backend orchestration, response contracts, persistence, safety gates, and report generation. It does not prove final AI/RAG answer quality.

## Added scripts

```bash
python scripts/validate_openapi.py
python scripts/run_backend_checks.py
python scripts/reset_demo_db.py
python scripts/run_demo_pipeline.py
python scripts/validate_uploaded_pdfs_be13.py --reset-db <paper1.pdf> <paper2.pdf> <paper3.pdf>
```

## Validation commands

```bash
python -m compileall app scripts/validate_uploaded_pdfs_be13.py scripts/run_demo_pipeline.py scripts/run_backend_checks.py scripts/validate_openapi.py
python scripts/validate_openapi.py
python scripts/init_db.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
```

## Standard response contract

All API endpoints must return the standard wrapper:

```json
{
  "success": true,
  "data": {},
  "message": "Request completed successfully",
  "errors": [],
  "request_id": "req_12345"
}
```

Known errors must return the same wrapper with `success=false` and structured error objects.

## Logging hardening

Structured logs now support workflow identifiers such as `document_id`, `pipeline_run_id`, `claim_id`, `reference_id`, `evidence_package_id`, `retrieval_result_id`, `verification_result_id`, `report_id`, `feedback_id`, and `survey_id` when services pass those fields. Logs must not include secrets, full PDF contents, or full prompts.

## OpenAPI validation

`validate_openapi.py` verifies that the generated FastAPI OpenAPI schema contains the critical public endpoints used by the backend flow. Differences from the manually finalized OpenAPI should be documented in validation notes rather than ignored.

## Limitations

- BE-13 does not implement frontend UI.
- BE-13 does not implement new embedding/vector search algorithms.
- BE-13 does not perform publisher full-text scraping.
- BE-13 does not implement production authentication.
- Mock RAG/GenAI validation proves backend readiness, not final AI-quality.
