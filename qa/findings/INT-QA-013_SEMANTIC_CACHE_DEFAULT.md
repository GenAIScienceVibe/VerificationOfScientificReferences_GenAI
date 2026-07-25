# INT-QA-013 — semantic_cache_match default missing

Finding ID: INT-QA-013  
Title: Real RAG path does not provide the required semantic_cache_match default  
Severity: P2  
Status: Closed  
Blocking: No / Resolved  
Component: Integration  
Phase impacted: BE9 / Integrated QA  
Endpoint/service: `RetrieveEvidenceResponse`, `RagDirectClient`, `RagResponseValidator`  
Test type: Contract / Unit

## Problem

The backend-facing contract requires a stable default when semantic cache matching is unused, but the real response omits the field and the validator does not add it.

## Steps to reproduce

```bash
cd backend
.venv/bin/python -c "from app.services.rag_ml_integration import RagResponseValidator; p={'claim_id':'c','reference_id':'r','retrieval_status':'FAILED','top_chunks':[]}; print(RagResponseValidator().validate(p,claim_id='c',reference_id='r'))"
```

## Expected result

`semantic_cache_match` equals `{"matched": false, "cached_result_id": null, "similarity": null}` when unused.

## Actual result

Runtime probe returned `semantic_cache_match_present=False`. Mock RAG includes the correct object, but real `RetrieveEvidenceResponse` and `RagDirectClient` omit it and the validator only validates it when present.

## Evidence

- `rag/api.py:126-140`
- `backend/app/services/rag_ml_integration.py:104-114`, `300-316`
- Runtime validator probe.

## Root cause hypothesis

Mock and real adapter response builders evolved separately.

## Suggested fix direction

Normalize the default in the backend validator/adapter and align the real RAG response schema.

## Regression risk

Medium for clients and stored result consistency.

## Validation required after fix

Test successful, failed, empty-evidence, mock, and real responses for the exact default shape.

## Closure note

Closed after independent QA re-validation on 2026-06-28. The exact unmatched
semantic-cache default is present on success, failure, skipped, validation-error,
exception, and persistence paths, while a supplied valid semantic-cache match
is preserved.
