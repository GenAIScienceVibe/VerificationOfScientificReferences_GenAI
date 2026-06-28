# INT-QA-006 — RAG tests not included in integrated validation

Finding ID: INT-QA-006  
Title: Backend validation does not execute the root RAG test suite  
Severity: P1  
Status: Closed  
Blocking: Yes  
Component: Tests / Integration  
Phase impacted: Integrated QA  
Endpoint/service: Validation commands  
Test type: Regression / Integration

## Problem

Backend pytest and backend checks can pass without collecting any `tests/rag` tests.

## Steps to reproduce

```bash
cd backend
.venv/bin/pytest -q
.venv/bin/python scripts/run_backend_checks.py
cd ..
pytest tests/rag -q
backend/.venv/bin/pytest tests/rag -q --tb=short
```

## Expected result

A documented integrated validation path runs backend tests and RAG tests in working environments.

## Actual result

Backend suite passes 130 tests, but `backend/pytest.ini` restricts discovery to `backend/tests`. `run_backend_checks.py` does not run either pytest suite. Root `pytest` is not installed as a command, and the backend environment reports 11 RAG collection errors.

## Evidence

- `backend/pytest.ini`: `testpaths = tests` relative to backend.
- Root command: exit 127, `pytest: command not found`.
- Backend environment root-suite command: exit 2, 11 collection errors.

## Root cause hypothesis

The validation workflow remained backend-only after the RAG code was merged.

## Suggested fix direction

Provide a combined validation entry point or clearly sequenced backend and RAG environment commands that fail the overall run if either suite fails.

## Regression risk

High. A green backend build currently gives false confidence about live integration.

## Validation required after fix

Run the integrated command from a clean checkout/environment and retain separate suite counts.

## Closure note

Closed after independent re-validation on 2026-06-28. The integrated runner
executes the backend suite and root `tests/rag` suite, reports missing import
dependencies as `BLOCKED`, reports real test failures as `FAIL`, and returns a
non-zero aggregate result. In the live re-validation run it surfaced the RAG
cache-safety failure and ended with `INTEGRATED_VALIDATION_RESULT=FAIL`; no silent
pass occurred. Runner-focused tests passed: 6 tests.
