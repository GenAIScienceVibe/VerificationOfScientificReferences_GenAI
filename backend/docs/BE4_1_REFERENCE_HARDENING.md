# BE-4.1 — Reference Boundary, Header/Footer Cleanup, DOI Continuation, and Real-PDF Regression Hardening

## Scope

BE-4.1 hardens BE-3 and BE-4 quality using real PDF failures found during QA. It does not implement BE-5 DOI metadata lookup and does not call CrossRef, OpenAlex, DOI Resolver, Semantic Scholar, RAG, or GenAI.

## Implemented items

- Repaired line-broken DOI prefixes and DOI bodies before section/reference extraction.
- Added conservative repeated header/footer cleanup for PDF page artifacts.
- Hardened BE-3 `References` section boundaries.
- Stopped references before appendix, survey, questionnaire, screenout, and similar post-reference content.
- Hardened BE-4 reference section trimming even when BE-3 provides a polluted `DocumentSection:References`.
- Improved individual reference splitting for APA, numbered, bracketed, multi-line, and PDF-collapsed references.
- Added false-positive filtering for footer/page/URL-only/survey artifacts.
- Added stricter DOI syntax validation so incomplete DOI values ending in `-`, `/`, or `:` are `MALFORMED`, not `FOUND`.
- Added enum validation for `doi_status` and `metadata_status` query filters.
- Added `ENABLE_RAW_TEXT_DEBUG_ENDPOINT`; `/raw-text` is disabled by default and enabled only for local QA when configured.
- Added failed-PDF audit trace by including the failed `document_id` in PDF extraction error detail.
- Added re-extraction safety: destructive reference re-extraction is blocked if downstream rows already exist.
- Added sanitized real-PDF regression text fixtures and a reusable real-PDF QA script.

## New/changed config

```env
ENABLE_RAW_TEXT_DEBUG_ENDPOINT="false"
```

Set this to `true` only in local QA when you need to inspect `/api/v1/documents/{document_id}/raw-text`.

## New safety behavior

### Raw text endpoint

By default:

```text
GET /api/v1/documents/{document_id}/raw-text -> DEBUG_ENDPOINT_DISABLED
```

This prevents accidental public exposure of uploaded document content or student/person identifiers.

### Reference re-extraction

Re-extraction is allowed while there are only `Reference` rows. It is blocked when downstream rows exist in tables such as:

- `source_metadata`
- `claim_reference_links`
- `evidence_packages`
- `rag_retrieval_results`
- `verification_results`
- `user_feedback`
- `claim_cache_index`

This prevents breaking BE-5+ and BE-6+ records by deleting/recreating reference IDs.

## Real PDF QA script

Run from `backend/`:

```bash
python scripts/qa_real_pdf_api_test.py /path/to/pdf1.pdf /path/to/pdf2.pdf
```

The script runs:

- upload
- section extraction
- reference extraction
- reference listing
- DOI status filters
- bad marker checks
- bad DOI-ending checks

## Known remaining limitation

BE-4.1 is deterministic rule-based extraction. It is safer than BE-4, but it is still not a perfect citation parser. Some complex PDFs may still need BE-5/BE-6 safeguards and manual review workflows. This patch focuses on preventing the specific real-PDF failures from polluting BE-5 metadata lookup.
