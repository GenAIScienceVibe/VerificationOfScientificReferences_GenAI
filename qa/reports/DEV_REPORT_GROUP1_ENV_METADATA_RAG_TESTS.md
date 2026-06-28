# Development Report — Group 1 Environment, Metadata Disabled Mode, and RAG Test Integration

Run date: 2026-06-28 (Asia/Singapore)  
Role: Development Agent  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`

## Findings addressed

- INT-QA-001 — Real RAG dependency and import readiness.
- INT-QA-002 — Metadata-disabled external call blocker.
- INT-QA-006 — RAG tests missing from integrated validation.

No other finding was fixed. DOI mapping, real RAG `top_k`, score normalization,
chunk provenance, `semantic_cache_match`, Door 2 behavior, BE4.2 extraction, and
BE10/BE11 safety behavior were not changed.

## Root cause

### INT-QA-001

Backend and RAG dependencies were split across two manifests with no combined
installation path for the active direct-Python adapter. After installing the RAG
packages, `rag.api` still attempted to load/download tiktoken's `cl100k_base`
asset during module import because the tokenizer was constructed globally.

### INT-QA-002

`MetadataLookupService._verify_reference` invoked CrossRef/OpenAlex/Semantic
Scholar/optional CORE title search before evaluating
`METADATA_LOOKUP_ENABLED=false`. DOI-based provider paths were already behind the
later guard.

### INT-QA-006

`backend/pytest.ini` intentionally discovers backend tests only, and no combined
runner invoked both backend and root RAG validation. A green backend suite could
therefore hide RAG collection or test failures.

## Files changed

- `requirements-integrated.txt`
- `README.md`
- `backend/README.md`
- `backend/app/services/doi_metadata_lookup.py`
- `backend/scripts/run_integrated_rag_checks.py`
- `backend/tests/test_be5_metadata_lookup.py`
- `backend/tests/unit/test_integrated_rag_checks.py`
- `rag/ingestion/chunker.py`
- `qa/reports/DEV_REPORT_GROUP1_ENV_METADATA_RAG_TESTS.md`

The ignored `backend/.venv` was populated from the new integrated manifest for
validation; it is not a source-file change.

## Fixes implemented

### INT-QA-001

- Added a root combined requirements manifest that includes both existing
  dependency files without duplicating or changing their pins.
- Documented exact creation/install/import commands for `backend/.venv`.
- Installed the combined dependency set and verified `pip check`.
- Made tiktoken construction lazy. Importing Door 1/Door 2 no longer downloads a
  tokenizer asset or requires `OPENROUTER_API_KEY`; tokenization behavior remains
  `cl100k_base` and is unchanged once called.
- Confirmed mock GenAI still selects `MockGenAiVerificationClient` without real
  Door 2 construction.

### INT-QA-002

- Gated title-based DOI resolution on `metadata_lookup_enabled` before any title
  provider can be called.
- Preserved existing local missing/malformed handling, cached-metadata behavior,
  and controlled `METADATA_SERVICE_UNAVAILABLE` handling for valid DOI lookup.
- Added strict spies for CrossRef, OpenAlex, Semantic Scholar, CORE, Unpaywall,
  SSRN, arXiv-related Semantic Scholar calls, DOI resolver use, and external PDF
  download.
- Covered both a reference with a DOI and a titled reference without a DOI.

### INT-QA-006

- Added `run_integrated_rag_checks.py` covering backend compile/import, backend
  pytest, OpenAPI, backend checks, demo pipeline, real RAG import, and root RAG
  pytest.
- Added explicit per-check and aggregate `PASS`, `FAIL`, and `BLOCKED` states.
- Missing import dependencies yield `BLOCKED` and prevent a misleading RAG-test
  pass; actual test failures yield `FAIL`.
- Preserved the invoked virtual-environment interpreter path rather than resolving
  its symlink to the system Python.

## Tests added or updated

- Two metadata-disabled regression tests with fail-on-call provider/PDF spies.
- Integrated requirements-manifest test.
- Integrated check-plan coverage test.
- Missing-dependency `BLOCKED` classification test.
- RAG-suite blocked-gate behavior test.
- Aggregate required-check failure test.
- Mock GenAI client-selection regression test.

## Commands run and results

| Command | Result |
|---|---|
| `backend/.venv/bin/python -m pip install -r requirements-integrated.txt` | Initial sandbox run failed on blocked DNS; approved network retry PASS. |
| `backend/.venv/bin/python -m pip check` | PASS — no broken requirements. |
| `backend/.venv/bin/python -c "from rag.api import retrieve_evidence, verify_claim; print('rag imports ok')"` | PASS. |
| `PYTHONPATH=backend RAG_MOCK_MODE=false GENAI_MOCK_MODE=true backend/.venv/bin/python -c "from app.services.rag_ml_integration import RagDirectClient; RagDirectClient(); from rag.api import retrieve_evidence; print('real rag import ok')"` | PASS. |
| Focused Group 1 backend tests | PASS — 8 passed. |
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS. |
| `cd backend && .venv/bin/pytest -q` | PASS — 138 passed. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS — 45 paths, no required gaps. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS. |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | FAIL — 352 passed, 1 failed. Dependencies/import/collection succeeded; remaining failure is `test_retrieve_evidence_does_not_reuse_cache_across_different_dois`. |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | Correctly reported `INTEGRATED_VALIDATION_RESULT=FAIL`: all backend/import checks PASS; RAG pytest FAIL with the same 352/1 result. |

The first cold-cache RAG test attempt additionally showed 39 tokenizer failures
under blocked DNS. After the one-time approved `cl100k_base` asset download, only
the cache-isolation failure remained.

## Pass/fail result

- INT-QA-001 implementation checks: PASS.
- INT-QA-002 regression and enabled-mode backend suite: PASS.
- INT-QA-006 runner behavior: PASS; it exposes the existing RAG failure.
- Overall integrated validation: FAIL because one out-of-scope RAG cache-safety
  test remains failing.

## Remaining risks

- `tests/rag/test_api.py::test_retrieve_evidence_does_not_reuse_cache_across_different_dois`
  fails: two requests with different DOI values reuse cached source embeddings.
  This is a cache/DOI safety concern, was not introduced by Group 1, and was not
  fixed because the user explicitly limited this development pass.
- First tokenization in a clean environment may require network access to obtain
  tiktoken's declared `cl100k_base` asset; imports themselves are now offline.
- Live real-RAG retrieval with an API key was not requested or executed.
- All non-Group-1 QA findings remain open for their own fixing cycles.

## Ready for QA revalidation

**Yes — for INT-QA-001, INT-QA-002, and INT-QA-006.** Overall integrated release
acceptance remains **No** until the separately scoped cache-safety failure and
other open findings are addressed and independently revalidated.
