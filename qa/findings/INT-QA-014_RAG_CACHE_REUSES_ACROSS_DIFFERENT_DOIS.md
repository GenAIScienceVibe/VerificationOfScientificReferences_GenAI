# INT-QA-014 — RAG source embedding cache reuses across different DOIs

Finding ID: INT-QA-014  
Title: RAG source embedding cache reuses across different DOIs  
Severity: P1  
Status: Closed  
Blocking: No / Resolved  
Component: RAG cache / retrieval  
Phase impacted: BE9 / RAG Door 1 / Integrated QA  
Endpoint/service: `rag.api.retrieve_evidence`  
Test type: Unit / Integration / Regression

## Problem

Different DOI values must not reuse the same source embedding cache entry. Such
reuse can associate one cited source's cached embeddings with another DOI and
creates a high academic-correctness risk.

## Steps to reproduce

From the repository root:

```bash
backend/.venv/bin/python -m pytest tests/rag/test_api.py::test_retrieve_evidence_does_not_reuse_cache_across_different_dois -q --tb=short
```

The same failure is also exposed by:

```bash
cd backend
.venv/bin/python scripts/run_integrated_rag_checks.py
```

## Expected result

The source embedding/index cache is scoped by normalized DOI and source-text or
evidence identity. Two retrieval requests for different DOI values each embed or
load only their own source chunks.

## Actual result

The RAG regression test calls `retrieve_evidence` for `10.1111/aaa` and
`10.2222/bbb`, but observes only one source-chunk embedding call. The second DOI
request reuses the first request's cached source embeddings.

## Evidence

- `tests/rag/test_api.py::test_retrieve_evidence_does_not_reuse_cache_across_different_dois`
  failed with `AssertionError: assert 1 == 2`.
- Independent root RAG run: 1 failed, 352 passed.
- Integrated runner: `rag_pytest: FAIL` and
  `INTEGRATED_VALIDATION_RESULT=FAIL` with exit code 1.
- Inspection shows the current cache key prefers `reference_id` over DOI, so a
  reused reference identity can select cached embeddings despite a changed DOI.

## Root cause hypothesis

The source embedding cache key does not jointly bind the normalized DOI to the
source/evidence identity.

## Suggested fix direction

Include normalized DOI and source/evidence identity in the cache key, or disable
cross-DOI cache reuse.

## Regression risk

High academic correctness risk. Incorrect cross-source evidence can affect
retrieval ranking and downstream support decisions.

## Validation required after fix

Re-run the exact failing test, the complete root RAG suite, the backend suite,
and the integrated validation runner. Add or retain coverage for identical and
different DOI/source combinations.

## Closure note

Closed after independent QA re-validation. The RAG embedding cache key now
binds normalized DOI, reference ID, source URL, evidence availability, and
SHA-256 source-text fingerprint. The original cross-DOI cache reuse regression
passed, the full RAG suite passed, backend regression passed, and the integrated
runner returned `INTEGRATED_VALIDATION_RESULT=PASS`.
