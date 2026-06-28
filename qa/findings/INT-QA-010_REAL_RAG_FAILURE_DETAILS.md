# INT-QA-010 — Real RAG failure details gap

Finding ID: INT-QA-010  
Title: Real RAG failures lose structured cause details  
Severity: P2  
Status: Closed  
Blocking: No / Resolved  
Component: RAG / Integration  
Phase impacted: BE9 / Integrated QA  
Endpoint/service: `retrieve_evidence`, `RagDirectClient`, `RagRetrievalService`  
Test type: Contract / Integration

## Problem

Door 1 converts broad exceptions into a bare `FAILED` response. The direct adapter and backend validator do not carry structured failure details, so persisted real failures can have `error_message=None`.

## Steps to reproduce

Inspect `rag/api.py:214-220`, `381-386`; `backend/app/services/rag_ml_integration.py:300-316`, `455-465`.

## Expected result

Failures are safe and include a backend-approved structured category/detail suitable for logs and QA without leaking secrets.

## Actual result

All pipeline exceptions collapse to `FAILED` with empty chunks and zero scores. A validator probe confirmed no `error`, `errors`, or `error_message` is required/present. The successful validation path stores no error message even when retrieval status is `FAILED`.

## Evidence

Runtime probe: `failed_error_detail_present=False`. Live failure execution is additionally blocked by missing dependencies.

## Root cause hypothesis

The RAG response contract models status but not a sanitized error object, and the backend treats any schema-valid response as a non-exceptional completion.

## Suggested fix direction

Define a small allow-listed failure-code/detail contract and persist it for non-success statuses while keeping sensitive exception text in controlled logs.

## Regression risk

Medium. Changes affect failure response validation and persistence.

## Validation required after fix

Exercise missing key, embedding error, chunking-empty, reranker fallback, and internal exception cases; verify stable status and sanitized detail.

## Closure note

Closed after independent QA re-validation. Failed RAG details are sanitized at
validation and persistence boundaries. Raw traceback text, local paths, file
URLs, token/key/secret/password/bearer patterns, and stack-like details are
replaced by the approved safe fallback. Safe approved messages are preserved.
Backend regression, RAG regression, OpenAPI/check/demo, and integrated
validation passed.
