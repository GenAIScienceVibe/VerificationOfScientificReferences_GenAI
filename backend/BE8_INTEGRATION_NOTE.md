# BE-8 Integration Note

Implemented BE-8 — Verification Cache Layer on top of BE-7 (Evidence Package Builder).

Key protection rule: All upstream services (evidence packages, metadata, claims) were preserved. BE-8 adds a cache check layer that sits in front of BE-9 (GenAI Verification) without changing any existing behavior.

Exact cache lookup is fully functional: claims are normalized (lowercase, punctuation removed) and hashed via SHA256, then matched against ClaimCacheIndex by hash + DOI + version keys. Cache rules (EXACT / SEMANTIC_HIGH / SEMANTIC_MEDIUM / MISS) are fully defined and the response structure is ready for the frontend.

Cache source field (NEW_VERIFICATION / EXACT_CACHE / SEMANTIC_CACHE / HUMAN_CORRECTED) already exists on the VerificationResult model and is ready to be set by BE-9.

Placeholder — Task 2 (Semantic cache): _semantic_lookup_placeholder() in cache_service.py always returns None. Real embedding computation and vector store lookup must be added by the RAG team. Requires infrastructure decision: external embedding service (e.g. OpenAI) or local vector store (e.g. pgvector, which requires switching from SQLite to PostgreSQL).

Placeholder — Task 4 (Store cache metadata): store_cache_entry() is fully implemented and writes to ClaimCacheIndex correctly, but is never called because VerificationResult objects do not exist yet. BE-9 must call store_cache_entry() after every successful verification.
Placeholder — Task 5 (cache_source on VerificationResult): The field and all four enum values exist in the model but are never set because VerificationResult rows are not created yet. BE-9 must set this field when writing verification results.

Version constants in evidence_service.py and cache_service.py (EMBEDDING_MODEL_VERSION, PROMPT_VERSION, VERIFICATION_POLICY_VERSION, EVIDENCE_VERSION) form part of the cache key and must stay in sync. If the RAG team uses a different model or prompt version, both files must be updated consistently.