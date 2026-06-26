# BE-7 — Evidence Package Builder

BE-7 prepares structured evidence packages for claim-reference pairs already created by BE-6. It builds on the stable BE4.2 reference/DOI extraction baseline, BE-5 DOI metadata lookup, and BE-6 claim/citation management.

## Purpose

The evidence package is the backend-owned contract that later BE-9 RAG/ML integration can consume. Frontend must not send raw documents directly to RAG/ML, and RAG/ML must not call external academic sources directly.

## Main endpoints

- `POST /api/v1/documents/{document_id}/prepare-evidence`
- `GET /api/v1/claims/{claim_id}/evidence-package`
- `GET /api/v1/documents/{document_id}/evidence-packages`

All endpoints use the standard response wrapper.

## Evidence package contract

Each package includes:

- document ID
- claim ID
- citation ID
- claim-reference link ID
- reference ID
- claim text
- citation text
- DOI and DOI status
- metadata from BE-5 `SourceMetadata` when available
- reference-extracted metadata fallback when official metadata is not available
- source evidence text when an abstract/full text is already available in backend-controlled data
- evidence availability status
- policy/version fields
- mapping details and warnings

## Evidence availability rules

- `FULL_TEXT_AVAILABLE`: a compatible existing `full_text` field is already present in stored metadata JSON.
- `ABSTRACT_AVAILABLE`: BE-5 `SourceMetadata.abstract` exists and is non-empty.
- `METADATA_ONLY`: metadata fields exist but no abstract/full text exists.
- `SOURCE_UNAVAILABLE`: no usable metadata, abstract, full text, DOI, URL, title, author, or year is available.

BE-7 does not scrape web pages, download publisher PDFs, call RAG/ML, or call GenAI verification.

## Metadata fallback rules

1. Prefer latest BE-5 `SourceMetadata` for the mapped reference.
2. If missing, use BE4.2 reference-extracted fields such as DOI, title, authors, year, and raw reference.
3. Do not invent metadata.
4. Add package warnings when metadata is unavailable or mapping is uncertain.

## Claim-reference eligibility

- `MAPPED`: package is created normally.
- `UNCERTAIN`, `MULTIPLE_MATCHES`, `NEEDS_HUMAN_REVIEW`: package is created if `reference_id` exists, with warning.
- `NO_MATCH`: package is skipped if no `reference_id` exists.

## Idempotency

Document-level evidence preparation replaces existing evidence packages for that document before rebuilding. Re-running `prepare-evidence` does not create uncontrolled duplicates.

## Policy/version fields

Configured from environment:

```env
EMBEDDING_MODEL_VERSION=embedding-v1
VERIFICATION_PROMPT_VERSION=verify-v1
VERIFICATION_POLICY_VERSION=policy-v1
```

## Validation

Run:

```bash
python -m compileall app
python scripts/init_db.py
pytest -q
python scripts/validate_uploaded_pdfs_be7.py --reset-db /path/to/paper1.pdf /path/to/paper2.pdf /path/to/paper3.pdf
```

## Uploaded research-paper validation summary

The BE-7 validation script was run against the three uploaded research PDFs. Results are stored in:

- `backend/validation/uploaded_pdf_validation_be7_output.txt`

High-level result:

- All three PDFs were accepted and processed.
- BE4.2 reference/DOI extraction still worked.
- BE-6 claim/citation extraction still worked.
- BE-7 evidence packages were created for mapped claim-reference links.
- No packages were created from the References section.
- No duplicate package issue was observed.
- Since live external metadata was not invoked in offline validation, packages used BE4.2 reference-extracted metadata fallback and were classified as `METADATA_ONLY` where appropriate.

## Limitations

BE-7 intentionally does not implement:

- verification cache layer
- semantic cache matching
- RAG retrieval calls
- embedding generation
- cosine similarity scoring
- GenAI support verification
- final safety scoring
- report generation
- publisher full-text retrieval
