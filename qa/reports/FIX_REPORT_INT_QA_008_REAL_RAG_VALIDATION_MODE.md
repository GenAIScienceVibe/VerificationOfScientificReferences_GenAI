# Fixing Report — INT-QA-008 Real RAG Validation Mode

Date: 2026-06-28  
Role: Fixing Agent  
Finding: INT-QA-008 — No staged real-RAG + mock-GenAI PDF validation mode exists  
Result: PASS  
Ready for QA revalidation: Yes

## Finding addressed

INT-QA-008 only. No finding file was closed or edited, and no unrelated production behavior was changed.

## Root cause

`backend/scripts/validate_uploaded_pdfs_be13.py` configured mock modes during module import, hard-coded `use_mock: true` for the BE9 retrieval request, and hard-coded `Mock RAG` / `Mock GenAI` labels. It therefore could not select or prove the real `RagDirectClient` path while retaining deterministic GenAI verification.

## Files changed

- `backend/scripts/validate_uploaded_pdfs_be13.py`
- `backend/tests/unit/test_real_rag_pdf_validation_mode.py`
- `qa/reports/FIX_REPORT_INT_QA_008_REAL_RAG_VALIDATION_MODE.md`

No production application module, API route shape, private PDF, RAG algorithm, safety policy, DOI mapping, cache logic, or packaging rule was modified.

## Validation mode added/updated

The uploaded-PDF validator now supports:

1. `Mock RAG + Mock GenAI` — existing offline behavior remains the default.
2. `Real RAG + Mock GenAI` — required staged mode. The backend uses its real request builder, `RagDirectClient`, RAG contract models, response transformation, BE9 validator, database persistence, verification orchestration, mock GenAI, BE10/BE11 processing, reporting, feedback, and UAT paths. Door 1 output is deterministic and offline, and the output explicitly labels this as `real RagDirectClient adapter with deterministic Door 1 boundary`; it is not presented as fully live retrieval quality validation.
3. `Real RAG + Real GenAI` — optional and guarded by `OPENROUTER_API_KEY`.
4. `Real RAG + live external embeddings` — optional and separately guarded by `OPENROUTER_API_KEY`.

For the deterministic real-adapter mode, the script marks one evidence package in the isolated validation database as validation-only source-ready data. This is used only to cross the backend adapter boundary and is explicitly not cited-source evidence or an academic-support assertion. The real adapter persists `mock_mode=false`.

The validator reports retrieval, verification, and metadata modes; dependency/import readiness; real-adapter selection; backend validator acceptance; score range; top-k compliance; safe provenance; semantic-cache default presence; unsupported labels; report generation; and packaging safety. Optional Markdown/JSON report output is supported.

## CLI flags added/updated

- `--mock-rag`
- `--real-rag`
- `--mock-genai`
- `--real-genai`
- `--metadata-disabled`
- `--metadata-mock`
- `--metadata-live`
- `--live-rag-embeddings`
- `--pdf-dir`
- `--report-output`
- existing `--reset-db` and positional PDF inputs retained

Missing PDFs, unavailable real-RAG imports/dependencies, missing live-embedding keys, and missing real-GenAI keys produce an explicit `validation_status: BLOCKED` with exit code 2.

## Tests added/updated

Nine deterministic unit tests were added for:

- CLI help and mode flags;
- default mock RAG + mock GenAI behavior;
- real RAG + mock GenAI + metadata-disabled environment configuration;
- actual `RagDirectClient` selection with `mock_mode=false`;
- mock GenAI client selection;
- dependency failure reported as BLOCKED;
- optional live RAG and real GenAI API-key guards;
- mode labels in validation summaries;
- rejection/reporting of unsupported support labels;
- packaging scan safety and zero packaged PDFs.

The existing two uploaded-PDF CLI path tests remain unchanged and pass.

## Mock RAG + Mock GenAI validation result

PASS for all three locally available ignored/private PDFs under `backend/tests/fixtures/private_pdfs/`.

- retrieval mode: Mock RAG
- verification mode: Mock GenAI
- metadata mode: disabled
- external metadata/provider calls: blocked by `METADATA_LOOKUP_ENABLED=false`
- pipelines/reports: generated successfully
- unsupported support labels: none
- packaging safety: pass, zero PDF entries
- generated local report: `/tmp/int008_mock_validation.md`

## Real RAG + Mock GenAI validation result

PASS for the same three local ignored/private PDFs.

For each PDF:

- retrieval mode: Real RAG
- execution boundary: real `RagDirectClient` with deterministic Door 1 output
- verification mode: Mock GenAI
- metadata mode: disabled
- real RAG import/dependencies: available
- real adapter selected and persisted as non-mock: yes
- backend response validator: passed
- all returned scores in 0–1: yes
- requested `top_k=3` respected: yes
- source/source_url provenance safe: yes
- semantic_cache_match default present: yes
- unsupported support labels: none
- pipeline and HTML report generation: passed
- packaging safety: pass, zero PDF entries
- generated local report: `/tmp/int008_real_adapter_validation.md`

## Real GenAI optional behavior

Real GenAI is not required for INT-QA-008. `--real-genai` is available only when `OPENROUTER_API_KEY` is configured; otherwise the validator returns BLOCKED before processing PDFs. The accepted staged mode uses `--mock-genai`, does not construct/call real Door 2, and continues through backend-owned BE10/BE11 validation and safety.

## Real RAG dependency/API-key behavior

Real RAG imports are checked before PDF processing. Missing dependencies return BLOCKED with the import error. The required deterministic real-adapter mode needs no API key and makes no external embedding call. Fully live embeddings require the explicit `--live-rag-embeddings` flag with `--real-rag` and `OPENROUTER_API_KEY`; missing configuration returns BLOCKED.

## PDF/private artifact handling

Only existing local ignored/private PDF paths were read. No PDF was created, copied into a report, added to the repository, or added to the release archive. Runtime uploaded copies and the isolated validation database remain excluded by packaging rules. When no usable PDF is supplied, the validator reports BLOCKED instead of passing silently.

## Packaging safety result

PASS.

- scan-only: `unsafe_artifact_scan: PASS`
- build: `unsafe_artifact_scan: PASS`
- unsafe entries: 0
- packaged PDFs: 0
- packaged database files: 0
- packaged `.env` files: 0
- release output: `/tmp/refcheck_ai_release_after_int008.zip`
- first build included 321 safe files; the final build included 322 safe files after this report was written. Both builds excluded 133 local/runtime artifacts, and the final archive contains the new validator, test, and fixing report.

## Commands run

From the repository root unless noted:

- `backend/.venv/bin/python -m py_compile backend/scripts/validate_uploaded_pdfs_be13.py` — PASS
- `backend/.venv/bin/python backend/scripts/validate_uploaded_pdfs_be13.py --help` — PASS
- `backend/.venv/bin/python -m pytest backend/tests/unit/test_be13_uploaded_pdf_cli.py backend/tests/unit/test_real_rag_pdf_validation_mode.py -q --tb=short` — PASS, 11 tests
- `backend/.venv/bin/python -m compileall backend/app backend/scripts` — PASS
- `backend/.venv/bin/python -m pytest backend/tests/test_full_text_pipeline.py -q --tb=short` — PASS, 8 tests (authoritative serial rerun)
- `backend/.venv/bin/python -m pytest backend/tests/unit/test_release_packaging.py -q --tb=short` — PASS, 26 tests (authoritative serial rerun)
- from `backend/`: `.venv/bin/pytest -q` — PASS, 233 tests
- from `backend/`: `.venv/bin/python scripts/validate_openapi.py` — PASS, 45 paths and no required gaps
- from `backend/`: `.venv/bin/python scripts/run_backend_checks.py` — PASS
- from `backend/`: `.venv/bin/python scripts/run_demo_pipeline.py` — PASS
- from `backend/`: `.venv/bin/python scripts/run_integrated_rag_checks.py` — PASS, `INTEGRATED_VALIDATION_RESULT=PASS`
- `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` — PASS, 365 tests
- from `backend/`: `.venv/bin/python scripts/validate_uploaded_pdfs_be13.py --mock-rag --mock-genai --metadata-disabled --pdf-dir tests/fixtures/private_pdfs --reset-db --report-output /tmp/int008_mock_validation.md` — PASS, 3 PDFs
- from `backend/`: `.venv/bin/python scripts/validate_uploaded_pdfs_be13.py --real-rag --mock-genai --metadata-disabled --pdf-dir tests/fixtures/private_pdfs --reset-db --report-output /tmp/int008_real_adapter_validation.md` — PASS, 3 PDFs
- `backend/.venv/bin/python backend/scripts/build_release_package.py --scan-only --root . --output /tmp/refcheck_ai_release_after_int008.zip` — PASS
- `backend/.venv/bin/python backend/scripts/build_release_package.py --root . --output /tmp/refcheck_ai_release_after_int008.zip` — PASS

An initial attempt ran the full-text and packaging test files concurrently. Both use the same SQLite test database, so their autouse fixtures raced while dropping tables and produced non-authoritative database errors. They were immediately rerun separately, exactly as the requested commands specify, and both passed. No code change was made in response to that execution artifact.

## Pass/fail result

PASS. The required staged `Real RAG + Mock GenAI` PDF validation mode exists, proves the real backend adapter/validator/persistence path without a GenAI or embedding API key, remains clearly distinguished from fully live retrieval, and preserves the existing mock mode.

## Remaining risks

- Fully live external embedding quality was not validated because it is intentionally optional and API-key/network dependent.
- Real GenAI was not executed because it is optional and must remain explicitly configured.
- The deterministic staged evidence validates integration mechanics, not cited-paper evidence quality or academic correctness.
- Independent QA revalidation is still required before closing INT-QA-008 or approving an integrated release.

## Ready for QA revalidation

Yes.
