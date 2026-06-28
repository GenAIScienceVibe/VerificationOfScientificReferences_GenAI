# BE-9 — RAG/ML Integration

BE-9 connects the backend to the AI/ML/RAG layer through a backend-controlled contract. It does not implement embeddings, vector search, RAG algorithms, GenAI verification, final support labels, safety scoring, reports, or frontend UI.

## Purpose

BE-9 sends BE-7 evidence packages to an internal RAG/ML service, validates the response, persists retrieval results, and exposes retrieval APIs for later BE-10 orchestration.

## Backend-to-RAG request contract

`POST /internal/rag/retrieve-evidence`

The backend sends only curated evidence package data:

- document_id
- claim_id
- reference_id
- evidence_package_id
- claim_text
- citation_text
- DOI and DOI status
- metadata from BE-5 or BE-7 fallback
- source_evidence from BE-7
- retrieval options
- policy/version metadata

The backend does not send the full uploaded paper unless a future evidence package explicitly contains legal full text.

## RAG response contract

The RAG/ML service returns retrieval-quality information only:

- retrieval_status
- top_chunks
- similarity scores
- retrieval confidence
- optional semantic_cache_match

BE-9 rejects responses that contain final support labels such as SUPPORTED or NOT_SUPPORTED. Final verification belongs to BE-10 and BE-11.

## Mock mode vs real RAG mode

Local/demo mode defaults to:

```env
RAG_MOCK_MODE=true
RAG_SERVICE_URL=http://localhost:9000
```

Mock mode returns deterministic chunks from available BE-7 evidence text/metadata. It is not final RAG quality.

Real mode uses `httpx` to call:

```text
{RAG_SERVICE_URL}/internal/rag/retrieve-evidence
```

## Timeout and retry behavior

Configured by:

```env
RAG_SERVICE_TIMEOUT_SECONDS=30
RAG_SERVICE_MAX_RETRIES=1
```

Timeouts and service failures are converted into controlled API errors and failure retrieval records.

## Response validation rules

BE-9 validates:

- claim_id and reference_id match the request
- retrieval_status is allowed
- top_chunks is a list
- chunk_text exists
- similarity scores are between 0 and 1
- retrieval_confidence is between 0 and 1
- semantic_cache_match structure is valid
- final support_status labels are not returned in BE-9

Invalid responses are not stored as successful retrievals.

## Retrieval result persistence

Retrieval attempts are stored in `rag_retrieval_results` with:

- document_id
- claim_id
- reference_id
- evidence_package_id
- retrieval_status
- top_chunks_json
- overall_similarity_score
- retrieval_confidence
- semantic_cache_match_json
- request_payload_summary
- response_payload_json
- error_message

## Semantic cache handoff

BE-9 can accept and store semantic cache match information from the RAG/ML response. It does not automatically reuse semantic cache results as final verification.

## APIs

- `POST /api/v1/claims/{claim_id}/retrieve-evidence`
- `GET /api/v1/claims/{claim_id}/retrieval-results`

## What BE-9 intentionally does not implement

- RAG internals
- embeddings
- vector database setup
- final GenAI verification
- final support labels
- final safety scoring
- reports
- publisher full-text retrieval
