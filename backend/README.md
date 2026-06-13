# verifAI / RefCheck AI Backend

FastAPI backend for the verifAI / RefCheck AI Generative AI course project.

Current implementation status:

- BE-1 — Backend Foundation: implemented
- BE-2 — Database Design: implemented
- BE-3 — Document Upload and Text Processing: implemented
- BE-4 — Reference and DOI Extraction: implemented
- BE-4.2 — DOI Attachment, Reference Continuation, and Extraction Quality Hardening: implemented
- BE-5 to BE-13: intentionally deferred

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

## Intentionally deferred

The following are not implemented yet:

- BE-5 DOI metadata lookup
- BE-6 claim and citation management logic
- BE-7 evidence package builder logic
- BE-8 verification cache logic
- BE-9 RAG/ML integration
- BE-10 GenAI verification orchestration
- BE-11 safety/confidence rules
- BE-12 report generation and feedback workflows
- BE-13 final testing/logging/demo hardening

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

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
