# INT-QA-004 — Real RAG top_k handling

Finding ID: INT-QA-004  
Title: Real RAG ignores backend retrieval `top_k`  
Severity: P1  
Status: Closed  
Blocking: No / Resolved  
Component: RAG / Integration  
Phase impacted: BE9 / Integrated QA  
Endpoint/service: `RagDirectClient.retrieve`, `rag.api.retrieve_evidence`  
Test type: Integration / Unit / Manual

## Problem

The backend includes `retrieval_options.top_k`, but the direct adapter does not pass it and does not truncate the result.

## Steps to reproduce

Inspect:

- `backend/app/services/rag_ml_integration.py:281-316`
- `rag/api.py:57-62` and `rag/api.py:355-378`

## Expected result

Requests for `top_k=1`, `3`, or `5` return at most that many chunks.

## Actual result

RAG uses fixed `DOOR1_TOP_K=5`; `RetrieveEvidenceRequest` has no `top_k`; `RagDirectClient` ignores the backend `retrieval_options`; `RagResponseValidator` receives no requested limit and cannot enforce it.

## Evidence

Backend request-builder tests only prove that `top_k` is placed in the outgoing dictionary. RAG component tests prove internal retriever models honor their own `top_k`, but no adapter test proves propagation from the backend contract.

## Root cause hypothesis

The direct adapter was connected to an older fixed-size Door 1 API without updating the RAG request model or adding adapter-side truncation.

## Suggested fix direction

Add bounded `top_k` to Door 1 or truncate safely in the adapter and validate the count before persistence.

## Regression risk

High for contract compatibility, prompt size, latency, and evidence determinism.

## Validation required after fix

Real-adapter tests for `top_k=1`, `3`, `5`, and bounds, plus a staged real-RAG run.

## Closure note

Closed after independent QA re-validation on 2026-06-28. Door 1 and the direct
adapter respect bounded `top_k` values for 1, 3, omitted/default 5, below-minimum,
and above-maximum requests in mock and real-adapter paths. Score range and
non-finite validation also passed.
