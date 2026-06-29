# Codex Agent Rules — Integrated Backend + RAG/ML Package

This repository contains the integrated verifAI / RefCheck AI backend plus RAG/ML code. Codex agents must treat this as a safety-critical academic reference-verification project.

## Non-negotiable architecture rule

Frontend → Backend → AI/ML/RAG → Backend → Frontend  
AI/ML/RAG → Backend → External Academic Sources

The backend remains the source of truth for orchestration, persistence, API responses, safety rules, reports, feedback, UAT data, and external academic metadata access. The frontend must not call RAG/ML or GenAI directly.

## Current known state

The previous BE13 backend passed final QA in mock RAG/GenAI mode. The latest shared package includes merged RAG/ML code and BE14-style full-text/source-PDF additions. The merged package is not yet accepted as live RAG/ML integrated until the integration issues are fixed and revalidated.

Known latest validation result:
- Backend compile: passed.
- Backend tests in mock mode: passed.
- OpenAPI/backend checks/demo pipeline: passed.
- Real RAG import/runtime: not validated and previously failed because RAG dependencies were missing.
- Root RAG tests: previously failed due missing dependencies.
- Real-PDF validation with integrated real RAG: not accepted yet.

## Agent roles

Use separate Codex conversations or separate tasks for:
1. Development Agent — implements planned integration fixes only.
2. QA Agent — validates without modifying production code.
3. Fixing Agent — fixes only QA findings.
4. Re-validation Agent — confirms fixes without modifying production code.

Do not let one agent implement and approve its own work.

## Final support statuses

Only these product-facing verification statuses are allowed:
- SUPPORTED
- PARTIALLY_SUPPORTED
- NOT_SUPPORTED
- INSUFFICIENT_EVIDENCE
- NEEDS_HUMAN_REVIEW

Do not introduce or return HALLUCINATED, TRUE, FALSE, VERIFIED, CONTRADICTED, UNKNOWN, or VALIDATED as final support statuses.

## Standard API wrappers

Success response:
```json
{
  "success": true,
  "data": {},
  "message": "Request completed successfully",
  "errors": [],
  "request_id": "req_12345"
}
```

Error response:
```json
{
  "success": false,
  "data": null,
  "message": "Validation failed",
  "errors": [
    {
      "code": "ERROR_CODE",
      "field": "field_name",
      "detail": "Human-readable detail."
    }
  ],
  "request_id": "req_12345"
}
```

## Critical protection rules

Never break:
- BE4.2 DOI/reference attachment quality.
- BE5 metadata safe-failure behavior.
- BE6 claim/citation mapping.
- BE7 evidence package structure.
- BE8 cache safety: never reuse across different DOI values.
- BE9 retrieval result validation.
- BE10 orchestration and final backend validation of GenAI output.
- BE11 safety/confidence rules.
- BE12 report/feedback/UAT behavior.
- BE13 demo hardening and standard wrappers.

## No uncontrolled scope expansion

Do not add new frontend work, new production authentication, OCR, publisher scraping, or broad architecture redesign unless explicitly requested.

## Before code changes

Before any production code edit, the agent must:
1. Read `.agent/shared_integrated_context.md`.
2. Read the role-specific agent file.
3. Inspect current code and tests.
4. Identify exact issue IDs being addressed.
5. Create/update QA report or finding files only when instructed.
6. Keep changes small, test-backed, and reversible.

## No Git assumption

The user may not have Git set up locally. When giving workflow advice, provide manual backup instructions first. Git commands may be optional only.
