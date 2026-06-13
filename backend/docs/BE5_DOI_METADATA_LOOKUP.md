# BE-5 - DOI Metadata Lookup

BE-5 adds backend-controlled DOI metadata lookup on top of the stable BE4.2 reference extraction baseline. It does not implement claim extraction, citation mapping, evidence packages, RAG, GenAI verification, report generation, or final support scoring.

## Implemented scope

- Single-reference DOI verification: `POST /api/v1/references/{reference_id}/verify-doi`
- Document-level DOI verification: `POST /api/v1/documents/{document_id}/verify-dois`
- Stored reference metadata retrieval: `GET /api/v1/references/{reference_id}/metadata`
- Existing reference list endpoint still returns `doi_status`, `metadata_status`, and `metadata_match_score`
- CrossRef client for `GET /works/{doi}`
- DOI resolver URL fallback using `https://doi.org/{doi}`
- SourceMetadata persistence
- metadata cache reuse for repeated DOI values
- metadata match scoring
- controlled handling of 404, timeout, malformed JSON, service failure, missing DOI, and malformed DOI

## BE4.2 compatibility protection

BE4.2 is preserved. Tests still cover reference splitting, DOI extraction, DOI attachment to the correct reference, multiline references, missing DOI, malformed DOI, and real-PDF regression fixtures.

A small defensive improvement was added during BE-5 validation: if PDF extraction produces an extra standalone DOI-only line after a completed reference, the DOI is preserved as an orphan DOI-only reference instead of being attached to the previous reference. This prevents BE-5 from validating a correct DOI against the wrong reference entry.

## Configuration

Add these environment variables in `.env`:

```env
METADATA_LOOKUP_ENABLED=true
CROSSREF_BASE_URL=https://api.crossref.org
DOI_RESOLVER_BASE_URL=https://doi.org
OPENALEX_BASE_URL=https://api.openalex.org
METADATA_SERVICE_TIMEOUT_SECONDS=10
METADATA_MAX_RETRIES=2
CROSSREF_MAILTO=
METADATA_USER_AGENT=verifai-refcheck-backend/1.0.0
```

`CROSSREF_MAILTO` is optional but recommended for polite API usage. Do not hardcode secrets.

## DOI normalization

Before lookup, BE-5:

- strips `https://doi.org/`
- strips `http://dx.doi.org/`
- strips `doi:` / `DOI:`
- removes obvious trailing punctuation
- lowercases the DOI
- rejects clearly invalid DOI syntax

## DOI and metadata statuses

- `FOUND`: DOI was extracted syntactically by BE4.2, but has not yet been proven valid.
- `VALID`: metadata lookup succeeded for that DOI.
- `INVALID`: metadata source indicates the DOI was not found.
- `MISSING`: no DOI was extracted.
- `MALFORMED`: DOI-like value exists but is syntactically invalid.
- `LOOKUP_FAILED`: lookup failed for service/network reasons.

Metadata statuses:

- `NOT_LOOKED_UP`
- `LOOKUP_SUCCEEDED`
- `LOOKUP_FAILED`
- `METADATA_UNAVAILABLE`

## Metadata match scoring

BE-5 compares BE4.2 extracted fields against official metadata fields:

- title similarity: 40%
- author similarity: 25%
- year match: 20%
- DOI match: 15%

If some extracted fields are missing, the score is recalculated from available fields only. This makes the score explainable and robust for imperfect PDF/reference parsing.

## Uploaded research-paper validation

The uploaded PDFs were processed through BE-3 and BE4.2. DOI lookup API behavior was exercised, but the sandbox has no external DNS/network access, so live CrossRef metadata retrieval could not be completed here. Automated BE-5 metadata behavior is validated with mocked CrossRef responses.

## Limitations

- BE-5 verifies DOI metadata availability only.
- BE-5 does not retrieve full paper text.
- BE-5 does not judge whether a claim is supported.
- BE-5 does not call RAG or GenAI.
- CrossRef metadata quality depends on publisher-submitted metadata.
- Live metadata lookup requires internet access from the runtime environment.
