# QA Re-validation Report — Group 2 RAG Contract Safety

Run date: 2026-06-28 (Asia/Singapore)  
Role: QA Re-validation Agent — validation only  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`  
Git branch: `integration/backend-rag-merge`  
Git commit: `86d70f20c6088bbdd2f5ad6107c04896e7061f98`  
Final decision: **FAIL**

## Scope and constraints

Revalidated only INT-QA-003, INT-QA-004, INT-QA-009, INT-QA-010, and
INT-QA-013. No production code, tests, or scripts were modified, and no fix was
attempted. Real-PDF validation, the full-text pipeline, documentation,
packaging, the direct Python service boundary, BE4.2, and unrelated BE10/BE11
behavior were not revalidated or changed.

## Executive result

- INT-QA-003: **Fixed and closed**.
- INT-QA-004: **Fixed and closed**.
- INT-QA-009: **Fixed and closed**.
- INT-QA-010: **Not fixed; remains Open**.
- INT-QA-013: **Fixed and closed**.
- Automated integrated runner: **PASS** with
  `INTEGRATED_VALIDATION_RESULT=PASS`.
- Group 2 QA re-validation: **FAIL** because INT-QA-010 still permits raw
  traceback/local-path and generic token details to reach persistence.

## Commands run

| Command | Result |
|---|---|
| `backend/.venv/bin/python -m pytest tests/rag/test_api.py -q --tb=short` | PASS — 28 passed in 0.93s. |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | PASS — 365 passed in 1.55s. |
| `backend/.venv/bin/python -m compileall -q rag` | PASS. |
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS. |
| `cd backend && .venv/bin/pytest -q tests/unit/test_group2_rag_contract_safety.py tests/test_be9_rag_ml_integration.py --tb=short` | PASS — 41 passed in 25.07s. |
| `cd backend && .venv/bin/pytest -q` | PASS — 168 passed in 106.64s. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS — 45 paths; required endpoint gaps `[]`. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS — compile/import, 18-table initialization, and OpenAPI checks passed. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS — demo completed and all endpoint calls returned 200. |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | PASS — backend 168 passed, RAG 365 passed, all checks PASS, `INTEGRATED_VALIDATION_RESULT=PASS`. |
| `cd backend && .venv/bin/python -c "<Door 1/Door 2 mapping, source URL, and failed-response sanitization probes>"` | MIXED — mapping and URL probes passed; raw traceback/path and generic token probes were returned unchanged. |

## INT-QA-003 — DOI status mapping

**Fixed.** The focused tests and an independent runtime probe confirmed the
same mapping in Door 1 and Door 2:

| Backend status | RAG status |
|---|---|
| `VALID` | `VALID` |
| `FOUND` | `UNRESOLVABLE` |
| `MISSING` | `UNRESOLVABLE` |
| `LOOKUP_FAILED` | `UNRESOLVABLE` |
| `MALFORMED` | `INVALID` |
| `INVALID` | `INVALID` |

An unknown status falls back to `UNRESOLVABLE` in both adapters. Only backend
`VALID` can become RAG `VALID`; no unverified known or unknown status reaches
the valid path. The finding file was closed and set to
`Blocking: No / Resolved`.

## INT-QA-004 — top_k and score contract

**Fixed.** Evidence from focused backend and RAG API tests confirms:

- `top_k=1` and `top_k=3` propagate and bound returned chunks;
- omitted `top_k` defaults to 5;
- below-minimum backend requests clamp to 1;
- above-maximum backend requests clamp to 20;
- mock and real-adapter paths share the bound;
- Door 1 uses the requested limit for dense/BM25 candidates, hybrid merge,
  and final truncation.

Finite scores above 1 clamp to 1, negative scores clamp to 0, and non-finite
backend-facing scores are rejected. Door 1 chunk, overall, and aggregate
confidence scores remain finite and in the 0–1 range. The finding file was
closed and set to `Blocking: No / Resolved`.

## INT-QA-009 — chunk provenance

**Fixed.** A safe public DOI URL and stable source label survive real-adapter
validation and database persistence. Independent URL probes confirmed that
file URLs, localhost, loopback/private IP addresses, credential-bearing URLs,
and `.local` hosts are removed. Focused tests also prove that local file paths
are not exposed in serialized chunk provenance. The finding file was closed
and set to `Blocking: No / Resolved`.

## INT-QA-010 — real RAG failure details

**Not fixed.** Standard Door 1 paths now return stable, safe messages for
unusable DOI, missing/empty source, empty chunks, embedding failure, no
relevant chunks, preprocessing failure, and internal retrieval failure. The
focused suites also prove that an API-key-shaped error is replaced before
persistence.

However, the independent adversarial validator probe returned both values
unchanged:

```text
Traceback: File /home/user/private/service.py line 42
upstream token=dummy-private-value
```

`RagRetrievalService` then passes `validated.get("error_message")` directly to
`_store_result`, so the unchanged detail would be persisted. The sanitizer
does not currently recognize raw traceback/local-path patterns or a generic
`token=...` credential pattern. This fails the explicit requirement that
persisted failure detail contain no secrets, local paths, or raw stack data.
The finding remains `Status: Open`; it was not closed and no fix was attempted.

## INT-QA-013 — semantic_cache_match default

**Fixed.** The exact default below is supplied on successful, failed, skipped,
validation-error, exception, mock, real-adapter, returned-result, and persisted
paths:

```json
{"matched": false, "cached_result_id": null, "similarity": null}
```

A supplied valid semantic-cache match is validated and preserved rather than
being overwritten. The finding file was closed and set to
`Blocking: No / Resolved`.

## Regression and integrated validation

- Backend regression: **PASS** — compile, 168 tests, OpenAPI validation,
  backend checks, and demo pipeline.
- RAG regression: **PASS** — compile, 28 API tests, and all 365 RAG tests.
- Integrated runner: **PASS** — all declared checks passed and the aggregate
  result was `INTEGRATED_VALIDATION_RESULT=PASS`.
- Generated database/OpenAPI artifacts were restored after validation.

The runner's PASS reflects its current automated gates; it does not cover the
adversarial INT-QA-010 traceback/local-path and generic-token scenario and
therefore does not override this QA failure.

## Finding-file disposition

| Finding | Result | File disposition |
|---|---|---|
| INT-QA-003 | Fixed | Closed; Blocking No / Resolved |
| INT-QA-004 | Fixed | Closed; Blocking No / Resolved |
| INT-QA-009 | Fixed | Closed; Blocking No / Resolved |
| INT-QA-010 | Not fixed | Remains Open; closure note records failed probe |
| INT-QA-013 | Fixed | Closed; Blocking No / Resolved |

No unrelated finding was modified or closed.

## Remaining risks

- INT-QA-010 remains open because untrusted failed-response detail can expose
  local paths, raw traceback content, or generic token values in persistence.
- Real embedding/LLM network calls were not made; deterministic contract tests
  exercised real-adapter orchestration without external credentials.
- Other open blocking findings outside this Group 2 scope remain untouched.
  This report does not approve the full integrated release.

## Final decision

**FAIL**
