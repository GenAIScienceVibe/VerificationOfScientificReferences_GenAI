# QA Re-validation Report — INT-QA-014 RAG Cache Isolation

Run date: 2026-06-28 (Asia/Singapore)  
Role: QA Re-validation Agent — validation only  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`  
Git branch: `integration/backend-rag-merge`  
Git commit: `86d70f20c6088bbdd2f5ad6107c04896e7061f98`  
Final decision: **PASS**

## Scope and constraints

Revalidated only INT-QA-014. No production code, tests, or scripts were
modified, and no fix was attempted. DOI mapping, top-k, score normalization,
traceability, semantic cache behavior, Door 2, full-text, documentation, and
packaging findings were not revalidated or changed.

## Commands run

| Command | Result |
|---|---|
| `backend/.venv/bin/python -m pytest tests/rag/test_api.py::test_retrieve_evidence_does_not_reuse_cache_across_different_dois -q --tb=short` | PASS — 1 passed in 0.92s. |
| `backend/.venv/bin/python -m pytest tests/rag/test_api.py -q --tb=short` | PASS — 21 passed in 0.91s. |
| Focused seven-case cache-key run with named pytest parameters | PASS — 7 passed in 0.88s. |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | PASS — 358 passed in 1.64s. |
| `backend/.venv/bin/python -m compileall -q rag` | PASS. |
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS. |
| `cd backend && .venv/bin/pytest -q` | PASS — 138 passed in 87.67s. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS — 45 paths; required endpoint gaps `[]`. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS — compile/import, 18-table initialization, and OpenAPI checks passed. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS — demo completed; all endpoint calls returned 200. |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | PASS — backend 138 passed, RAG 358 passed, every check PASS, exit 0, `INTEGRATED_VALIDATION_RESULT=PASS`. |

## INT-QA-014 result

**Fixed.** Inspection confirms `_EmbeddingCacheKey` binds:

- normalized DOI;
- reference ID;
- source URL;
- evidence availability;
- SHA-256 source-text fingerprint.

The key is frozen and deterministic. DOI normalization strips whitespace and
common `doi:`, `doi.org`, and `dx.doi.org` resolver prefixes, then applies
case-folding. Cache reuse occurs only when the complete key matches.

## Evidence

- Different DOI values with the same `reference_id`: PASS; two source-embedding
  calls, so no cross-DOI reuse.
- Same DOI, source text, URL, reference ID, and evidence type: PASS; cached
  source embeddings were reused.
- Same DOI with different source text: PASS; no reuse.
- Same DOI with different source URL: PASS; no reuse.
- Same DOI with different evidence availability: PASS; no reuse.
- DOI case and resolver-prefix variants: PASS; normalized to the same key.
- Full `rag.api` surface: 21 passed.
- Full RAG regression: 358 passed.
- Backend regression: 138 passed, plus OpenAPI/check/demo commands.
- Integrated validation: every required check passed and the aggregate result
  was `INTEGRATED_VALIDATION_RESULT=PASS`.

## Finding-file disposition

`qa/findings/INT-QA-014_RAG_CACHE_REUSES_ACROSS_DIFFERENT_DOIS.md` was updated
to `Status: Closed` and `Blocking: No / Resolved` with the requested closure
note.

SHA-256 comparison confirmed that every other `qa/findings/INT-QA-*.md` file was
unchanged during this re-validation.

## Backend regression result

**PASS.** Backend compile, 138 tests, OpenAPI validation, backend checks, and
the demo pipeline passed. Generated DB/OpenAPI artifacts were restored after
validation.

## RAG regression result

**PASS.** The original defect scenario, all seven focused cache cases, all 21
`rag.api` tests, and the full 358-test RAG suite passed.

## Integrated runner result

**PASS.** Exit code 0 with `INTEGRATED_VALIDATION_RESULT=PASS`.

## Remaining risks

- The in-memory embedding cache remains process-local and unbounded; lifecycle
  and size limits are outside INT-QA-014.
- Exact text hashing intentionally converts harmless text differences into safe
  cache misses rather than risking unsafe reuse.
- No live embedding API call was required or made; deterministic mocks exercise
  the cache orchestration logic directly.
- Other QA findings remain outside this re-validation. This PASS closes only
  INT-QA-014 and does not approve the full integrated release.

## Final decision

**PASS**
