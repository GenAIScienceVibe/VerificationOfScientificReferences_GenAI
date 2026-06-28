# INT-QA-005 — Direct Python RAG service-boundary risk

Finding ID: INT-QA-005  
Title: Direct Python RAG integration is undocumented and bypasses configured HTTP boundary  
Severity: P2  
Status: Open  
Blocking: No  
Component: Integration / Docs  
Phase impacted: BE9 / Integrated QA  
Endpoint/service: `RagMlClient`, `RagDirectClient`  
Test type: Manual / Architecture

## Problem

Real mode always selects an in-process `rag.api` import, while `RAG_SERVICE_URL`, retry, timeout, and HTTP adapter settings remain documented and configured.

## Steps to reproduce

Inspect `backend/app/services/rag_ml_integration.py:270-366` and backend README BE9 configuration.

## Expected result

The accepted deployment boundary is explicit and the runtime/configuration match it.

## Actual result

`RagMlClient.retrieve` calls `RagDirectClient`; the HTTP method is named `_http_retrieve_unused`. Backend README still presents `RAG_SERVICE_URL`, retry, and timeout settings without explaining that real retrieval ignores them.

## Evidence

- Direct client mutates `sys.path` at runtime to import the repository-root package.
- Literal backend-folder import cannot find `rag` unless the direct client is instantiated first or `PYTHONPATH` is adjusted.
- No `/internal/rag/retrieve-evidence` service implementation or health/readiness validation was found.

## Root cause hypothesis

The merge chose an in-process demo shortcut without completing the architecture decision and documentation.

## Suggested fix direction

Formally accept and document in-process integration with a combined environment, or restore the RAG HTTP service boundary and remove dead/misleading configuration.

## Regression risk

Medium. Deployment, dependency isolation, retries, health checks, and scaling behavior differ materially.

## Validation required after fix

Validate the selected boundary from a clean setup and verify health/readiness, failure handling, and backend ownership.

## Closure note

Open as of 2026-06-28. Non-blocking only if in-process mode is explicitly accepted for the demo.
