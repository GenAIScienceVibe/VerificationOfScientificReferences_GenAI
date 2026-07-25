# Live RAG/ML Validation Protocol

## Purpose

This protocol validates that the integrated package works beyond mock mode. It must be run after dependency/runtime issues are fixed.

## Modes

### Mode 1 — Existing backend mock mode
```text
RAG_MOCK_MODE=true
GENAI_MOCK_MODE=true
METADATA_LOOKUP_ENABLED=false or mock
```
Validates backend orchestration, contracts, DB, safety, and reports.

### Mode 2 — Real RAG + mock GenAI
```text
RAG_MOCK_MODE=false
GENAI_MOCK_MODE=true
```
Validates real RAG retrieval while keeping LLM verification deterministic.
This is the first required live integration mode.

### Mode 3 — Real RAG + real GenAI
```text
RAG_MOCK_MODE=false
GENAI_MOCK_MODE=false
OPENROUTER_API_KEY=...
```
Optional until API keys and model access are available. Must not be claimed as passed unless actually run.

## Required validations

For each mode:
- backend app imports
- RAG imports if mode uses real RAG
- tests pass
- real PDFs process
- retrieval results stored
- similarity scores are 0–1
- top_k respected
- no unsupported labels
- safety rules applied
- reports generated

## Real PDF set

Use the private PDFs in:
```text
backend/tests/fixtures/private_pdfs/
```

## Manual checks

For each PDF:
- references and DOI counts reasonable
- no DOI-only bad rows
- evidence packages contain correct claim/reference/DOI
- real RAG chunks are connected to correct evidence package
- no full document is sent unnecessarily to RAG
- low/no evidence cases are safe
- report counts match backend data

## Pass criteria for Mode 2

- No import/dependency errors.
- Real RAG retrieval executes at least one successful retrieval where evidence text is available.
- Source-unavailable/metadata-only cases fail safely.
- Backend validator accepts all RAG responses.
- Pipeline succeeds or partial-fails with controlled standard errors.
