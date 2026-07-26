# verifAI / RefCheck AI Backend

Backend service for **verifAI**, an AI-assisted scientific citation and evidence verification system. The backend is the source of truth for document processing, DOI/reference handling, claim-citation management, evidence packaging, RAG retrieval orchestration, GenAI verification orchestration, deterministic safety rules, report generation, and feedback capture.

The current backend is integrated with the repository-level `rag/` package through a direct Python adapter (`RagDirectClient`). There is no separate RAG HTTP service required for the standard integrated setup.

---

## 1. What the backend does

The backend exposes a FastAPI API under `/api/v1` and coordinates the full verification workflow:

1. Upload or submit a scientific document.
2. Extract text, sections, references, DOIs, citations, and claims.
3. Resolve DOI metadata and retrieve available source evidence.
4. Build evidence packages for claim-reference pairs.
5. Check verification cache for safe reuse.
6. Call the internal RAG/ML layer for evidence retrieval.
7. Run GenAI-assisted verification in mock or live mode.
8. Apply backend safety and confidence rules.
9. Store verification results, reports, feedback, and audit information.
10. Return structured responses to the frontend.

Important architectural rule:

> The frontend must not call RAG, GenAI, external academic providers, storage, or the database directly. All critical verification logic is mediated by the backend.

---

## 2. Repository context

This README is for the backend, but the backend depends on the root-level `rag/` package when real RAG mode is enabled.

Relevant directories:

```text
backend/
  app/
    api/v1/              FastAPI route modules
    core/                configuration, errors, middleware, responses
    db/                  database session and initialization
    models/              SQLAlchemy workflow models and enums
    repositories/        persistence access layer
    schemas/             API schemas
    services/            backend business workflow services
  scripts/               setup, validation, demo, and packaging scripts
  tests/                 backend regression and integration tests
  .env.example           local backend configuration template
  requirements.txt       backend-only dependency manifest

rag/
  api.py                 RAG subgroup integration entry point
  ingestion/             text cleaning and chunking
  retrieval/             embeddings, BM25, FAISS/vector search, hybrid retrieval
  prompts/               classifier and verifier prompt modules
  verification/          GenAI output validation models
  requirements.txt       RAG dependency manifest

requirements.txt         root combined dependency manifest for backend + RAG
requirements-integrated.txt legacy combined manifest
```

Use the **root-level dependency manifest** for integrated backend + RAG work. Backend-only dependencies are not enough when `RagDirectClient` is used.

---

## 3. Prerequisites

Recommended local environment:

- Python 3.12
- pip
- Git
- Linux/macOS shell or equivalent Windows terminal

Optional external keys for live modes:

- `OPENROUTER_API_KEY` for live RAG embeddings and OpenRouter-backed classification/fallbacks
- `GROQ_API_KEY` for live GenAI verification through Groq
- `UNPAYWALL_EMAIL` for Unpaywall metadata/full-text lookup
- `CORE_API_KEY` for CORE full-text/title-search fallback
- Optional provider keys such as Semantic Scholar, IEEE Xplore, and Google Books where configured

For normal local development and demo validation, external keys are **not required** if mock modes are enabled.

---

## 4. Quick start: local backend with integrated RAG dependencies

Run the following commands from the repository root.

```bash
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create the local environment file:

```bash
cp backend/.env.example backend/.env
```

Initialize the database:

```bash
cd backend
python scripts/init_db.py
```

Run the backend:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open the API documentation:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/redoc
```

Health checks:

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/health/readiness
```

---

## 5. Recommended local `.env` for deterministic demo mode

For local development without external API keys, keep the backend in deterministic/offline mode:

```env
APP_NAME="verifAI / RefCheck AI Backend"
APP_VERSION="1.0.0"
ENVIRONMENT="local"
API_PREFIX="/api/v1"
LOG_LEVEL="INFO"

DATABASE_URL="sqlite:///./data/refcheck_local.db"
FILE_STORAGE_DIR="./data/uploads"
MAX_UPLOAD_SIZE_BYTES="26214400"
CORS_ORIGINS="http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173"

DEMO_MODE=true
ENABLE_RAW_TEXT_DEBUG_ENDPOINT=false

METADATA_LOOKUP_ENABLED=false
METADATA_MOCK_MODE=true

RAG_SERVICE_ENABLED=true
RAG_MOCK_MODE=true
GENAI_MOCK_MODE=true
GENAI_VERIFICATION_MODE=mock

CACHE_ENABLED=true
CACHE_EXACT_ENABLED=true
CACHE_SEMANTIC_ENABLED=false
```

This mode is best for first-time setup, frontend integration, demos, and CI-style validation because it avoids live provider calls.

---

## 6. Enabling real RAG and live GenAI modes

### 6.1 Mock RAG + Mock GenAI

Default safe mode for local demos:

```env
RAG_MOCK_MODE=true
GENAI_MOCK_MODE=true
METADATA_LOOKUP_ENABLED=false
METADATA_MOCK_MODE=true
```

### 6.2 Real RAG adapter + Mock GenAI

This mode exercises the real backend-to-RAG adapter path while keeping GenAI deterministic:

```env
RAG_SERVICE_ENABLED=true
RAG_MOCK_MODE=false
GENAI_MOCK_MODE=true
METADATA_LOOKUP_ENABLED=false
```

For fully live RAG embeddings, also configure:

```env
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### 6.3 Real GenAI verification

Live GenAI verification requires configured provider keys:

```env
GENAI_MOCK_MODE=false
GENAI_VERIFICATION_MODE=live
GROQ_API_KEY=your_groq_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

Groq is used as the primary live verification provider. OpenRouter is used by the RAG embedding path and as a fallback for some RAG/GenAI routines.

### 6.4 Live academic metadata/full-text lookup

```env
METADATA_LOOKUP_ENABLED=true
METADATA_MOCK_MODE=false
CROSSREF_MAILTO=your_email@example.com
UNPAYWALL_EMAIL=your_email@example.com
CORE_API_KEY=your_core_api_key_here
```

Keep `METADATA_LOOKUP_ENABLED=false` for deterministic offline validation.

---

## 7. Common API workflow

### 7.1 Upload a PDF

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload \
  -F "file=@sample.pdf" \
  -F "document_title=Demo Scientific Paper"
```

### 7.2 Submit plain text

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/text \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Demo Scientific Text",
    "text": "Demo Paper\n\nAbstract\nGenerative AI tools can support writing (Smith, 2023).\n\nReferences\nSmith, J. (2023). Demo paper. doi:10.1234/demo"
  }'
```

### 7.3 Start the full verification pipeline asynchronously

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/{document_id}/pipeline-runs \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "FULL_VERIFICATION",
    "use_cache": true,
    "use_rag": true,
    "use_genai_safety_review": true,
    "generate_report": true
  }'
```

The frontend can poll document status:

```bash
curl http://127.0.0.1:8000/api/v1/documents/{document_id}/status
```

### 7.4 Run verification synchronously

Useful for local testing:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/{document_id}/run-verification \
  -H "Content-Type: application/json" \
  -d '{"generate_report": true}'
```

### 7.5 Retrieve results and report

```bash
curl http://127.0.0.1:8000/api/v1/documents/{document_id}/verification-results
curl http://127.0.0.1:8000/api/v1/documents/{document_id}/summary
curl http://127.0.0.1:8000/api/v1/documents/{document_id}/report
```

---

## 8. Main API groups

| Area | Endpoint examples |
|---|---|
| Health | `GET /api/v1/health`, `GET /api/v1/health/readiness` |
| Documents | `POST /api/v1/documents/upload`, `POST /api/v1/documents/text`, `GET /api/v1/documents/{document_id}` |
| References and DOI metadata | `POST /api/v1/documents/{document_id}/extract-references`, `POST /api/v1/documents/{document_id}/verify-dois`, `POST /api/v1/references/{reference_id}/upload-source-pdf` |
| Claims and citations | `POST /api/v1/documents/{document_id}/extract-claims`, `GET /api/v1/documents/{document_id}/claims`, `GET /api/v1/documents/{document_id}/claim-reference-links` |
| Evidence packages | `POST /api/v1/documents/{document_id}/prepare-evidence`, `GET /api/v1/documents/{document_id}/evidence-packages` |
| Cache | `POST /api/v1/claims/{claim_id}/check-cache`, `GET /api/v1/claims/{claim_id}/cache-result` |
| RAG retrieval | `POST /api/v1/claims/{claim_id}/retrieve-evidence`, `GET /api/v1/claims/{claim_id}/retrieval-results` |
| Verification orchestration | `POST /api/v1/documents/{document_id}/pipeline-runs`, `POST /api/v1/documents/{document_id}/run-verification` |
| Reports and feedback | `POST /api/v1/documents/{document_id}/reports`, `GET /api/v1/reports/{report_id}/download`, `POST /api/v1/verification-results/{result_id}/feedback` |

All application responses use the backend standard success/error wrapper.

---

## 9. Final support statuses

The backend only exposes the following final support statuses:

```text
SUPPORTED
PARTIALLY_SUPPORTED
NOT_SUPPORTED
INSUFFICIENT_EVIDENCE
NEEDS_HUMAN_REVIEW
```

The RAG retrieval layer must not return final support labels. Final support decisions are made by backend verification orchestration and safety/confidence rules.

---

## 10. Validation and testing

### 10.1 Backend test suite

From `backend/`:

```bash
.venv/bin/python -m compileall app scripts
.venv/bin/pytest -q
.venv/bin/python scripts/validate_openapi.py
.venv/bin/python scripts/run_backend_checks.py
.venv/bin/python scripts/run_demo_pipeline.py
```

### 10.2 Integrated Backend + RAG validation

From `backend/`:

```bash
.venv/bin/python scripts/run_integrated_rag_checks.py
```

This validates backend compile/import, backend tests, OpenAPI, backend checks, demo pipeline, RAG import readiness, and `tests/rag`.

### 10.3 RAG test suite

From the repository root:

```bash
backend/.venv/bin/python -m pytest tests/rag -q --tb=short
```

### 10.4 Uploaded PDF validation

Mock RAG + Mock GenAI mode:

```bash
cd backend
.venv/bin/python scripts/validate_uploaded_pdfs_be13.py \
  --mock-rag \
  --mock-genai \
  --metadata-disabled \
  --pdf-dir tests/fixtures/private_pdfs \
  --reset-db \
  --report-output /tmp/verifai_mock_validation.md
```

Real RAG adapter + Mock GenAI mode:

```bash
cd backend
.venv/bin/python scripts/validate_uploaded_pdfs_be13.py \
  --real-rag \
  --mock-genai \
  --metadata-disabled \
  --pdf-dir tests/fixtures/private_pdfs \
  --reset-db \
  --report-output /tmp/verifai_real_rag_mock_genai_validation.md
```

If local private PDFs are not present, the validator should report the run as blocked rather than silently passing.

---

## 11. Database and file storage

By default, the backend uses SQLite and local file storage:

```env
DATABASE_URL="sqlite:///./data/refcheck_local.db"
FILE_STORAGE_DIR="./data/uploads"
```

The database tables are initialized automatically at application startup. You can also initialize them manually:

```bash
cd backend
python scripts/init_db.py
```

For production-style deployments, use a persistent volume for SQLite and uploads, or migrate the database configuration to a managed database service after adding the required database driver and migration strategy.

Do not commit runtime databases, uploaded PDFs, `.env` files, virtual environments, cache folders, or private research papers.

---

## 12. Railway deployment notes

For Railway backend deployment from the monorepo, use the repository root as the service root because the backend imports the root-level `rag/` package.

Recommended backend service settings:

```text
Root directory: /
Build command: pip install -r requirements.txt
Start command: cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health check path: /api/v1/health
```

Recommended environment for a safe demo deployment:

```env
ENVIRONMENT=production
API_PREFIX=/api/v1
DATABASE_URL=sqlite:///./data/refcheck_railway.db
FILE_STORAGE_DIR=./data/uploads
CORS_ORIGINS=https://your-frontend-domain.example
DEMO_MODE=true
METADATA_LOOKUP_ENABLED=false
METADATA_MOCK_MODE=true
RAG_SERVICE_ENABLED=true
RAG_MOCK_MODE=true
GENAI_MOCK_MODE=true
CACHE_ENABLED=true
CACHE_EXACT_ENABLED=true
CACHE_SEMANTIC_ENABLED=false
ENABLE_RAW_TEXT_DEBUG_ENDPOINT=false
```

If SQLite and uploaded files must survive redeploys, mount a Railway volume to the backend runtime data directory, for example `/app/backend/data`.

---

## 13. Release packaging and privacy check

A release package should exclude private PDFs, uploaded files, runtime databases, `.env` files, caches, virtual environments, IDE files, and Git metadata.

From the repository root:

```bash
backend/.venv/bin/python backend/scripts/build_release_package.py \
  --scan-only \
  --root . \
  --output /tmp/verifai_release.zip

backend/.venv/bin/python backend/scripts/build_release_package.py \
  --root . \
  --output /tmp/verifai_release.zip
```

A clean package should contain source code, documentation, tests, scripts, and QA reports, but no private/runtime artifacts.

---

## 14. Troubleshooting

### `ModuleNotFoundError: No module named 'rag'`

Install dependencies from the repository root and use the combined root `requirements.txt`:

```bash
python -m pip install -r requirements.txt
```

The real adapter inserts the project root into `sys.path`, but the root-level `rag/` package must still exist in the deployed/runtime package.

### `OPENROUTER_API_KEY is not set`

Either keep the backend in mock RAG mode:

```env
RAG_MOCK_MODE=true
GENAI_MOCK_MODE=true
```

or configure live RAG credentials:

```env
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### `GROQ_API_KEY is not set`

Either keep GenAI verification in mock mode:

```env
GENAI_MOCK_MODE=true
GENAI_VERIFICATION_MODE=mock
```

or configure:

```env
GROQ_API_KEY=your_groq_key_here
```

### CORS errors from the frontend

Add the frontend domain to `CORS_ORIGINS`:

```env
CORS_ORIGINS=http://localhost:5173,https://your-frontend-domain.example
```

### Railway cannot find dependency files

Use a self-contained root `requirements.txt` for Railway. Avoid a root `requirements.txt` that only references another file with `-r requirements-integrated.txt`, because some build layers copy only the primary manifest before installation.

---

## 15. Additional documentation

See the phase documentation under `backend/docs/` for deeper implementation notes:

```text
BE2_DATABASE_DESIGN.md
BE3_DOCUMENT_UPLOAD_AND_TEXT_PROCESSING.md
BE4_REFERENCE_AND_DOI_EXTRACTION.md
BE4_2_DOI_ATTACHMENT_AND_EXTRACTION_QUALITY.md
BE5_DOI_METADATA_LOOKUP.md
BE6_CLAIM_AND_CITATION_MANAGEMENT.md
BE7_EVIDENCE_PACKAGE_BUILDER.md
BE8_VERIFICATION_CACHE_LAYER.md
BE9_RAG_ML_INTEGRATION.md
BE10_GENAI_VERIFICATION_ORCHESTRATION.md
BE11_SAFETY_AND_CONFIDENCE_RULES.md
BE12_REPORT_GENERATION_AND_FEEDBACK.md
BE13_TESTING_LOGGING_DEMO_HARDENING.md
```

