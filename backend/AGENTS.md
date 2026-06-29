# Backend-Specific Codex Rules

This folder contains the FastAPI backend. The backend is already BE1–BE13 complete in mock RAG/GenAI mode and now includes integration changes for RAG/ML and source-PDF/full-text support.

## Backend responsibilities

The backend owns:
- FastAPI public `/api/v1/*` routes.
- Database models/repositories.
- File upload and text processing.
- Reference extraction and DOI extraction.
- DOI metadata lookup and safe failure handling.
- Claim/citation extraction and mapping.
- Evidence package building.
- Verification cache.
- RAG/ML client integration.
- GenAI verification orchestration.
- Safety/confidence rules.
- Report generation, feedback, UAT.
- QA/demo scripts.

## Current integration risk areas

Treat these as high-risk until fixed and revalidated:
- Real RAG dependency setup.
- Real RAG import when `RAG_MOCK_MODE=false`.
- Real GenAI verifier path when `GENAI_MOCK_MODE=false`.
- Metadata disabled mode still performing title-based DOI lookup.
- DOI status mapping into RAG, especially `FOUND → VALID`.
- Real RAG ignoring backend `top_k`.
- Direct Python import of RAG instead of service boundary.
- Source-PDF/full-text end-to-end validation.

## Required backend validation commands

Run from `backend/` where applicable:
```bash
.venv/bin/python -m compileall app scripts
.venv/bin/pytest -q
.venv/bin/python scripts/validate_openapi.py
.venv/bin/python scripts/run_backend_checks.py
.venv/bin/python scripts/run_demo_pipeline.py
.venv/bin/python scripts/validate_uploaded_pdfs_be13.py --pdf-dir tests/fixtures/private_pdfs
```

After real RAG integration fixes, also run an explicit real-RAG validation mode if added, for example:
```bash
RAG_MOCK_MODE=false GENAI_MOCK_MODE=true .venv/bin/python scripts/validate_uploaded_pdfs_be13.py --pdf-dir tests/fixtures/private_pdfs --real-rag --mock-genai
```

If such flags do not exist, Development Agent should add them or provide a separate real-RAG validator script.

## Do not hide external calls in mock mode

When metadata/RAG/GenAI is disabled or mocked, validation reports must clearly say so. Mock mode validates orchestration and contracts, not live answer quality.
