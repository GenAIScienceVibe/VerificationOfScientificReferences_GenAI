# INT-QA-001 — Real RAG dependency and import readiness

Finding ID: INT-QA-001  
Title: Real RAG cannot import or collect its tests in the backend runtime  
Severity: P1  
Status: Closed  
Blocking: Yes  
Component: RAG / Integration  
Phase impacted: BE9 / BE10 / Integrated QA  
Endpoint/service: `rag.api`, `RagDirectClient`  
Test type: Integration / Unit

## Problem

The installed backend environment does not contain the RAG dependency set, so Door 1 and Door 2 cannot be imported and real RAG cannot run.

## Steps to reproduce

From the repository root:

```bash
backend/.venv/bin/python -c "from rag.api import retrieve_evidence, verify_claim; print('rag imports ok')"
backend/.venv/bin/pytest tests/rag -q --tb=short
PYTHONPATH=backend RAG_MOCK_MODE=false GENAI_MOCK_MODE=true backend/.venv/bin/python -c "from app.services.rag_ml_integration import RagDirectClient; RagDirectClient(); from rag.api import retrieve_evidence; print('real rag import ok')"
```

## Expected result

Imports succeed and the RAG test suite collects and runs in the documented integrated environment.

## Actual result

`rag.api` fails first on `ModuleNotFoundError: No module named 'tiktoken'`. RAG pytest stops with 11 collection errors. Missing imports include `tiktoken`, `openai`, `rank_bm25`, `flashrank`, `jinja2`, `numpy`, `faiss`, and `langchain_text_splitters`.

## Evidence

- `backend/requirements.txt` contains backend dependencies only.
- `rag/requirements.txt` contains the missing RAG dependencies, but they are not installed in `backend/.venv`.
- Import probes: cleaner imports, while chunker, embedder, vector store, BM25, hybrid retrieval, and `rag.api` fail.
- Door 2 models import, but classifier fails without `openai` and verifier/validator fail without `jinja2`.

## Root cause hypothesis

The package has two requirement files but no installed or documented combined runtime/service environment for the direct Python adapter.

## Suggested fix direction

Choose and document either a combined environment containing both requirement sets or a separately deployed RAG service. Validate version compatibility and provide one repeatable integrated setup command.

## Regression risk

High. Dependency changes can destabilize the backend environment or make direct imports platform-specific.

## Validation required after fix

Run both import commands, all RAG tests, backend tests, and a staged real-RAG + mock-GenAI retrieval against source text.

## Closure note

Closed after independent re-validation on 2026-06-28. The combined dependency
manifest includes both backend and RAG requirements, `pip check` reports no
broken requirements, and both `rag.api` and `RagDirectClient` import successfully
with `OPENROUTER_API_KEY` removed. `GENAI_MOCK_MODE=true` selects the mock GenAI
client without constructing real Door 2. The root RAG suite now imports, collects,
and runs all 353 tests; its separate DOI cache-isolation failure is tracked as
INT-QA-014 and does not reopen dependency/import readiness.
