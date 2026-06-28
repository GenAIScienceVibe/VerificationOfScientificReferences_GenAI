# INT-QA-009 — Real RAG chunk traceability gap

Finding ID: INT-QA-009  
Title: Real RAG drops source and source_url from returned chunks  
Severity: P2  
Status: Closed  
Blocking: No / Resolved  
Component: RAG / Integration  
Phase impacted: BE9 / BE11 / Integrated QA  
Endpoint/service: `TopChunkResult`, `RagDirectClient`  
Test type: Contract / Integration

## Problem

The input carries `source_url`, but the real Door 1 output model and adapter omit both chunk `source` and `source_url`.

## Steps to reproduce

Inspect `rag/ingestion/models.py:21-26`, `rag/api.py:117-140`, and `backend/app/services/rag_ml_integration.py:300-315`.

## Expected result

Backend-facing chunks preserve available source identity/URL so persisted evidence is auditable.

## Actual result

`SourceEvidence.source_url` is accepted, but `TopChunkResult` has only ID, text, score, and evidence type. `RagDirectClient` serializes only those fields. Mock RAG includes source fields, so mock tests do not reveal the real-path loss.

## Evidence

Static contract inspection; live execution is blocked by INT-QA-001.

## Root cause hypothesis

Provenance was not propagated from request/source metadata through chunk models to the adapter response.

## Suggested fix direction

Add provenance fields to backend-facing real chunk output and test persistence without exposing private local paths or sensitive data.

## Regression risk

Medium to high for academic auditability and report traceability.

## Validation required after fix

Real retrieval from abstract and uploaded full text must preserve expected source/source_url through API response and database storage.

## Closure note

Closed after independent QA re-validation on 2026-06-28. Real-adapter chunks
carry a stable source label and safe public source URL; local paths,
credential-bearing URLs, localhost, and private addresses are removed, and
validated provenance persists through the backend retrieval result.
