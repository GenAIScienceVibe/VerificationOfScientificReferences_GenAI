# BE-8 — Verification Cache Layer

BE-8 adds the backend-controlled verification cache layer. It is not the BE-5 DOI metadata cache and it does not perform RAG, embedding generation, vector search, GenAI verification, safety scoring, or report generation.

## Purpose

The cache avoids repeated verification work for the same normalized claim + DOI + compatible policy versions. It prepares the contract that BE-10 can use after final verification results exist.

## Exact cache key

The exact cache key uses:

- normalized claim text
- SHA-256 normalized claim hash
- normalized DOI
- evidence version
- embedding model version
- prompt version
- verification policy version

Claim normalization is conservative. It lowercases, trims, collapses whitespace, and removes harmless punctuation. It does not remove negation words, numeric values, percentages, years, sample sizes, p-values, or scientific terms.

DOI normalization strips `https://doi.org/`, `http://dx.doi.org/`, and `doi:` prefixes, lowercases the DOI, and removes obvious trailing punctuation.

## Cache sources

- `NEW_VERIFICATION`: no reusable cache result; verification should run later.
- `EXACT_CACHE`: exact normalized claim + DOI + policy-compatible cache result found.
- `SEMANTIC_CACHE`: reserved/prepared semantic reuse source through a mockable interface.
- `HUMAN_CORRECTED`: reserved source for later human-corrected results.

## Config

```env
CACHE_ENABLED=true
CACHE_EXACT_ENABLED=true
CACHE_SEMANTIC_ENABLED=false
CACHE_HIGH_SIMILARITY_THRESHOLD=0.92
CACHE_MEDIUM_SIMILARITY_THRESHOLD=0.80
CACHE_MIN_CONFIDENCE_TO_REUSE=0.75
CACHE_TTL_DAYS=180
CACHE_REQUIRE_SAME_DOI=true
CACHE_REQUIRE_SAME_POLICY_VERSION=true
CACHE_REQUIRE_SAME_REFERENCE=false
CACHE_EVIDENCE_VERSION=evidence-v1
```

## Decision rules

Exact cache reuse requires the same normalized claim hash, same DOI, compatible versions, non-expired cache entry, and confidence above the configured threshold. Cache is never reused across different DOI values. Low-confidence results are not reused. `NEEDS_HUMAN_REVIEW` cache entries are returned safely with `recommended_action=NEEDS_HUMAN_REVIEW` and are not presented as confident automated verification.

Semantic cache is interface-only in BE-8. The local implementation can be enabled in tests using a lightweight mockable text similarity comparison. Real embeddings/vector search are deferred to BE-9.

## API endpoints

- `POST /api/v1/claims/{claim_id}/check-cache`
- `GET /api/v1/claims/{claim_id}/cache-result`

## What BE-8 intentionally does not implement

- real RAG retrieval
- embedding generation
- vector database search
- GenAI support verification
- final safety scoring
- report generation
- publisher full-text retrieval
- frontend UI

## Uploaded PDF validation

Validation was run on the three provided PDFs. Demo verification results were seeded for selected claim-reference pairs because BE-10 final verification does not exist yet. Cache decisions were manually checked for exact reuse, different DOI blocking, low-confidence blocking, and human-review safety. Full validation output is in `backend/validation/uploaded_pdf_validation_be8_output.txt`.
