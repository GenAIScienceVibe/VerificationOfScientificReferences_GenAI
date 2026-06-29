# QA Re-validation Report — INT-QA-010 Failure Detail Sanitization

Run date: 2026-06-28 (Asia/Singapore)  
Role: QA Re-validation Agent — validation only  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`  
Git branch: `integration/backend-rag-merge`  
Git commit: `86d70f20c6088bbdd2f5ad6107c04896e7061f98`  
Final decision: **PASS**

## Scope and constraints

Revalidated only INT-QA-010. No production code, tests, or scripts were
modified, and no fix was attempted. DOI mapping, top-k, score normalization,
provenance, semantic-cache behavior, Door 2, full-text, documentation,
packaging, service-boundary, BE4.2, BE10, BE11, and all other findings were not
revalidated or changed.

## Commands run

| Command | Result |
|---|---|
| Independent 14-case unsafe-message validator probe | PASS — all 14 became exactly `RAG retrieval did not return usable evidence.` |
| Independent safe-message, multiline, and length probe | PASS — all three approved messages were unchanged; safe multiline text was normalized; long detail was bounded to 500 characters. |
| Independent in-memory persistence probe across all 14 unsafe messages, success, `AppException`, and validator-error paths | PASS — returned/stored/payload details were safe, successful detail was `None`, and persisted forbidden fragments were `[]`. |
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS. |
| `cd backend && .venv/bin/pytest -q tests/unit/test_group2_rag_contract_safety.py tests/test_be9_rag_ml_integration.py --tb=short` | PASS — 63 passed in 38.15s. |
| `cd backend && .venv/bin/pytest -q` | PASS — 190 passed in 120.42s. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS — 45 paths; required endpoint gaps `[]`. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS — compile/import, 18-table initialization, and OpenAPI checks passed. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS — demo completed; endpoint calls returned 200. |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | PASS — backend 190 passed, RAG 365 passed, every check PASS, `INTEGRATED_VALIDATION_RESULT=PASS`. |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | PASS — 365 passed in 1.48s. |

## INT-QA-010 result

**Fixed.** Independent QA reproduced the complete expected behavior at both
validation and persistence boundaries.

## Evidence

### Unsafe-message replacement

Each of the following became exactly
`RAG retrieval did not return usable evidence.`:

- raw traceback text;
- generic `token=...` detail;
- Linux `/home/...` path;
- macOS `/Users/...` path;
- Windows `C:\Users\...` path;
- `file://` URL;
- authorization/bearer value;
- access token and refresh token values;
- API key, password, and secret values;
- `sk-` style key;
- multiline traceback/exception dump.

### Safe behavior preservation

These approved messages remained unchanged:

- `No relevant evidence chunks were found.`
- `Source evidence is unavailable or empty.`
- `Embedding service failed while preparing retrieval vectors.`

Safe multiline detail was normalized to one line, and a 600-character safe
detail was bounded to exactly 500 characters.

### Persistence boundaries

- For every one of the 14 unsafe messages, a failed real-RAG response returned
  the approved fallback and stored that fallback in both
  `RagRetrievalResult.error_message` and
  `RagRetrievalResult.response_payload_json["error_message"]`.
- An unsafe `AppException` detail was sanitized before database storage.
- An unsafe validator/invalid-response detail was sanitized before database
  storage and before `AppException.error.detail` was returned.
- A successful real-adapter retrieval persisted `error_message=None` in the
  returned result, database column, and stored response payload.
- A database-wide probe found none of these fragments in persisted error
  fields or response payloads: traceback, local path, file URL, token/API-key,
  authorization/bearer, password, secret, or `sk-` key markers.

## Finding-file disposition

`qa/findings/INT-QA-010_REAL_RAG_FAILURE_DETAILS.md` was updated to
`Status: Closed` and `Blocking: No / Resolved` with the requested closure note.
No other finding file was modified or closed.

## Backend regression result

**PASS.** Backend compile, all 190 tests, OpenAPI validation, backend checks,
and the demo pipeline passed.

## RAG regression result

**PASS.** All 365 RAG tests passed. No RAG code or RAG test was modified during
re-validation.

## OpenAPI/check/demo result

**PASS.** OpenAPI retained 45 paths with no required endpoint gaps, backend
checks completed successfully, and the demo completed with successful endpoint
responses.

## Integrated runner result

**PASS.** The runner independently repeated backend and RAG validation and
returned `INTEGRATED_VALIDATION_RESULT=PASS`.

## Remaining risks

- Sanitization intentionally favors safe generic persistence over retaining
  diagnostic specificity for suspicious details.
- Validation used deterministic clients and an isolated in-memory database;
  no live embedding or LLM network call was required or made.
- Other blocking findings outside INT-QA-010 remain open and untouched. This
  report closes only INT-QA-010 and does not approve the full integrated
  release.

## Final decision

**PASS**
