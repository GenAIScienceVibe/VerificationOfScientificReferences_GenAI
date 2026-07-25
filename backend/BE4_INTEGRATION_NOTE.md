# BE-4 Integration Note

BE-4 — Reference and DOI Extraction has been integrated into the existing full project structure under `backend/`.

This phase adds deterministic, rule-based reference extraction and DOI syntax extraction only. It preserves the final architecture boundary:

Frontend → Backend → AI/ML/RAG → Backend → Frontend  
AI/ML/RAG → Backend → External Academic Sources

No frontend, RAG, GenAI, CrossRef, OpenAlex, DOI Resolver, or Semantic Scholar logic was added in BE-4.

## New BE-4 endpoints

- `POST /api/v1/documents/{document_id}/extract-references`
- `GET /api/v1/documents/{document_id}/references`
- `GET /api/v1/references/{reference_id}`

## Database behavior

- Uses existing BE-2 `Reference` model.
- Persists parsed references in the `references` table.
- Sets `metadata_status = NOT_LOOKED_UP`.
- Updates `Document.references_count`.
- Updates document status to `REFERENCES_EXTRACTED` after successful extraction.
- Re-running extraction replaces existing references for the document to avoid duplicates.

## Deferred to BE-5+

- DOI existence validation
- CrossRef/OpenAlex metadata lookup
- claim extraction
- citation mapping
- evidence package building
- RAG retrieval
- GenAI verification
- report generation
