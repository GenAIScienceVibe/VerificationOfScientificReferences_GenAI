# QA Re-validation Report — Group 1 Environment, Metadata Disabled Mode, and RAG Test Integration

Run date: 2026-06-28 (Asia/Singapore)  
Role: QA Re-validation Agent — validation only  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`  
Git branch: `integration/backend-rag-merge`  
Git commit: `86d70f20c6088bbdd2f5ad6107c04896e7061f98`  
Final decision: **FAIL**

## Scope and constraints

Revalidated only INT-QA-001, INT-QA-002, and INT-QA-006. No production code,
tests, or scripts were modified, and no fixes were attempted. Other findings
were not revalidated or closed. No live embedding, metadata-provider, or GenAI
calls were made.

## Commands run

| Command | Result |
|---|---|
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS — exit 0. |
| `cd backend && .venv/bin/pytest -q` | PASS — 138 passed in 87.48s. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS — 45 paths; required endpoint gaps `[]`. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS — compile/import, 18-table initialization, and OpenAPI checks passed. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS — all pipeline endpoint calls returned 200 and the report completed. |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | FAIL as required by the exposed RAG defect — all backend/import checks passed; RAG pytest reported 1 failed and 352 passed; exit 1 and `INTEGRATED_VALIDATION_RESULT=FAIL`. |
| `backend/.venv/bin/python -c "from rag.api import retrieve_evidence, verify_claim; print('rag imports ok')"` | PASS — `rag imports ok`. |
| `PYTHONPATH=backend RAG_MOCK_MODE=false GENAI_MOCK_MODE=true backend/.venv/bin/python -c "from app.services.rag_ml_integration import RagDirectClient; RagDirectClient(); from rag.api import retrieve_evidence; print('real rag import ok')"` | PASS — `real rag import ok`. |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | FAIL — 1 failed, 352 passed; exact failure was the cross-DOI cache-isolation test. |
| Import probe with `OPENROUTER_API_KEY` removed | PASS — Door 1 and Door 2 symbols imported without an API key. |
| `RAG_MOCK_MODE=false GENAI_MOCK_MODE=true` client probe with `OPENROUTER_API_KEY` removed | PASS — `RagDirectClient` initialized and GenAI selected `MockGenAiVerificationClient`; real Door 2 was not constructed. |
| Focused metadata-disabled tests for DOI and no-DOI references | PASS — 2 passed in 1.81s. |
| `cd backend && .venv/bin/pytest -q tests/unit/test_integrated_rag_checks.py` | PASS — 6 passed in 3.70s. |
| `cd backend && .venv/bin/python -m pip check` | PASS — no broken requirements found. |

## INT-QA-001 — Fixed and closed

- `requirements-integrated.txt` exists and includes both
  `backend/requirements.txt` and `rag/requirements.txt`.
- Root and backend-direct RAG import probes passed with no API key.
- Documentation provides the combined installation and import commands.
- Mock GenAI selection did not construct the real Door 2 client.
- The root RAG suite collected and ran 353 tests. Its one functional failure is
  outside dependency/import readiness and is recorded separately as INT-QA-014.

Result: **FIXED — CLOSED**.

## INT-QA-002 — Fixed and closed

- Inspection confirms title lookup is gated by
  `metadata_lookup_enabled` before the provider search chain.
- Strict fail-on-call spies cover CrossRef title/DOI, OpenAlex title/DOI,
  Semantic Scholar title/DOI/arXiv, CORE title/full text, Unpaywall, SSRN, DOI
  resolver, and external PDF/full-text extraction.
- Both disabled-mode scenarios passed and proved zero external provider calls.
- The enabled/default backend regression suite passed all 138 tests.

Result: **FIXED — CLOSED**.

## INT-QA-006 — Fixed and closed

- The integrated runner exists and runs backend validation plus `tests/rag`.
- Focused tests prove missing imports become `BLOCKED`, gate the RAG suite, and
  return exit code 2 rather than passing silently.
- Focused tests prove any required test failure makes the aggregate result
  `FAIL` with exit code 1.
- The actual run exposed the existing RAG test failure and ended in `FAIL`.

Result: **FIXED — CLOSED**.

## New issue detection

INT-QA-014 was created: **RAG source embedding cache reuses across different
DOIs**. The exact regression test failed because two different DOI requests
produced only one source-chunk embedding call (`assert 1 == 2`). It is P1,
blocking, and Open.

## Overall integrated validation result

**FAIL.** The Group 1 findings are fixed, but the integrated test surface is red
because INT-QA-014 is confirmed. Other findings were deliberately left unchanged
and retain their existing status.

## Final QA decision

**FAIL**

Do not approve the full integrated release while INT-QA-014 or any other
blocking finding remains open.
