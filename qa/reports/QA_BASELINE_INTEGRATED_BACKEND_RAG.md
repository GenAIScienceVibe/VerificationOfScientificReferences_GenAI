# QA Baseline Report — Integrated Backend + RAG

Run date: 2026-06-28 (Asia/Singapore)  
Role: QA Agent — validation only  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`  
Git branch: `integration/backend-rag-merge`  
Git commit: `86d70f20c6088bbdd2f5ad6107c04896e7061f98`  
Final decision: **FAIL**

## Executive baseline

The backend remains stable in mock RAG/mock GenAI mode: compile, the authoritative isolated backend suite (130 tests), OpenAPI validation, backend checks, demo pipeline, and the three-private-PDF BE13 validator passed. Backend BE10/BE11 remains the final verification and safety authority, and mock GenAI does not require real RAG Door 2 imports.

The package is not a validated live Backend + RAG/ML integration. The backend runtime cannot import real RAG, root RAG tests cannot collect, staged real-RAG validation does not exist, metadata-disabled mode still executes title-provider calls, `FOUND` maps unsafely to RAG `VALID`, real RAG ignores backend `top_k`, and real chunk provenance/default/failure contracts are incomplete. Private PDFs and populated runtime artifacts are tracked.

## Scope and constraints

- Read all mandated agent, protocol, runbook, issue-register, and initial-finding files before validation.
- Did not modify production code, tests, or scripts.
- Did not install dependencies or make intentional live external academic/LLM calls.
- Door 2 was inspected and import-probed only; it was not live-executed.
- Real RAG could not be executed because imports fail.

## Commands run and results

### Backend mock-mode baseline

| Command | Result | Evidence |
|---|---|---|
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS | Exit 0. |
| `cd backend && .venv/bin/pytest -q` | PASS on authoritative isolated rerun | A preliminary shared-DB capture was invalidated after overlapping QA runners interfered with the same SQLite test DB. Clean isolated rerun with mock RAG/GenAI and metadata enabled: `130 passed in 77.91s`. |
| `DATABASE_URL=sqlite:////tmp/qa_backend_pytest_enabled.db FILE_STORAGE_DIR=/tmp/qa_backend_uploads_enabled RAG_MOCK_MODE=true GENAI_MOCK_MODE=true METADATA_LOOKUP_ENABLED=true .venv/bin/pytest -q --tb=short` | PASS | 130 passed. This is the authoritative backend-suite result. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS | 45 paths; required endpoint gaps `[]`. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS | Compile/import, 18-table DB initialization, and OpenAPI checks passed. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS | Text→references→claims→evidence→mock verification/safety→report completed; all endpoint calls returned 200. |
| `cd backend && .venv/bin/python scripts/validate_uploaded_pdfs_be13.py --pdf-dir tests/fixtures/private_pdfs` | PASS in mock mode | Exit 0 for all three PDFs; mock RAG/mock GenAI pipeline, reports, feedback, UAT, wrappers, and allowed support labels passed. This did not validate real RAG quality. |
| Isolated `/tmp` rerun of the PDF validator with per-PDF output filtering | PASS | Each named PDF reported `pipeline_status: SUCCEEDED`, `report_generated: True`, `unsupported_labels_found: []`, and `problems_found: []`. |

Backend mock baseline decision: **PASS**, with the explicit limitation that it is mock-only.

### RAG/ML readiness

| Command | Result | Evidence |
|---|---|---|
| `pytest tests/rag -q` from repository root | FAIL / cannot run | Exit 127: `pytest: command not found`. |
| `backend/.venv/bin/pytest tests/rag -q --tb=short` | FAIL | 11 collection errors caused by missing RAG dependencies. |
| `backend/.venv/bin/python -c "from rag.api import retrieve_evidence, verify_claim; print('rag imports ok')"` | FAIL | `ModuleNotFoundError: No module named 'tiktoken'`. |
| Literal backend-folder import requested by QA protocol | FAIL | `ModuleNotFoundError: No module named 'rag'`; backend working directory does not expose the repository-root package until the direct client mutates `sys.path`. |
| `PYTHONPATH=backend ... RagDirectClient(); from rag.api import retrieve_evidence` | FAIL | Package becomes discoverable, then fails on missing `tiktoken`. |
| RAG dependency presence probe in `backend/.venv` | FAIL | Missing `langchain_text_splitters`, `tiktoken`, `openai`, `faiss`, `numpy`, `rank_bm25`, `flashrank`, and `jinja2`. |
| `backend/.venv/bin/python -m pip check` | PASS for installed subset only | No broken installed requirements; this does not mean RAG requirements are installed. |
| Individual retrieval-module imports | FAIL except cleaner | Cleaner imports; chunker, embedder, vector store, BM25, hybrid retriever, and `rag.api` fail on missing dependencies. |
| Door 2 module import probes | FAIL except models | Verification models import; classifier fails on `openai`; verifier and validator fail on `jinja2`. |

RAG readiness decision: **FAIL**. Door 1 and Door 2 are not import-ready in the integrated runtime.

## Area-by-area assessment

### 1. Backend mock mode stability

PASS. Compile, 130 backend tests, OpenAPI, checks, demo pipeline, and three-PDF mock validator passed. All observed final support statuses stayed within the allowed five values. The demo and validator clearly report mock limitations in their output, though integrated README documentation is incomplete.

### 2. RAG/ML package readiness

FAIL. `rag/requirements.txt` declares an apparently broad RAG dependency set, but it is not installed in the backend runtime and no root test environment is provided. RAG tests fail at collection. Door 1 `retrieve_evidence` and Door 2 `verify_claim` cannot import. Retrieval modules are present in source but not runnable in the integration environment.

### 3. Backend-to-RAG integration readiness

FAIL.

- `RAG_MOCK_MODE=true` still works; mock client and mock GenAI instantiate without importing `rag.api`.
- `RAG_MOCK_MODE=false` cannot import real RAG.
- A live real response could not be executed through the backend validator.
- Backend validator enforces nonnegative scores and clamps values over 1 to 1, but live real-score production was not validated. RAG output models do not declare 0–1 bounds for similarity/rerank scores.
- Backend `top_k` is built but not passed to real RAG; fixed `DOOR1_TOP_K=5` is used.
- Real adapter drops `source` and `source_url`.
- Required `semantic_cache_match` default is absent in real responses and validator normalization.
- Direct Python import is the active real path; configured HTTP service settings are unused.

### 4. Metadata-disabled mode

FAIL. The guard blocks DOI-based CrossRef and downstream OpenAlex/Semantic Scholar/SSRN/arXiv/Unpaywall/CORE paths once a DOI is present, but it occurs after title-based DOI resolution. With metadata disabled, the three-PDF run repeatedly invoked/logged CrossRef, OpenAlex, and Semantic Scholar title searches; CORE would also be included when configured. Therefore the requirement that all external metadata/title/full-text calls are blocked is not met.

A controlled disabled-mode backend suite produced `125 passed, 5 failed`; four failures were expected because BE5 tests explicitly exercise mocked enabled metadata behavior, while the document-level captured logs independently reproduced the disabled title-search defect.

### 5. DOI status mapping

FAIL. Runtime mapping probe:

```text
FOUND->VALID
MISSING->UNRESOLVABLE
MALFORMED->INVALID
VALID->VALID
INVALID->INVALID
LOOKUP_FAILED->UNRESOLVABLE
```

Only `VALID->VALID` is acceptable. `FOUND->VALID` is unsafe and appears in both real retrieval and real GenAI adapters. The other requested mappings do not become RAG `VALID`.

### 6. Real-PDF validation

- Mock RAG + mock GenAI: PASS for all three existing PDFs.
- Real RAG + mock GenAI: FAIL / mode absent. Validator has no `--real-rag` flag, explicitly calls `use_mock: true`, and hard-codes mock labels.
- Real RAG + real GenAI: optional flag gating exists through `GENAI_MOCK_MODE=false`, but no accepted validator, dependency-ready runtime, key-readiness check, or clearly reconciled setup documentation exists. Not run and not accepted.

### 7. Door 2 / GenAI safety

PASS for backend ownership in inspected/mock paths, with integration blockers.

- BE10 validates GenAI output against the five allowed statuses and chunk IDs.
- BE11 safety runs after stored real/mock GenAI output and can downgrade/override status and confidence.
- RAG Door 2 is only selected by the backend real GenAI client; it does not persist or return directly to the frontend.
- `GENAI_MOCK_MODE=true` selected `MockGenAiVerificationClient` successfully despite missing RAG dependencies, proving Door 2 is not imported unnecessarily in mock mode.
- Unsafe `FOUND->VALID` is still present in the real Door 2 adapter and must be fixed before live use.

### 8. Full-text pipeline

PARTIAL / NOT ACCEPTED.

- `POST /api/v1/references/{reference_id}/upload-source-pdf` exists in OpenAPI.
- Code exists for uploaded PDF extraction, Unpaywall, arXiv DOI handling, Semantic Scholar/OpenAlex/SSRN fallbacks, CORE full text, and preprint/full-text evidence classification.
- No test covers the upload endpoint or `inject_fulltext_from_uploaded_pdf`.
- No end-to-end test proves upload/provider text → persisted source metadata → `FULL_TEXT_AVAILABLE` evidence package → real RAG retrieval with provenance.
- Existing preprint test proves SSRN abstract classification only, not provider download or real retrieval.

### 9. Documentation and packaging

FAIL.

- Root README is two lines; `rag/README.md` and `tests/README.md` are blank.
- Root `.env.example` contains only LLM key placeholders; backend example defaults to mock RAG/GenAI but does not document the combined RAG install/runtime.
- Backend README still documents HTTP RAG settings and future real GenAI behavior, not the current direct adapters.
- No authoritative setup explains Mode 2 or runs both test suites.
- `backend/.env` and pytest cache are ignored and not tracked.
- Tracked-file scan found all three private PDFs, 17 populated SQLite DBs, and three uploaded PDF artifacts. Nested `backend/data/*.db` and private PDFs are not covered by current ignore rules.

## Contract and safety notes

- Backend remains the source of truth in the inspected orchestration path.
- Mock GenAI/RAG does not bypass BE10/BE11.
- RAG retrieval does not return unsupported final labels; Door 2 uses exactly the allowed five labels.
- Real score normalization is not live-validated. Backend-side clamping protects positive scores above 1, but real RAG schema does not itself enforce 0–1.
- Real RAG `FAILED` responses lack structured error details and can be stored with no error message.

## Findings created

| ID | Severity | Blocking | Status | Summary |
|---|---|---:|---|---|
| INT-QA-001 | P1 | Yes | Open | Real RAG dependency/import readiness |
| INT-QA-002 | P1 | Yes | Open | Metadata-disabled title-provider calls |
| INT-QA-003 | P1 | Yes | Open | Unsafe `FOUND->VALID` DOI mapping |
| INT-QA-004 | P1 | Yes | Open | Real RAG ignores backend `top_k` |
| INT-QA-005 | P2 | No | Open | Undocumented direct Python service boundary |
| INT-QA-006 | P1 | Yes | Open | RAG tests absent from integrated validation |
| INT-QA-007 | P2 | Yes for full-text acceptance | Open | Full-text endpoint/provider/RAG E2E gap |
| INT-QA-008 | P1 | Yes | Open | Staged real-RAG validator missing |
| INT-QA-009 | P2 | Yes for real contract | Open | Real chunk source/source_url loss |
| INT-QA-010 | P2 | No | Open | Real RAG failure details missing |
| INT-QA-011 | P1 | Yes | Open | Tracked private/runtime artifacts |
| INT-QA-012 | P2 | No | Open | Integrated documentation incomplete/stale |
| INT-QA-013 | P2 | Yes for real contract | Open | `semantic_cache_match` default absent |

## Blocking findings

INT-QA-001, INT-QA-002, INT-QA-003, INT-QA-004, INT-QA-006, INT-QA-008, and INT-QA-011 are release-level blockers. INT-QA-007 blocks full-text completion claims; INT-QA-009 and INT-QA-013 block complete backend-facing real-RAG contract acceptance.

## Final QA baseline decision

**FAIL**

The backend mock baseline is healthy, but the merged package must not be described as live RAG/ML integrated or real-PDF real-RAG validated. Revalidation must be performed by a separate Re-validation Agent after fixes; this QA Agent did not fix or approve its own findings.
