# Development Report — Group 2 RAG Contract Safety

Run date: 2026-06-28 (Asia/Singapore)  
Role: Development Agent  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`  
Git branch: `integration/backend-rag-merge`  
Git commit: `86d70f20c6088bbdd2f5ad6107c04896e7061f98`

## Findings addressed

- INT-QA-003 — Unsafe DOI status mapping.
- INT-QA-004 — Real RAG `top_k` handling.
- INT-QA-009 — Real RAG chunk traceability gap.
- INT-QA-010 — Real RAG failure details gap.
- INT-QA-013 — Missing `semantic_cache_match` default.

Backend-facing score normalization was also hardened as explicitly required by
the Group 2 task. No other finding was fixed or closed.

## Root cause

- Door 1 and Door 2 maintained separate DOI maps that treated extracted but
  unverified `FOUND` as RAG `VALID`.
- The backend request contained `retrieval_options.top_k`, but the direct
  adapter did not pass it and Door 1 used a fixed result count of five.
- FlashRank scores were returned without a final range guard, while the backend
  validator treated positive and negative out-of-range scores differently and
  did not reject non-finite values.
- The real adapter serialized chunk text/score/type but dropped the request's
  source identity and URL.
- Mock and real response builders evolved separately, leaving real and skipped
  paths without the stable semantic-cache default.
- Door 1 collapsed failure paths into a bare `FAILED` result, and the backend
  discarded error detail for schema-valid failed responses.

## Files changed

- `backend/app/services/rag_ml_integration.py`
- `backend/app/services/genai_verification.py`
- `rag/api.py`
- `tests/rag/test_api.py`
- `backend/tests/test_be9_rag_ml_integration.py`
- `backend/tests/unit/test_group2_rag_contract_safety.py`
- `qa/reports/DEV_REPORT_GROUP2_RAG_CONTRACT_SAFETY.md`

## Fixes implemented

### DOI safety

- Only backend `VALID` maps to RAG `VALID` in Door 1 and Door 2.
- `FOUND`, `MISSING`, and `LOOKUP_FAILED` map to `UNRESOLVABLE`.
- `MALFORMED` and `INVALID` map to `INVALID`.
- Unknown statuses continue to fail safely as `UNRESOLVABLE`.

### Bounded top_k

- Added `top_k` to `rag.api.RetrieveEvidenceRequest`, default 5, bounded 1–20.
- Door 1 now uses the requested value for dense/BM25 oversampling, hybrid
  merging, and final defensive truncation.
- `RagDirectClient` passes the bounded backend value and defensively limits the
  serialized chunks.
- Backend top-k normalization now safely handles omitted, nonnumeric, below-min,
  and above-max values. Mock and real clients use the same bounds.

### Score safety

- Door 1 normalizes FlashRank and dense fallback scores to finite 0–1 values
  before computing chunk, overall, and confidence scores.
- The backend validator consistently clamps negative and above-one finite
  values, logs normalization, and rejects non-finite values.
- No weighted internal score above one can be persisted as a backend-facing
  score.

### Chunk provenance

- Real-adapter chunks now include a stable source label and a source URL when a
  safe public HTTP(S) URL is available.
- File paths, credential-bearing URLs, localhost, `.local`, and private,
  loopback, link-local, or reserved IP URLs are removed before persistence.
- Evidence type remains unchanged.

### Semantic-cache default

- Successful, failed, mock, real, skipped, validation-failure, exception, and
  persisted-result paths now use:

  ```json
  {"matched": false, "cached_result_id": null, "similarity": null}
  ```

- Existing real semantic-cache matches remain validated and persisted.

### Safe failure details

- Door 1 returns stable safe detail for unusable DOI, missing/empty evidence,
  empty chunks, embedding failure, no relevant evidence, preprocessing failure,
  and internal retrieval failure.
- Exception type may be logged, but raw exception text is not returned.
- Backend validation sanitizes sensitive-key/token patterns, bounds detail
  length, and persists safe detail for non-success real results.

No final route shape, support-status enum, mock-mode behavior, BE4.2 extraction,
BE10/BE11 safety authority, direct service-boundary choice, PDF validator,
full-text provider pipeline, or packaging behavior was changed.

## Tests added or updated

- Table-driven Door 1 and Door 2 tests for all six backend DOI statuses.
- RAG and real-adapter tests for `top_k=1`, `top_k=3`, omitted/default, invalid,
  and out-of-range values, plus mock/real bounds consistency.
- RAG and backend-validator tests for negative, above-one, and non-finite scores.
- Successful and failed real-adapter validator compatibility tests.
- Provenance tests for source/source URL, private file paths, loopback URLs, and
  database persistence.
- Semantic-cache default tests for success, failure, empty/skip, mock, real,
  validation-error, and persistence paths.
- Safe failure-detail tests for unusable DOI, empty source, empty chunks,
  embedding failure, internal failure, secret redaction, and persistence.
- Existing tests were retained; no assertion was weakened or removed.

## Commands run

| Command | Result |
|---|---|
| `backend/.venv/bin/python -m pytest tests/rag/test_api.py -q --tb=short` | PASS — 28 passed. |
| `cd backend && .venv/bin/pytest -q tests/unit/test_group2_rag_contract_safety.py tests/test_be9_rag_ml_integration.py --tb=short` | PASS — 41 passed in 24.69s. |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | PASS — 365 passed in 1.60s. |
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS. |
| `cd backend && .venv/bin/pytest -q` | PASS — 168 passed in 103.89s. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS — 45 paths; required endpoint gaps `[]`. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS — demo completed; endpoint calls returned 200. |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | PASS — backend 168 passed, RAG 365 passed, every check PASS, `INTEGRATED_VALIDATION_RESULT=PASS`. |
| Preliminary extra compile probe using `backend/.venv/bin/python` while already in `backend/` | Could not run — exit 127 because that relative path became `backend/backend/.venv/bin/python`; corrected compile commands above passed. |

## Pass/fail result

**PASS.** Focused contract tests, complete RAG and backend suites, OpenAPI,
backend checks, demo, real-RAG import gate, and the integrated runner passed.

## Remaining risks

- Real embedding and LLM network calls were not made; contract behavior was
  validated deterministically with mocks and the dependency-ready real adapter.
- A staged real-RAG PDF validation mode remains a separate finding and was not
  implemented.
- Full-text upload/provider end-to-end validation, the direct Python service
  boundary decision, documentation/packaging, and private-artifact handling
  remain outside this group.
- Full-text provenance can only use the evidence availability and safe URL
  supplied by the current backend contract; it does not infer provider origin.
- The five finding files remain Open pending independent QA re-validation.

## Ready for QA revalidation

**Yes.**
