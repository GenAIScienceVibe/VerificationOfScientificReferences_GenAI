# Fixing Report — INT-QA-007 Full-text Pipeline Validation

Run date: 2026-06-28 (Asia/Singapore)  
Role: Fixing Agent  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`  
Git branch: `integration/backend-rag-merge`  
Git commit: `86d70f20c6088bbdd2f5ad6107c04896e7061f98`

## Finding addressed

INT-QA-007 — Full-text upload, Unpaywall, arXiv, CORE, and RAG flow lacks
end-to-end coverage.

No other finding was fixed or closed. INT-QA-008 remains outside this task.
No staged real-RAG/private-PDF validation mode was added.

## Root cause

The BE14-style source-PDF and provider full-text implementation was merged
after the earlier backend validation suite. Existing tests covered isolated
abstract, metadata-only, source-unavailable, SSRN classification, metadata-
disabled, and RAG contract behavior, but no deterministic test connected:

```text
source upload/provider result
  -> SourceMetadata.raw_metadata_json.full_text
  -> EvidencePackage FULL_TEXT_AVAILABLE
  -> BE9 request source_evidence
  -> RagDirectClient
  -> validated and persisted RagRetrievalResult
```

The implementation already supported the required flow. No production defect
was required to close the coverage gap.

## Files changed

- `backend/tests/test_full_text_pipeline.py`
- `qa/reports/FIX_REPORT_INT_QA_007_FULL_TEXT_PIPELINE_VALIDATION.md`

No production code, existing test, script, API route, schema, model, packaging
rule, private artifact, or finding file was modified.

## Tests added

Eight deterministic tests were added:

1. uploaded source PDF through endpoint, metadata, evidence package, real direct
   RAG adapter, response validation, and persistence;
2. uploaded PDF extraction character-cap enforcement;
3. mocked Unpaywall PDF/full-text success;
4. mocked arXiv direct-PDF/full-text success;
5. mocked CORE inline-full-text success;
6. provider download/CORE failure falling back safely to abstract evidence;
7. metadata-disabled mode blocking every metadata, title, full-text provider,
   DOI resolver, and PDF-download call;
8. mocked SSRN abstract fallback producing retrieval-usable preprint evidence
   without a final support status.

The module creates only database records and in-memory byte strings. It does
not create or commit a PDF fixture and does not make network calls.

## Uploaded source PDF flow validation

**PASS.** The integration test proves:

- `POST /api/v1/references/{reference_id}/upload-source-pdf` accepts a
  deterministic multipart PDF upload;
- the PDF extraction boundary is called with the upload bytes and configured
  `FULLTEXT_MAX_CHARS` value;
- extracted text and the safe upload source label are stored in
  `SourceMetadata.raw_metadata_json`;
- the existing reference metadata state remains valid and the linked claim is
  reported as affected;
- the independent extraction helper caps long text exactly at `max_chars` and
  closes its PDF document;
- `POST /api/v1/documents/{document_id}/prepare-evidence` creates one
  `FULL_TEXT_AVAILABLE` package whose `source_evidence_text` is the uploaded
  text;
- `RagRequestBuilder` sends that exact text as
  `source_evidence.text`, with `FULL_TEXT_AVAILABLE` and a public source URL;
- neither the BE9 request nor persisted RAG provenance contains a local path.

The PDF parser is monkeypatched for the endpoint test. The cap test replaces
the in-memory PyMuPDF document object. No filesystem PDF is used.

## Unpaywall, arXiv, CORE, and preprint validation

**PASS.** All provider clients and PDF extraction/download calls are mocks:

- Unpaywall: a mocked OA PDF URL is extracted, merged into raw metadata, and
  promoted to `FULL_TEXT_AVAILABLE` evidence.
- arXiv: an arXiv DOI selects the direct `arxiv.org/pdf/...` URL without
  calling Unpaywall, then produces full-text evidence.
- CORE: mocked inline text is merged directly without attempting a PDF
  download, then produces full-text evidence.
- Failure: a failed OA PDF extraction followed by an unavailable CORE result
  preserves the CrossRef abstract and produces `ABSTRACT_AVAILABLE` evidence.
- SSRN: mocked CrossRef/OpenAlex/Semantic Scholar/SSRN behavior produces
  `PREPRINT_AVAILABLE`, a `PREPRINT_SOURCE` warning, and abstract-form input for
  retrieval. Retrieval returns no final support label; BE11 remains the owner
  of preprint limitations and final safety.
- Disabled mode: with `METADATA_LOOKUP_ENABLED=false`, all CrossRef, OpenAlex,
  Semantic Scholar, Unpaywall, CORE, SSRN, title-search, arXiv, resolver, and
  PDF-download mocks remain uncalled.

Existing metadata-only and source-unavailable skip tests, abstract-only tests,
and BE11 preprint-confidence tests remain unchanged and passed in the full
backend regression.

## RAG full-text integration validation

**PASS.** The upload integration test uses the real backend `RagRequestBuilder`,
`RagMlClient`, `RagDirectClient`, `RagResponseValidator`, and
`RagRetrievalService` boundaries. Only `rag.api.retrieve_evidence` is replaced
with a deterministic in-memory response, so no embedding service, OpenRouter,
LLM, API key, or network is required.

The captured RAG Door 1 request contains:

- `FULL_TEXT_AVAILABLE`;
- the exact uploaded source evidence text;
- the public source URL;
- the requested bounded `top_k`.

The returned and persisted result contains a `FULL_TEXT` chunk, source label
`uploaded_full_text`, safe public `source_url`, `mock_mode=false`,
`error_message=None`, and the standard unmatched `semantic_cache_match`.
Neither response contains `support_status`, preserving backend BE10/BE11 final
verification authority.

## Packaging safety

**PASS.** No PDF was added to Git or outside the existing ignored private
fixture directory. Packaging tests still pass. The clean release scanner and
builder report `unsafe_artifact_scan: PASS`; independent archive inspection
finds zero unsafe entries and zero PDF members. The new test module is included
in the release.

Before adding this report, the archive contained 318 approved files. The final
post-report scan and build contain 319 approved files, exclude 126
local/private/generated artifact counters, and report zero unsafe entries.

## Commands run

| Command | Result |
|---|---|
| Initial `cd backend && .venv/bin/pytest -q tests/test_full_text_pipeline.py --tb=short` | Test-harness setup failure — 6 passed, 2 failed because the tests imported root `rag` before `RagDirectClient` added the repository root to `sys.path`; no application defect. |
| Corrected `cd backend && .venv/bin/pytest -q tests/test_full_text_pipeline.py --tb=short` | PASS — 8 passed in 6.73s. |
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS. |
| `cd backend && .venv/bin/pytest -q tests/unit/test_release_packaging.py --tb=short` | PASS — 26 passed in 14.58s. |
| `cd backend && .venv/bin/pytest -q` | PASS — 224 passed in 145.38s. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS — 45 paths; required endpoint gaps `[]`. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS — compile/import, 18-table initialization, and OpenAPI checks passed. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS — demo completed; every endpoint call returned HTTP 200. |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | PASS — backend 224 passed, RAG 365 passed, every check PASS, `INTEGRATED_VALIDATION_RESULT=PASS`. |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | PASS — 365 passed in 1.77s. |
| `backend/.venv/bin/python backend/scripts/build_release_package.py --scan-only --root . --output /tmp/refcheck_ai_release_after_int007.zip` | PASS — 319 approved files, 126 exclusion counters, unsafe scan PASS. |
| `backend/.venv/bin/python backend/scripts/build_release_package.py --root . --output /tmp/refcheck_ai_release_after_int007.zip` | PASS — clean 319-file ZIP created; unsafe scan PASS. |
| Independent archive member/PDF scan | PASS — zero unsafe entries, zero PDF members, new test present. |
| Protected production/finding/packaging hash comparison | PASS — all protected files unchanged. |

## Pass/fail result

**PASS.** The upload/provider-to-evidence-to-RAG flow now has deterministic,
network-free integration coverage. All focused tests and full regressions pass.

## API and safety impact

- No API route, request, response, OpenAPI contract, model, or schema changed.
- No DOI mapping, score, top-k, cache, traceability, failure-detail, BE4.2,
  BE10, or BE11 behavior changed.
- Mock mode remains available and unchanged.
- Tests make no live academic-provider, embedding, or GenAI calls.
- No API key is required.

## Remaining risks

- Provider tests validate deterministic backend orchestration and contracts,
  not availability or content quality of live Unpaywall, arXiv, CORE, SSRN,
  CrossRef, OpenAlex, or Semantic Scholar services.
- The endpoint test mocks PDF extraction; the separate cap test exercises the
  extraction boundary in memory. OCR and scanned/image-only PDFs remain out of
  scope.
- Real/private PDF plus real embedding retrieval remains INT-QA-008 scope and
  was intentionally not implemented or claimed here.
- INT-QA-007 remains Open until an independent QA Re-validation Agent confirms
  this coverage and closes it.

## Ready for QA revalidation

**Yes.**
