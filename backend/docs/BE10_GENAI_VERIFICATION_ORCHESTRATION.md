# BE-10 — GenAI Verification Orchestration

## Purpose

BE-10 creates the first backend-controlled end-to-end verification orchestration layer. It coordinates earlier phase outputs and stores `VerificationResult` records for claim-reference pairs.

## Flow

1. Validate document exists and processed text is available.
2. Confirm references, DOI metadata state, claims, and evidence packages exist.
3. Create a `PipelineRun` and `PipelineStep` records.
4. Check BE-8 verification cache.
5. Reuse safe exact cache hits as `CACHE_ONLY` results.
6. For cache misses, call BE-9 retrieval service.
7. Send retrieved chunks to the backend-controlled GenAI verification service.
8. Validate GenAI JSON output before storage.
9. Apply basic BE-10 safety gates.
10. Store `VerificationResult` and `SafetyCheck` rows.
11. Index eligible new results into `ClaimCacheIndex`.
12. Return pipeline and verification summaries through API endpoints.

## GenAI verification contract

The backend sends only claim/evidence context, not the full paper:

```json
{
  "claim_id": "claim_001",
  "claim_text": "AI tools improve academic writing productivity.",
  "citation_text": "(Smith, 2023)",
  "doi_status": "VALID",
  "metadata": {"title": "...", "abstract": "..."},
  "retrieved_evidence": [{"chunk_id": "chunk_001", "chunk_text": "...", "similarity_score": 0.82}],
  "overall_similarity_score": 0.82
}
```

Expected response:

```json
{
  "support_status": "PARTIALLY_SUPPORTED",
  "confidence": 0.72,
  "explanation": "...",
  "evidence_used": ["chunk_001"],
  "limitations": "...",
  "human_review_required": true
}
```

## Allowed final support statuses

- `SUPPORTED`
- `PARTIALLY_SUPPORTED`
- `NOT_SUPPORTED`
- `INSUFFICIENT_EVIDENCE`
- `NEEDS_HUMAN_REVIEW`

The backend rejects unsupported labels such as `HALLUCINATED`, `TRUE`, `FALSE`, `VERIFIED`, or `UNKNOWN`.

## Basic BE-10 safety gates

BE-10 includes minimal safety gating only. BE-11 will harden this policy.

- Missing/malformed/invalid DOI → `NEEDS_HUMAN_REVIEW`
- `SOURCE_UNAVAILABLE` → `INSUFFICIENT_EVIDENCE` or review fallback
- No relevant RAG evidence → `INSUFFICIENT_EVIDENCE`
- Similarity below configured threshold → `NEEDS_HUMAN_REVIEW`
- GenAI confidence below `0.60` → `NEEDS_HUMAN_REVIEW`
- Invalid GenAI JSON → fallback review result

## Rerun/idempotency behavior

BE-10 stores multiple verification attempts with `PipelineRun` tracking. Result-list APIs return latest results per claim-reference pair to reduce frontend confusion.

## Uploaded-paper validation

The validation script `scripts/validate_uploaded_pdfs_be10.py` runs the current pipeline through uploaded research papers and uses mock RAG/GenAI services. It also seeds one demo cache row per paper to validate cache-hit orchestration. These seeded results are marked as demo validation data, not real final academic verification.

## Limitations

- Uses mock GenAI by default for local/sandbox validation.
- Uses mock RAG unless a real AI/ML/RAG service is configured.
- BE-10 safety gates are basic; BE-11 will implement deeper safety/confidence rules.
- BE-10 does not generate reports or feedback analytics.
- BE-10 does not replace human academic review.
