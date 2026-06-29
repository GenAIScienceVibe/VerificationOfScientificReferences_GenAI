# verifAI / RefCheck AI Backend

FastAPI backend for the verifAI / RefCheck AI Generative AI course project.

Current implementation status:

- BE-1 — Backend Foundation: implemented
- BE-2 — Database Design: implemented
- BE-3 — Document Upload and Text Processing: implemented
- BE-4 — Reference and DOI Extraction: implemented
- BE-4.2 — DOI Attachment, Reference Continuation, and Extraction Quality Hardening: implemented
- BE-5 — DOI Metadata Lookup: implemented
- BE-6 — Claim and Citation Management: implemented
- BE-7 — Evidence Package Builder: implemented
- BE-8 — Verification Cache Layer: implemented
- BE-9 — RAG/ML Integration: implemented
- BE-10 — GenAI Verification Orchestration: implemented
- BE-11 — Safety and Confidence Rules: implemented
- BE-12 — Report Generation and Feedback: implemented
- BE-13 — Testing, Logging, and Demo Hardening: implemented

External metadata, RAG, and GenAI behavior can run in disabled, mock, or demo mode depending on environment configuration. Mock/demo mode validates backend orchestration and contracts, not final AI/RAG answer quality.

## Backend scope

The backend is the central orchestrator:

```text
Frontend → Backend → AI/ML/RAG → Backend → Frontend
AI/ML/RAG → Backend → External Academic Sources
```

Frontend, RAG, GenAI, and external academic services must not write directly to the database. In BE-3, raw uploaded documents are processed only by the backend and are not sent to AI/RAG services.

## Implemented in BE-1

- FastAPI app
- `/api/v1` router
- health/readiness endpoints
- response/error wrapper
- request ID middleware
- structured logging foundation
- environment configuration
- SQLite local database connection foundation
- initial document stub endpoints

## Implemented in BE-2

- SQLAlchemy model set for the full backend verification workflow
- 18 database tables
- required enums/status constants
- relationships and indexes
- thin repository/data-access layer
- local/demo database initialization script
- seed/demo data script
- database-backed document records
- database/model/repository tests

## Implemented in BE-3

- PDF upload validation
- safe local file storage using internal document IDs
- PyMuPDF text extraction for text-based PDFs
- plain text submission processing
- raw and cleaned text persistence
- rule-based broad section detection
- `DocumentSection` persistence
- document details/status/sections/raw-text endpoints
- BE-3 document-processing tests


## Implemented in BE-4

- deterministic references-section detection from BE-3 `DocumentSection` records and `cleaned_text` fallback
- rule-based individual reference splitting for APA-style, numbered, bracketed, blank-line separated, and multi-line references
- DOI extraction using regex with support for `doi:`, `DOI:`, `https://doi.org/`, and `http://dx.doi.org/` formats
- DOI normalization to lowercase DOI values without URL/prefix or obvious trailing punctuation
- BE-4 DOI statuses: `FOUND`, `MISSING`, and `MALFORMED`
- `Reference` database persistence with `metadata_status = NOT_LOOKED_UP`
- idempotent re-run behavior by replacing existing extracted references for the document
- document `references_count` and status update to `REFERENCES_EXTRACTED`
- reference APIs:
  - `POST /api/v1/documents/{document_id}/extract-references`
  - `GET /api/v1/documents/{document_id}/references`
  - `GET /api/v1/references/{reference_id}`
- BE-4 reference/DOI tests and fixtures

## Implemented in BE-4.2

- hardened references-section boundary detection
- conservative repeated header/footer/page-artifact cleanup
- DOI line-continuation repair before extraction
- stricter malformed DOI detection
- improved APA/numbered/bracketed/multi-line reference splitting
- false-positive filtering for URL-only, page-only, footer, and survey artifacts
- enum validation for `doi_status` and `metadata_status` filters
- `/raw-text` debug endpoint disabled by default via `ENABLE_RAW_TEXT_DEBUG_ENDPOINT`
- failed PDF audit visibility by returning failed `document_id` in error detail
- destructive reference re-extraction blocked when downstream rows already exist
- sanitized real-PDF regression fixtures and `scripts/qa_real_pdf_api_test.py`

## Setup

Backend-only mock setup:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For the current direct-Python Backend + RAG integration, install the combined
manifest from the repository root instead:

```bash
python -m venv backend/.venv
backend/.venv/bin/python -m pip install -r requirements-integrated.txt
```

This installs both backend and `rag/requirements.txt` dependencies into
`backend/.venv`. Importing `rag.api` does not require `OPENROUTER_API_KEY`; a key
is required only when live embeddings or real Door 2 calls execute.

## Configuration

Edit `.env`:

```env
APP_NAME="verifAI / RefCheck AI Backend"
APP_VERSION="1.0.0"
ENVIRONMENT="local"
API_PREFIX="/api/v1"
DATABASE_URL="sqlite:///./data/refcheck_be4_2.db"
ENABLE_RAW_TEXT_DEBUG_ENDPOINT="false"
FILE_STORAGE_DIR="./data/uploads"
MAX_UPLOAD_SIZE_BYTES="10485760"
GROQ_MODEL="meta-llama/llama-4-scout-17b-16e-instruct"
```

Do not commit real secrets such as `GROQ_API_KEY`.

## Initialize the database

```bash
python scripts/init_db.py
```

Optional BE-2 demo data:

```bash
python scripts/seed_demo_data.py
```

## Run backend

```bash
uvicorn app.main:app --reload
```

Swagger docs:

```text
http://127.0.0.1:8000/docs
```

## Test APIs

Health:

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/health/readiness
```

Submit text:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/text \
  -H "Content-Type: application/json" \
  -d '{"title":"Demo Scientific Text","text":"Demo Paper\n\nAbstract\nGenerative AI tools can improve writing (Smith, 2023).\n\nReferences\nSmith, J. (2023). Demo paper. doi:10.1234/demo"}'
```

Upload PDF:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload \
  -F "file=@sample.pdf" \
  -F "document_title=Demo PDF"
```

Inspect document:

```bash
curl http://127.0.0.1:8000/api/v1/documents/{document_id}
curl http://127.0.0.1:8000/api/v1/documents/{document_id}/status
curl http://127.0.0.1:8000/api/v1/documents/{document_id}/sections
curl http://127.0.0.1:8000/api/v1/documents/{document_id}/raw-text
```

Extract and inspect references:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/{document_id}/extract-references
curl http://127.0.0.1:8000/api/v1/documents/{document_id}/references
curl "http://127.0.0.1:8000/api/v1/documents/{document_id}/references?doi_status=FOUND"
curl http://127.0.0.1:8000/api/v1/references/{reference_id}
```

Run real-PDF QA locally:

```bash
python scripts/qa_real_pdf_api_test.py /path/to/pdf1.pdf /path/to/pdf2.pdf
```

## Run validation

```bash
python -m compileall app
python -c "from app.main import app; print(app.title, app.version, len(app.openapi()['paths']))"
python scripts/init_db.py
pytest -q
```

## Documentation

See:

```text
docs/BE2_DATABASE_DESIGN.md
docs/BE3_DOCUMENT_UPLOAD_AND_TEXT_PROCESSING.md
docs/BE4_REFERENCE_AND_DOI_EXTRACTION.md
docs/BE4_2_REFERENCE_HARDENING.md
```


## BE-4.2 DOI quality endpoints/diagnostics

`POST /api/v1/documents/{document_id}/extract-references` now returns `doi_coverage` and `quality_warnings`. DOI existence validation is still BE-5 and no external metadata service is called in BE-4.2.

Run real-PDF QA:

```bash
python scripts/qa_real_pdf_api_test.py /path/to/pdf1.pdf /path/to/pdf2.pdf
```

## BE-5 - DOI Metadata Lookup

BE-5 builds on the stable BE4.2 baseline and adds backend-controlled DOI metadata lookup.

### New endpoints

```text
POST /api/v1/references/{reference_id}/verify-doi
POST /api/v1/documents/{document_id}/verify-dois
GET  /api/v1/references/{reference_id}/metadata
```

### Metadata configuration

```env
METADATA_LOOKUP_ENABLED=true
CROSSREF_BASE_URL=https://api.crossref.org
DOI_RESOLVER_BASE_URL=https://doi.org
OPENALEX_BASE_URL=https://api.openalex.org
METADATA_SERVICE_TIMEOUT_SECONDS=10
METADATA_MAX_RETRIES=2
CROSSREF_MAILTO=
METADATA_USER_AGENT=verifai-refcheck-backend/1.0.0
```

### Typical BE-5 flow

```bash
python scripts/init_db.py
uvicorn app.main:app --reload
```

1. Upload PDF or submit text.
2. Extract references.
3. Verify one reference DOI or all document DOIs.
4. Retrieve stored metadata.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/references/{reference_id}/verify-doi
curl -X POST http://127.0.0.1:8000/api/v1/documents/{document_id}/verify-dois
curl http://127.0.0.1:8000/api/v1/references/{reference_id}/metadata
```

BE-5 does not perform claim extraction, citation mapping, RAG retrieval, GenAI verification, full-text retrieval, report generation, or final support scoring.

### Uploaded PDF validation helper

```bash
python scripts/validate_uploaded_pdfs_be5.py --reset-db --attempt-live-metadata /path/to/paper1.pdf /path/to/paper2.pdf
```

Live metadata lookup requires internet/DNS access. In restricted environments, unit tests use mocked CrossRef responses.

## BE-6 — Claim and Citation Management

This package includes BE-6 claim/citation management. After BE-3 document processing, BE4.2 reference/DOI extraction, and optional BE-5 DOI metadata lookup, run:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/{document_id}/extract-claims \
  -H "Content-Type: application/json" \
  -d '{"mode":"citation_linked_only"}'
```

Then inspect:

```text
GET /api/v1/documents/{document_id}/claims
GET /api/v1/documents/{document_id}/citations
GET /api/v1/documents/{document_id}/claim-reference-links
GET /api/v1/claims/{claim_id}
GET /api/v1/claim-reference-links/{link_id}
```

BE-6 does not verify claim support. Evidence building, RAG, GenAI verification, safety scoring, and reports remain later phases.

## BE-7 — Evidence Package Builder

BE-7 is now implemented. It prepares structured evidence packages from BE-6 claim-reference links. It does **not** call RAG/ML, generate embeddings, run GenAI verification, retrieve publisher full text, or create final support labels.

### BE-7 endpoints

```text
POST /api/v1/documents/{document_id}/prepare-evidence
GET  /api/v1/claims/{claim_id}/evidence-package
GET  /api/v1/documents/{document_id}/evidence-packages
```

### BE-7 run flow

```bash
python scripts/init_db.py
uvicorn app.main:app --reload
```

Then run the available pipeline up to BE-7:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/{document_id}/extract-references
curl -X POST http://127.0.0.1:8000/api/v1/documents/{document_id}/verify-dois
curl -X POST http://127.0.0.1:8000/api/v1/documents/{document_id}/extract-claims -H "Content-Type: application/json" -d '{"mode":"citation_linked_only"}'
curl -X POST http://127.0.0.1:8000/api/v1/documents/{document_id}/prepare-evidence
```

### BE-7 validation

```bash
python -m compileall app
python scripts/init_db.py
pytest -q
python scripts/validate_uploaded_pdfs_be7.py --reset-db /path/to/paper1.pdf /path/to/paper2.pdf /path/to/paper3.pdf
```

See `docs/BE7_EVIDENCE_PACKAGE_BUILDER.md` and `validation/BE7_VALIDATION_REPORT.md`.

## BE-8 — Verification Cache Layer

BE-8 adds backend-controlled verification-cache lookup and cache indexing. It is separate from BE-5 DOI metadata caching.

### Endpoints

```text
POST /api/v1/claims/{claim_id}/check-cache
GET  /api/v1/claims/{claim_id}/cache-result
```

### Cache behavior

- Reuse requires the same normalized claim and same normalized DOI.
- Different DOI values are never reused.
- Low-confidence or expired cache rows are not reused.
- `NEEDS_HUMAN_REVIEW` cache entries are returned safely and are not treated as confident verification.
- Semantic cache is prepared as a mockable interface only; real vector search is deferred to BE-9.

### Validation

```bash
python -m compileall app
python scripts/init_db.py
pytest -q
python scripts/validate_uploaded_pdfs_be8.py --reset-db /path/to/paper1.pdf /path/to/paper2.pdf /path/to/paper3.pdf
```

## BE-9 — RAG/ML Integration

BE-9 adds backend-controlled integration with the AI/ML/RAG service while preserving BE4.2, BE-5, BE-6, BE-7, and BE-8 behavior.

### Configuration

```env
RAG_SERVICE_ENABLED=true
RAG_SERVICE_URL=http://localhost:9000
RAG_SERVICE_TIMEOUT_SECONDS=30
RAG_SERVICE_MAX_RETRIES=1
RAG_TOP_K=5
RAG_MIN_SIMILARITY_THRESHOLD=0.60
RAG_MOCK_MODE=true
RAG_REQUEST_VERSION=rag-request-v1
```

### Run flow

```bash
python scripts/init_db.py
uvicorn app.main:app --reload
```

Then run the existing flow up to BE-7 and retrieve evidence:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/claims/{claim_id}/retrieve-evidence \
  -H "Content-Type: application/json" \
  -d '{"evidence_package_id":"evidence_001","top_k":5,"use_mock":true}'

curl http://127.0.0.1:8000/api/v1/claims/{claim_id}/retrieval-results
```

### Validate

```bash
python -m compileall app scripts/validate_uploaded_pdfs_be9.py
python scripts/init_db.py
pytest -q
python scripts/validate_uploaded_pdfs_be9.py --reset-db /path/to/paper1.pdf /path/to/paper2.pdf
```

The current real path is an in-process import through `RagDirectClient`, so a
backend-only environment cannot run it. After installing
`requirements-integrated.txt`, validate the complete backend and RAG unit surface:

```bash
.venv/bin/python scripts/run_integrated_rag_checks.py
```

The command prints `INTEGRATED_VALIDATION_RESULT=PASS`, `FAIL`, or `BLOCKED` and
returns exit code 0, 1, or 2 respectively. Missing RAG dependencies are `BLOCKED`,
never a silent pass. Live API-key calls are not part of this unit/integration
runner. A clean environment may download tiktoken's `cl100k_base` asset during
the first tokenization test; it is cached for later runs.

BE-9 is integration-only. It does not implement RAG/ML internals, embeddings, vector DB, GenAI verification, final support labels, safety scoring, report generation, or frontend UI.

## BE-10 — GenAI Verification Orchestration

BE-10 adds the backend-controlled verification orchestration layer. It coordinates previous backend phases, checks BE-8 cache decisions, retrieves evidence through BE-9, validates GenAI-style verification output, applies basic safety gates, stores `VerificationResult` and `SafetyCheck` records, and exposes pipeline/result APIs.

### Important scope

BE-10 uses mockable/local GenAI verification by default. This validates orchestration, result validation, persistence, and safety fallback behavior without requiring a live Groq call. A real configured Groq client can be added behind the same service boundary later.

BE-10 does not implement BE-11 advanced safety/confidence policy, BE-12 reports/feedback, frontend UI, direct frontend-to-RAG calls, direct frontend-to-GenAI calls, or publisher full-text retrieval.

### New endpoints

```text
POST /api/v1/documents/{document_id}/pipeline-runs
POST /api/v1/documents/{document_id}/run-verification
GET  /api/v1/pipeline-runs/{pipeline_run_id}
GET  /api/v1/pipeline-runs/{pipeline_run_id}/steps
GET  /api/v1/documents/{document_id}/verification-results
GET  /api/v1/verification-results/{result_id}
```

### Run full verification after BE-3 to BE-9 outputs exist

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/{document_id}/pipeline-runs \
  -H "Content-Type: application/json" \
  -d '{"mode":"FULL_VERIFICATION","use_cache":true,"use_rag":true,"use_genai_safety_review":true,"generate_report":false}'

curl http://127.0.0.1:8000/api/v1/pipeline-runs/{pipeline_run_id}
curl http://127.0.0.1:8000/api/v1/pipeline-runs/{pipeline_run_id}/steps
curl http://127.0.0.1:8000/api/v1/documents/{document_id}/verification-results
```

### Validation

```bash
python -m compileall app scripts/validate_uploaded_pdfs_be10.py
python scripts/init_db.py
pytest -q
python scripts/validate_uploaded_pdfs_be10.py --reset-db /path/to/paper1.pdf /path/to/paper2.pdf /path/to/paper3.pdf
```

## BE-11 — Safety and Confidence Rules

BE-11 adds deterministic backend safety and confidence rules on top of BE-10 verification orchestration. The backend now evaluates DOI safety, evidence availability, RAG similarity, GenAI confidence, cache safety, and evidence-used consistency before exposing final results. Safety checks are stored and exposed through result detail APIs and safety summary APIs.

New endpoints:

```text
GET /api/v1/verification-results/{result_id}/safety-checks
GET /api/v1/documents/{document_id}/safety-summary
```

BE-11 intentionally does not implement report generation, feedback analytics, frontend UI, or production hardening.


## BE-12 — Report Generation and Feedback

BE-12 adds backend-generated document summaries, HTML verification reports, feedback storage, mapping-feedback storage, and UAT survey storage.

New endpoints:

```text
GET  /api/v1/documents/{document_id}/summary
POST /api/v1/documents/{document_id}/reports
GET  /api/v1/reports/{report_id}
GET  /api/v1/documents/{document_id}/report
GET  /api/v1/reports/{report_id}/download?format=HTML
POST /api/v1/verification-results/{result_id}/feedback
POST /api/v1/claim-reference-links/{link_id}/feedback
POST /api/v1/uat/surveys
```

HTML report is the MVP format. PDF export is intentionally not implemented in BE-12 and returns `REPORT_EXPORT_NOT_SUPPORTED`.

BE-12 does not rerun verification, does not change final support labels, does not auto-apply feedback as truth, and does not replace human academic review.

Validation:

```bash
python -m compileall app scripts/validate_uploaded_pdfs_be12.py
python scripts/init_db.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
python scripts/validate_uploaded_pdfs_be12.py --reset-db /path/to/paper1.pdf /path/to/paper2.pdf /path/to/paper3.pdf
```

## BE-13 Final Backend Hardening

BE-13 adds final testing, logging, OpenAPI validation, demo mode, and setup hardening. It does not add frontend UI or new AI/RAG algorithms.

### Final validation commands

```bash
python -m compileall app scripts/validate_uploaded_pdfs_be13.py scripts/run_demo_pipeline.py scripts/run_backend_checks.py scripts/validate_openapi.py
python scripts/validate_openapi.py
python scripts/init_db.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
```

### Demo commands

```bash
python scripts/reset_demo_db.py
python scripts/run_demo_pipeline.py
```

### Uploaded PDF validation

```bash
python scripts/validate_uploaded_pdfs_be13.py --reset-db <paper1.pdf> <paper2.pdf> <paper3.pdf>
```

See `docs/BACKEND_SETUP_GUIDE_BE13.md` and `docs/BE13_TESTING_LOGGING_DEMO_HARDENING.md` for complete setup and demo guidance.
