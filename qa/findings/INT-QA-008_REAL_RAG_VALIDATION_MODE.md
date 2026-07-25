# INT-QA-008 — Real-RAG validation mode missing

Finding ID: INT-QA-008  
Title: No staged real-RAG + mock-GenAI PDF validation mode exists  
Severity: P1  
Status: Closed  
Blocking: No / Resolved  
Component: Tests / Integration  
Phase impacted: Integrated QA  
Endpoint/service: `validate_uploaded_pdfs_be13.py`  
Test type: Real PDF / Integration

## Problem

The required Mode 2 validator (`RAG_MOCK_MODE=false`, `GENAI_MOCK_MODE=true`) is absent or cannot select real retrieval.

## Steps to reproduce

```bash
cd backend
.venv/bin/python scripts/validate_uploaded_pdfs_be13.py --help
```

## Expected result

The validator exposes an explicit real-RAG/mock-GenAI mode, does not force `use_mock`, labels output accurately, and checks real retrieval persistence/contracts.

## Actual result

Only positional PDFs, `--pdf-dir`, and `--reset-db` exist. The script defaults both mocks true, calls retrieval with `use_mock: true`, and hard-codes `retrieval_mode: Mock RAG` / `verification_mode: Mock GenAI`.

## Evidence

- `backend/scripts/validate_uploaded_pdfs_be13.py:12-22`
- `backend/scripts/validate_uploaded_pdfs_be13.py:145`
- `backend/scripts/validate_uploaded_pdfs_be13.py:227-230`
- Help output has no `--real-rag` or `--mock-genai` option.

## Root cause hypothesis

The validator predates merged live RAG and was not extended for staged acceptance.

## Suggested fix direction

Add a clear Mode 2 path or separate validator after resolving dependencies; prevent explicit mock overrides and assert at least one successful real retrieval.

## Regression risk

High. Mock validation can otherwise be mistaken for live integration acceptance.

## Validation required after fix

Run all three PDFs in Mode 2 and verify score bounds, `top_k`, provenance, safe no-evidence handling, storage, safety, and reports.

## Closure note

Closed after independent QA re-validation. The uploaded-PDF validator now supports explicit Mock RAG + Mock GenAI and staged Real RagDirectClient + Mock GenAI modes. The required staged mode exercises the real backend adapter, request builder, RAG contract model, response validation, persistence, pipeline orchestration, mock GenAI, BE10/BE11 safety, reporting, feedback, UAT, and packaging-safety checks without requiring real GenAI or live embeddings. Optional real GenAI/live-embedding modes are API-key guarded. Mock and real-adapter validation passed on the available local ignored/private PDFs, full backend/RAG regressions passed, OpenAPI/check/demo/integrated runner passed, and release scan/build remained clean with zero unsafe/PDF/DB/.env entries. Live embedding quality and real GenAI output quality remain outside this staged validation.
