# INT-QA-007 — Full-text upload/provider validation gap

Finding ID: INT-QA-007  
Title: Full-text upload, Unpaywall, arXiv, CORE, and RAG flow lacks end-to-end coverage  
Severity: P2  
Status: Closed  
Blocking: No / Resolved  
Component: Full-text / Tests  
Phase impacted: BE14 / Integrated QA  
Endpoint/service: `POST /api/v1/references/{reference_id}/upload-source-pdf`  
Test type: API / Integration / Real PDF

## Problem

Full-text code and endpoint are present, but there is no test proving uploaded or provider-derived text reaches a `FULL_TEXT_AVAILABLE`/`PREPRINT_AVAILABLE` evidence package and then real RAG retrieval.

## Steps to reproduce

Search backend tests for `upload-source-pdf`, `inject_fulltext_from_uploaded_pdf`, and full-text provider calls.

## Expected result

End-to-end tests cover upload validation, text extraction/storage, evidence availability, source traceability, and real RAG retrieval. Provider fallbacks have mocked success/failure/disabled-mode tests.

## Actual result

The endpoint is in OpenAPI and implementation exists. Evidence builder recognizes `raw_metadata_json.full_text`. Only a preprint classification test was found; no source-PDF endpoint test and no upload/provider→evidence→RAG end-to-end test exists.

## Evidence

- `backend/app/api/v1/references.py:38-74`
- `backend/app/services/doi_metadata_lookup.py:566-602` and `729-819`
- `backend/app/services/evidence_package_builder.py:233-257`
- No matching backend test for the upload endpoint or injected full text.

## Root cause hypothesis

BE14-style implementation was merged after the BE13 validation suite without extending fixtures and staged validation.

## Suggested fix direction

Add isolated fixtures and mocked-provider tests, then a staged real-RAG retrieval from an uploaded source PDF.

## Regression risk

Medium to high for privacy, storage, evidence classification, and retrieval provenance.

## Validation required after fix

Prove uploaded PDF → extracted text → persisted metadata → rebuilt `FULL_TEXT_AVAILABLE` package → bounded, traceable real-RAG chunks.

## Closure note

Closed after independent QA re-validation. Deterministic tests now validate uploaded source PDF flow, mocked Unpaywall/arXiv/CORE full-text paths, provider failure fallback, metadata-disabled no-external-call behavior, SSRN/preprint retrieval-usable evidence, BE9 full-text RAG request construction, direct RAG adapter handoff, persisted FULL_TEXT retrieval result, safe provenance, no support_status leakage from BE9, and packaging safety with zero PDF/private artifacts in the clean release. Backend regression, RAG regression, OpenAPI/check/demo, integrated validation, and release scan/build passed.
