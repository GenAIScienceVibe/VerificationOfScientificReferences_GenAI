# Fixing Report — INT-QA-014 RAG Cache Isolation

Run date: 2026-06-28 (Asia/Singapore)  
Role: Fixing Agent  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`

## Finding addressed

INT-QA-014 — RAG source embedding cache reuses across different DOIs.

No other finding was fixed or closed.

## Root cause

`rag.api` keeps source embeddings in the module-level `_embedding_cache`. Its
key was `request.reference_id or request.doi`, so `reference_id` took precedence
whenever present. Reusing a reference ID therefore reused its cached
`EmbedderOutput` even when the DOI or source evidence changed. The key did not
normalize DOI values and did not contain source URL, evidence availability, or
a source-text fingerprint.

The embedding, vector-store, BM25, and hybrid-retrieval modules do not contain
another cross-request source cache; their indexes and retrieval state are built
per call. The unsafe reuse was isolated to `rag/api.py`.
The requested `rag/embedding/` path does not exist in this package; the active
embedding implementation is `rag/retrieval/embedder.py`.

## Files changed

- `rag/api.py`
- `tests/rag/test_api.py`
- `qa/reports/FIX_REPORT_INT_QA_014_RAG_CACHE_ISOLATION.md`

## Fix implemented

- Replaced the string cache key with a frozen `_EmbeddingCacheKey` containing:
  - normalized DOI;
  - backend `reference_id`;
  - source URL;
  - evidence availability;
  - SHA-256 fingerprint of the source text.
- Normalized DOI whitespace, case, `doi:` prefixes, and common `doi.org` /
  `dx.doi.org` resolver prefixes for deterministic cache identity.
- Preserved cache reuse only when normalized DOI, source identity, evidence
  availability, and exact source text all match.
- Preserved the existing in-memory cache and embedding pipeline. No network
  calls or API-key requirements were introduced.
- Did not change DOI status mapping, top-k behavior, score handling,
  traceability, semantic cache behavior, Door 2, backend safety, mock mode, or
  API contracts.

## Tests added or updated

- Kept the original failing assertion and confirmed different DOI values with
  the same `reference_id` cause two source-embedding calls.
- Retained the existing same-DOI/same-source cache-reuse test.
- Added parameterized functional coverage proving:
  - same DOI plus different source text does not reuse;
  - different DOI plus different source text does not reuse;
  - DOI case and resolver-prefix variants normalize to the same key;
  - same DOI plus different source URL does not reuse;
  - same DOI plus different evidence availability does not reuse.

## Commands run

| Command | Result |
|---|---|
| Pre-fix exact failing test | FAIL reproduced — `assert 1 == 2`; 1 failed. |
| `backend/.venv/bin/python -m pytest tests/rag/test_api.py::test_retrieve_evidence_does_not_reuse_cache_across_different_dois -q --tb=short` | PASS — 1 passed. |
| `backend/.venv/bin/python -m pytest tests/rag/test_api.py -q --tb=short` | PASS — 21 passed. |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | PASS — 358 passed in 1.57s. |
| `backend/.venv/bin/python -m compileall -q rag` | PASS. |
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS. |
| `cd backend && .venv/bin/pytest -q` | PASS — 138 passed in 87.38s. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS — 45 paths; required endpoint gaps `[]`. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS — demo completed and endpoint calls returned 200. |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | PASS — backend 138 passed, RAG 358 passed, all checks PASS, `INTEGRATED_VALIDATION_RESULT=PASS`. |

## Pass/fail result

**PASS.** The exact INT-QA-014 scenario, all cache-key cases, the full RAG
suite, backend regression suite, OpenAPI/check/demo commands, and integrated
runner passed.

## Remaining risks

- The cache remains process-local and unbounded, matching the existing design;
  cache lifecycle or size limits were outside INT-QA-014.
- The text fingerprint is intentionally exact. Harmless formatting differences
  produce a safe cache miss rather than risking unsafe reuse.
- Live embedding/API calls were not required and were not made; tests use the
  existing deterministic embedding mocks.
- Other integrated QA findings remain unchanged and must be handled in their
  own fixing and re-validation cycles.
- INT-QA-014 remains Open until an independent Re-validation Agent closes it.

## Ready for QA revalidation

**Yes.**
