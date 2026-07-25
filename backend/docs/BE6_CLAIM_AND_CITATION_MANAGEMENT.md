# BE-6 — Claim and Citation Management

BE-6 adds backend-owned claim and citation management on top of the stable BE4.2 + BE-5 baseline.

## Scope implemented

- Selects body text from BE-3 `DocumentSection` records.
- Excludes `References`, `Bibliography`, `Works Cited`, `Reference List`, and appendix-like sections.
- Splits body text into paragraphs and sentences.
- Detects in-text citations deterministically before claim extraction.
- Uses a backend-controlled, mockable claim extraction client with the same JSON contract expected from a future Groq-backed internal GenAI service.
- Validates claim extraction output before database persistence.
- Stores `Claim`, `Citation`, `ClaimReferenceLink`, and `PromptRun` records.
- Maps APA/author-year and numbered citations to existing `Reference` records.
- Exposes frontend-facing APIs for claims, citations, and claim-reference links.

## Citation patterns supported

APA / author-year:

- `(Smith, 2023)`
- `(Smith & Lee, 2023)`
- `(Smith et al., 2023)`
- `(Smith, 2023; Lee, 2022)`
- `Smith (2023)`
- `Smith and Lee (2023)`

Numbered:

- `[1]`
- `[2, 3]`
- `[1-3]`
- `[1–3]`
- `(1)`
- `^1`

## Internal claim extraction contract

The backend prepares one citation-bearing sentence/chunk at a time:

```json
{
  "document_id": "doc_001",
  "section_name": "Introduction",
  "paragraph_id": "p_001",
  "text": "AI tools can improve writing productivity (Smith, 2023).",
  "detected_citations": ["(Smith, 2023)"]
}
```

Expected output shape:

```json
{
  "claims": [
    {
      "claim_text": "AI tools can improve writing productivity.",
      "citation_text": "(Smith, 2023)",
      "claim_type": "EMPIRICAL",
      "confidence": 0.88
    }
  ]
}
```

For local validation, the default `CLAIM_EXTRACTION_MODE=local_deterministic` avoids live GenAI calls. It is mockable in tests and can be replaced by a Groq-backed internal service later without changing persistence/API contracts.

## Validation rules

Backend rejects invalid model output before storing:

- invalid JSON
- missing `claims` array
- missing `claim_text`
- missing or invented `citation_text`
- unsupported `claim_type`
- confidence outside `0..1`
- claim text not grounded in the provided sentence

Failed prompt chunks are recorded in `PromptRun` and do not corrupt stored claims.

## Mapping strategy

- APA citations map by author surname + year against `Reference.extracted_authors`, `Reference.extracted_year`, `reference_key`, raw reference text, and available metadata.
- Numbered citations map by reference order.
- Multi-citation strings can create multiple links for one claim.
- `NO_MATCH`, `UNCERTAIN`, and `MULTIPLE_MATCHES` are stored safely.

## Public BE-6 endpoints

- `POST /api/v1/documents/{document_id}/extract-claims`
- `GET /api/v1/documents/{document_id}/claims`
- `GET /api/v1/claims/{claim_id}`
- `GET /api/v1/documents/{document_id}/citations`
- `GET /api/v1/documents/{document_id}/claim-reference-links`
- `GET /api/v1/claim-reference-links/{link_id}`
- `GET /api/v1/documents/{document_id}/claim-reference-map` compatibility alias

## Duplicate handling

For MVP/demo reliability, rerunning `extract-claims` replaces existing BE-6 claim/citation/link records for the document. This avoids repeated duplicate inserts.

## What BE-6 intentionally does not implement

- Evidence package creation
- Verification cache
- RAG retrieval
- Semantic similarity scoring
- GenAI support verification
- Final support labels
- Safety scoring
- Report generation
- Publisher full-text retrieval

## Uploaded research-paper validation

The validation script is:

```bash
python scripts/validate_uploaded_pdfs_be6.py --reset-db <pdf1> <pdf2> <pdf3>
```

It runs BE-3 upload/text extraction, BE4.2 reference/DOI extraction, and BE-6 claim/citation extraction/mapping. `--verify-dois` may be added to attempt BE-5 live metadata lookup, but this depends on external network availability.
