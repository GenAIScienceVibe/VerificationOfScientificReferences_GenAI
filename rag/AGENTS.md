# RAG/ML-Specific Codex Rules

This folder contains the RAG/ML code. It must integrate with the backend without taking over backend responsibilities.

## RAG responsibilities

RAG/ML may own:
- Source-evidence cleaning.
- Chunking.
- Embeddings.
- Vector retrieval.
- BM25/hybrid retrieval if implemented.
- Reranking if implemented.
- Retrieval scoring.
- RAG-only unit tests.

RAG/ML must not own:
- Public frontend API.
- Document upload/persistence.
- DOI metadata lookup to external academic sources unless backend explicitly provides the data.
- Final support status authority.
- Backend safety/confidence overrides.
- Reports, feedback, UAT.

## Backend-facing retrieval contract

A backend-facing real RAG result must satisfy backend BE9 validation:
- retrieval_status must be a backend-accepted value.
- all scores must be between 0 and 1.
- top_chunks must include chunk_id, chunk_text, similarity_score, evidence_type.
- source and source_url should be populated by the adapter when available.
- semantic_cache_match should default to `{matched:false,cached_result_id:null,similarity:null}` when not used.
- no unsupported final verification labels should be produced by retrieval.

## Critical integration rules

- Do not return weighted scores above 1.0 as backend-facing similarity scores.
- Use weighted scores internally for ranking only.
- Respect backend `top_k`.
- Handle missing/unavailable source evidence safely.
- Do not treat backend `FOUND` DOI as validated `VALID` unless metadata has verified it.
- If no source text exists, return no-evidence safely; do not invent evidence.
- Door 1 retrieval must be validated before Door 2 verification is enabled.
