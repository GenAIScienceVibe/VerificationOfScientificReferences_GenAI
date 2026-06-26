# BE-8 Integration Note

This package implements BE-8 — Verification Cache Layer on top of the stable BE7 baseline. It preserves BE4.2, BE-5, BE-6, and BE-7 behavior.

BE-8 introduces:

- `VerificationCacheService`
- cache key normalization and hashing
- exact cache lookup
- cache decision schema
- mockable semantic cache interface
- cache index creation from `VerificationResult`
- `/claims/{claim_id}/check-cache`
- `/claims/{claim_id}/cache-result`

BE-8 does not call RAG, embeddings, GenAI verification, or final safety scoring.
