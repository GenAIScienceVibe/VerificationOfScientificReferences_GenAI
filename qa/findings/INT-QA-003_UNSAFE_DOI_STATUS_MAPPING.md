# INT-QA-003 — Unsafe DOI status mapping

Finding ID: INT-QA-003  
Title: Backend FOUND DOI status maps to RAG VALID  
Severity: P1  
Status: Closed  
Blocking: No / Resolved  
Component: Integration  
Phase impacted: BE9 / BE10 / BE11  
Endpoint/service: `RagRequestBuilder`, `RealGenAiVerificationClient`  
Test type: Unit / Manual

## Problem

`FOUND` means extracted but not metadata-verified, yet both real retrieval and real Door 2 adapters map it to RAG `VALID`.

## Steps to reproduce

```bash
cd backend
.venv/bin/python -c "from app.services.rag_ml_integration import _DOI_STATUS_TO_RAG; print(_DOI_STATUS_TO_RAG)"
```

Inspect `backend/app/services/genai_verification.py` lines 129-134.

## Expected result

Only backend `VALID` maps to RAG `VALID`. `FOUND`, `MISSING`, `MALFORMED`, `LOOKUP_FAILED`, and `INVALID` must not become RAG `VALID`.

## Actual result

Observed mapping: `FOUND->VALID`, `VALID->VALID`, `MISSING->UNRESOLVABLE`, `LOOKUP_FAILED->UNRESOLVABLE`, `MALFORMED->INVALID`, `INVALID->INVALID`. The same unsafe `FOUND->VALID` mapping exists in the real GenAI client.

## Evidence

- `backend/app/services/rag_ml_integration.py:23-31`
- `backend/app/services/genai_verification.py:129-134`
- Runtime mapping probe reproduced the mapping.

## Root cause hypothesis

Extraction success was conflated with metadata resolution/validation during backend-to-RAG enum adaptation.

## Suggested fix direction

Map `FOUND` to `UNRESOLVABLE` or stop before real retrieval/verification until explicit validation changes the backend status to `VALID`.

## Regression risk

High. Claims may be checked against unverified or wrongly attached identifiers.

## Validation required after fix

Add table-driven tests for every backend DOI status in both the Door 1 and Door 2 adapters and rerun BE4.2/BE5/BE11 safety regression suites.

## Closure note

Closed after independent QA re-validation on 2026-06-28. Door 1 and Door 2
map only backend `VALID` to RAG `VALID`; all six known statuses and the unknown
status fallback passed focused validation, backend regression, and integrated
validation.
