# QA Re-validation Report — INT-QA-008 Real RAG Validation Mode

Run date: 2026-06-29 (Asia/Singapore)  
Role: QA Re-validation Agent  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`  
Git branch: `integration/backend-rag-merge`  
Git commit tested: `86d70f20c6088bbdd2f5ad6107c04896e7061f98`

## Scope

Revalidated only INT-QA-008 — the staged Real RAG + Mock GenAI uploaded-PDF
validation mode.

No production code, test, script, API route, schema, RAG implementation,
full-text implementation, packaging rule, DOI mapping, score behavior,
provenance behavior, semantic-cache behavior, failure sanitization, BE4.2,
BE10, or BE11 logic was modified. Only the assigned finding file was closed
after successful re-validation, and this report was added.

## Commands run

| Command | Result |
|---|---|
| Pre-validation branch, commit, worktree, finding-state, protected-file hash, and private-PDF hash audit | PASS — expected pre-existing changes preserved; three local private PDFs available; finding initially Open / Blocking Yes. |
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS. |
| `cd backend && .venv/bin/python scripts/validate_uploaded_pdfs_be13.py --help` | PASS — all ten required mode/report flags documented. |
| `cd backend && .venv/bin/pytest -q tests/unit/test_be13_uploaded_pdf_cli.py tests/unit/test_real_rag_pdf_validation_mode.py --tb=short` | PASS — 11 passed in 9.23s. |
| `cd backend && .venv/bin/pytest -q tests/test_full_text_pipeline.py --tb=short` | PASS — 8 passed in 8.29s. |
| `cd backend && .venv/bin/pytest -q tests/unit/test_release_packaging.py --tb=short` | PASS — 26 passed in 18.28s. |
| Optional real-GenAI guard with `OPENROUTER_API_KEY` removed | PASS — exit 2, `validation_status: BLOCKED`, clear real-GenAI key reason. |
| Optional live-embedding guard with `OPENROUTER_API_KEY` removed | PASS — exit 2, `validation_status: BLOCKED`, clear live-embedding key reason. |
| Missing PDF-directory guard | PASS — exit 2, `validation_status: BLOCKED`, missing-directory path reported. |
| `cd backend && .venv/bin/python scripts/validate_uploaded_pdfs_be13.py --mock-rag --mock-genai --metadata-disabled --pdf-dir tests/fixtures/private_pdfs --reset-db --report-output /tmp/int008_revalidation_mock.md` | PASS — all 3 available local PDFs. |
| `cd backend && .venv/bin/python scripts/validate_uploaded_pdfs_be13.py --real-rag --mock-genai --metadata-disabled --pdf-dir tests/fixtures/private_pdfs --reset-db --report-output /tmp/int008_revalidation_real_rag_mock_genai.md` | PASS — all 3 available local PDFs. |
| Staged real-RAG command repeated with `OPENROUTER_API_KEY` explicitly removed and report `/tmp/int008_revalidation_real_rag_mock_genai_no_key.md` | PASS — all 3 PDFs; confirms required mode has no API-key dependency. |
| Supplied independent validation-report inspection script | PASS — both requested reports exist, show PASS, contain required status fields, contain empty problem/unsupported-label lists, and do not contain BLOCKED. |
| Additional per-PDF report-field/count inspection | PASS — 3 PDF sections per report; every required field present; real-mode checks true for all 3 PDFs; live-quality disclaimer present. |
| Independent isolated-database inspection | PASS after filtering serialized JSON `null` rows — 3 documents, 6 persisted non-mock response payloads, 12 safe-provenance chunks, bounded scores, top-k respected, semantic default present, and no retrieval-level support status. |
| `cd backend && .venv/bin/pytest -q` | PASS — 233 passed in 171.95s. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS — 45 paths; required gaps `[]`. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS — compile/import, 18-table initialization, and OpenAPI validation passed. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS — demo completed; endpoint calls returned HTTP 200. |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | PASS — 365 passed in 1.60s. |
| `backend/.venv/bin/python backend/scripts/build_release_package.py --scan-only --root . --output /tmp/refcheck_ai_release_int008_revalidation.zip` | PASS — 322 approved files, 139 exclusions, unsafe scan PASS. |
| `backend/.venv/bin/python backend/scripts/build_release_package.py --root . --output /tmp/refcheck_ai_release_int008_revalidation.zip` | PASS — clean 322-file ZIP created. |
| Supplied independent release-ZIP inspection script | PASS — unsafe entries `()`, required missing `[]`, PDF entries `[]`, database entries `[]`, environment entries `[]`. |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | PASS — backend 233 passed, RAG 365 passed, every check PASS, `INTEGRATED_VALIDATION_RESULT=PASS`. |
| Post-validation protected-file and private-PDF hash audit | PASS — validator, tests, integrated runner, packaging script, and all three private PDFs were byte-for-byte unchanged. |

An initial ad hoc database-inspection expression encountered an expected
serialized JSON `null` row and raised an `AttributeError`. The corrected
read-only query filtered non-dictionary payloads and produced the successful
database evidence reported above. This was an inspection-query issue, not an
application or test failure.

## CLI flag validation result

**PASS.** `--help` independently documents:

- `--mock-rag`;
- `--real-rag`;
- `--mock-genai`;
- `--real-genai`;
- `--metadata-disabled`;
- `--metadata-mock`;
- `--metadata-live`;
- `--live-rag-embeddings`;
- `--pdf-dir`;
- `--report-output`.

The help text distinguishes the real `RagDirectClient` adapter with
deterministic Door 1 output from fully live external embeddings. Focused tests
also confirm the default remains Mock RAG + Mock GenAI.

## Mock RAG + Mock GenAI validation result

**PASS.** The existing mode processed all three available local ignored/private
PDFs and returned exit code 0 with `validation_status: PASS`.

For every PDF, the report shows:

- `retrieval_mode: Mock RAG`;
- `verification_mode: Mock GenAI`;
- `metadata_mode: disabled`;
- external metadata calls blocked;
- successful pipeline and report generation;
- `unsupported_labels_found: []`;
- `problems_found: []`;
- packaging safety passed with zero PDF entries.

The focused tests confirm this remains the parser and environment default.

## Real RAG + Mock GenAI validation result

**PASS.** The required staged mode processed the same three local PDFs and
returned exit code 0 with `validation_status: PASS`. It was also repeated with
`OPENROUTER_API_KEY` explicitly absent and again passed for all three PDFs.

For every PDF, independent report and database evidence confirms:

- `RAG_MOCK_MODE=false`;
- `GENAI_MOCK_MODE=true`;
- `METADATA_LOOKUP_ENABLED=false`;
- `retrieval_mode: Real RAG`;
- `verification_mode: Mock GenAI`;
- `metadata_mode: disabled`;
- real RAG imports/dependencies available;
- real `RagDirectClient` selected;
- returned and persisted retrieval payload marked `mock_mode=false`;
- backend BE9 response validation passed;
- all overall, confidence, and chunk scores remained within 0–1;
- requested `top_k=3` was respected;
- source and HTTPS source URL provenance remained safe;
- the unmatched `semantic_cache_match` default was present;
- no unsupported support label or retrieval-level `support_status` appeared;
- pipeline orchestration, Mock GenAI, backend BE10/BE11 safety, report,
  feedback, mapping feedback, and UAT paths completed;
- `problems_found: []`.

The deterministic probe replaces Door 1 execution output only. The real
backend request builder, RAG contract models, `RagDirectClient` adapter,
response transformation, validator, persistence, orchestration, mock GenAI,
and backend safety/reporting paths execute.

## Real GenAI/live embedding optional guard result

**PASS.** With `OPENROUTER_API_KEY` explicitly removed:

- `--real-rag --real-genai` returned exit code 2 and `BLOCKED` with the exact
  reason that optional real GenAI requires the key;
- `--real-rag --mock-genai --live-rag-embeddings` returned exit code 2 and
  `BLOCKED` with the exact reason that fully live embeddings require the key.

The required Real RAG + Mock GenAI deterministic-adapter mode passed without
the key. It therefore neither requires real Door 2 nor makes live embedding
calls unless explicitly requested.

## PDF/private artifact handling result

**PASS.** All three available ignored/private PDFs were validated. No PDF was
added, copied into the repository, or packaged. Pre/post SHA-256 values for all
three PDFs matched exactly. Missing PDF input was independently confirmed to
return explicit BLOCKED status rather than a silent pass.

Runtime upload copies and validation databases remained under excluded local
runtime paths.

## Validation report content result

**PASS.** Both requested reports exist and have three PDF sections. They contain
all required fields:

- retrieval, verification, metadata, and RAG execution modes;
- RAG import and dependency readiness;
- real-adapter selection and backend-validator result;
- score, top-k, provenance, and semantic-cache checks;
- unsupported-label check;
- report/reports generation;
- packaging safety;
- problem list.

Each report has one overall PASS, three empty unsupported-label lists, three
empty problem lists, three successful report-generation fields, and three
successful packaging fields. Neither report contains BLOCKED.

The staged real-RAG report explicitly says that live embedding quality was not
tested. Static inspection also confirms the deterministic fixture/probe text
says it is not cited-source evidence and does not assert academic support. The
mode therefore makes no live-quality or academic-correctness claim.

## Packaging safety result

**PASS.** Scan-only and build modes returned `unsafe_artifact_scan: PASS`.
Independent archive inspection confirmed:

- zero unsafe entries;
- zero PDF entries;
- zero database entries;
- zero populated `.env` entries;
- the validator script is included;
- the focused real-RAG validation test is included;
- the INT-QA-008 fixing report is included.

The final archive contains 322 approved files. Its 139 exclusion counters
include local/private/runtime PDFs, databases, environment data, caches,
generated validation outputs, IDE/VCS data, and virtual environments.

## Finding result

**INT-QA-008: Fixed.** The original reproduction now exposes and successfully
executes explicit Mock RAG + Mock GenAI and staged Real `RagDirectClient` +
Mock GenAI modes. The required staged mode proves the real adapter, contract,
validation, persistence, orchestration, backend safety, and reporting boundary
without requiring real GenAI, live embeddings, external metadata providers, or
an API key.

Finding file closed: **Yes.** Only
`qa/findings/INT-QA-008_REAL_RAG_VALIDATION_MODE.md` was updated. Its status is
Closed and blocking value is No / Resolved, with the requested independent-QA
closure note.

## Regression results

- Backend regression: **PASS** — 233 tests.
- RAG regression: **PASS** — 365 tests.
- OpenAPI/check/demo: **PASS** — 45 paths, no required gaps, backend checks
  completed, and the demo completed successfully.
- Integrated runner: **PASS** — every check passed and
  `INTEGRATED_VALIDATION_RESULT=PASS`.

## Remaining risks

- The staged mode validates integration mechanics and deterministic contract
  behavior, not live external embedding availability or retrieval quality.
- Real GenAI output quality was not evaluated; that mode remains optional and
  explicitly API-key guarded.
- Deterministic validation evidence is not cited-source evidence and must not
  be interpreted as proof of academic support or correctness.
- Existing local private PDFs remain subject to consent, retention, access,
  and sharing controls, although validation and packaging did not alter or
  release them.
- INT-QA-005 and INT-QA-012 remain open but are marked non-blocking; they were
  not revalidated or changed here. After closing INT-QA-008, the finding-status
  audit found no remaining Open + Blocking INT-QA finding. This report does not
  independently approve unrelated release-governance concerns.

## Final decision

**PASS** for INT-QA-008 re-validation.
