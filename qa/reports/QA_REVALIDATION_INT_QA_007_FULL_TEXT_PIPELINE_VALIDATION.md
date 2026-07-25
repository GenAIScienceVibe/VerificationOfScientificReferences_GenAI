# QA Re-validation Report — INT-QA-007 Full-text Pipeline Validation

Run date: 2026-06-28 (Asia/Singapore)  
Role: QA Re-validation Agent  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`  
Git branch: `integration/backend-rag-merge`  
Git commit tested: `86d70f20c6088bbdd2f5ad6107c04896e7061f98`

## Scope

Revalidated only INT-QA-007 — deterministic end-to-end coverage of the
full-text upload/provider/evidence/RAG pipeline.

No production code, test, script, API route, schema, RAG behavior, packaging
rule, or unrelated finding was modified. INT-QA-008 was not changed or
revalidated and remains Open and Blocking. This report does not approve the
full integrated release.

## Commands run

| Command | Result |
|---|---|
| Static inspection of `backend/tests/test_full_text_pipeline.py` and protected upload/metadata/evidence/RAG/packaging code | PASS — deterministic in-memory bytes/mocks; no live provider/OpenRouter call site. |
| Git tracking and non-private fixture audit | PASS — no tracked PDF, DB, populated `.env`, or new non-private test PDF. |
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS. |
| `cd backend && .venv/bin/pytest -q tests/test_full_text_pipeline.py --tb=short` | PASS — 8 passed in 6.69s. |
| `cd backend && .venv/bin/pytest -q tests/unit/test_release_packaging.py --tb=short` | PASS — 26 passed in 16.11s. |
| `cd backend && .venv/bin/pytest -q` | PASS — 224 passed in 146.72s. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS — 45 paths; required endpoint gaps `[]`. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS — compile/import, 18-table initialization, and OpenAPI checks passed. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS — demo completed; all endpoint calls returned HTTP 200. |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | PASS — backend 224 passed, RAG 365 passed, every check PASS, `INTEGRATED_VALIDATION_RESULT=PASS`. |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | PASS — 365 passed in 1.68s. |
| `backend/.venv/bin/python backend/scripts/build_release_package.py --scan-only --root . --output /tmp/refcheck_ai_release_int007_revalidation.zip` | PASS — 319 approved files, 126 exclusion counters, unsafe scan PASS. |
| `backend/.venv/bin/python backend/scripts/build_release_package.py --root . --output /tmp/refcheck_ai_release_int007_revalidation.zip` | PASS — clean 319-file ZIP created; unsafe scan PASS. |
| Supplied independent ZIP inspection | PASS — unsafe entries `()`, required missing `[]`, PDF entries `[]`, database entries `[]`, environment entries `[]`. |
| Post-validation protected/private hash, worktree, and finding-state audit | PASS — protected code/tests/scripts unchanged; private evidence unchanged; INT-QA-011 remains closed; INT-QA-008 remains untouched. |

## Upload-source-PDF flow result

**PASS.** Independent inspection and focused execution confirm that the test:

- creates no PDF file and relies on no real/private PDF fixture;
- uploads deterministic multipart bytes named `synthetic-source.pdf`;
- monkeypatches the upload PDF extraction boundary and separately exercises
  extraction capping with an in-memory PyMuPDF document object;
- verifies the configured `FULLTEXT_MAX_CHARS` value reaches extraction;
- verifies extracted text and its upload source label are stored in
  `SourceMetadata.raw_metadata_json`;
- verifies the existing reference metadata status remains
  `LOOKUP_SUCCEEDED`;
- calls the real prepare-evidence API and obtains one
  `FULL_TEXT_AVAILABLE` package;
- verifies `EvidencePackage.source_evidence_text` equals the uploaded text;
- verifies `RagRequestBuilder` sends `FULL_TEXT_AVAILABLE`, the expected text,
  the public source URL, and bounded `top_k`;
- verifies the `RagDirectClient` Door 1 request receives the same full-text
  source evidence;
- verifies returned and persisted results contain a `FULL_TEXT` chunk;
- verifies source `uploaded_full_text` and the public HTTPS `source_url` are
  preserved;
- checks request, returned, and persisted structures for Linux, macOS,
  Windows, and `file://` private-path markers;
- preserves the standard unmatched `semantic_cache_match`;
- confirms neither the persisted BE9 payload nor returned Door 1 payload
  contains `support_status`.

Only `rag.api.retrieve_evidence` is monkeypatched at the RAG boundary. The real
backend request builder, direct adapter, validator, coordinator, and database
persistence path execute. No embedding, GenAI, provider, or network service is
called and no API key is required.

## Provider-path validation result

**PASS.** The focused tests independently pass for:

- mocked Unpaywall OA-PDF discovery and extraction, producing persisted raw
  full text and `FULL_TEXT_AVAILABLE` evidence;
- arXiv DOI-to-direct-PDF selection without Unpaywall, producing
  `FULL_TEXT_AVAILABLE` evidence;
- mocked CORE inline text without a PDF download, producing
  `FULL_TEXT_AVAILABLE` evidence;
- failed OA PDF extraction plus unavailable CORE, safely retaining the
  CrossRef abstract and producing `ABSTRACT_AVAILABLE` evidence;
- `METADATA_LOOKUP_ENABLED=false`, with CrossRef, OpenAlex, Semantic Scholar,
  Unpaywall, CORE, SSRN, DOI resolver, title-search, arXiv, and full-text
  download mocks all remaining uncalled;
- mocked SSRN abstract fallback, producing `PREPRINT_AVAILABLE`, the
  `PREPRINT_SOURCE` warning, and retrieval-usable abstract evidence.

The SSRN Door 1 response contains no final support status. Existing BE11
preprint safety coverage (`test_preprint_source_caps_confidence_and_requires_review`)
remains present and passed in the full backend suite, confirming BE11 retains
final preprint limitation and safety authority.

## RAG full-text integration result

**PASS.** The direct backend adapter receives full-text evidence and returns a
bounded, validated `FULL_TEXT` result with safe provenance. The persisted
`RagRetrievalResult` retains the evidence type, source, source URL,
`mock_mode=false`, default semantic-cache structure, and no error. BE9 returns
retrieval information only and does not decide final claim support.

Regression coverage also passed for existing mock RAG, abstract-only evidence,
metadata-only skip, and source-unavailable skip behavior as part of the
224-test backend suite.

## Packaging safety result

**PASS.** No PDF fixture was added or tracked. The focused test uses only
in-memory bytes and monkeypatches. Private PDF and local environment hashes
were unchanged after validation, and INT-QA-011 remains Closed / No / Resolved.

The scan and build both returned `unsafe_artifact_scan: PASS` for 319 approved
files. Independent ZIP inspection confirmed:

- required full-text test, fixing report, packaging script, and packaging guide
  are included;
- zero unsafe entries;
- zero PDF entries;
- zero database entries;
- zero populated `.env` entries.

## Finding result

**INT-QA-007: Fixed.** The original missing-coverage scenario is now exercised
through deterministic endpoint, service, persistence, evidence-package, direct
RAG adapter, response-validation, and packaging tests.

Finding file closed: **Yes.** Only
`qa/findings/INT-QA-007_FULL_TEXT_PIPELINE_VALIDATION_GAP.md` was updated. Its
status is Closed and blocking value is No / Resolved, with the requested
independent-QA closure note.

## Regression results

- Backend regression: **PASS** — 224 tests.
- RAG regression: **PASS** — 365 tests.
- OpenAPI/check/demo: **PASS** — 45 paths, no endpoint gaps, checks completed,
  and demo endpoint calls returned HTTP 200.
- Integrated runner: **PASS** — `INTEGRATED_VALIDATION_RESULT=PASS`.

## Remaining risks

- The tests validate deterministic backend orchestration and contracts, not
  live availability or content quality of external academic providers.
- The endpoint parser is mocked for the end-to-end test; extraction capping is
  separately tested in memory. OCR and scanned/image-only PDFs remain out of
  scope.
- Real/private PDF plus real embeddings in a staged real-RAG/mock-GenAI
  validation mode remains INT-QA-008 scope.
- INT-QA-008 remains Open and Blocking; full integrated release approval is
  withheld.

## Final decision

**PASS** for INT-QA-007 re-validation. Full integrated release approval is not
granted because INT-QA-008 remains open and blocking.
