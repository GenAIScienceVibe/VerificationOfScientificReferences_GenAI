# verifAI / RefCheck AI Backend — BE-1 Backend Foundation

This package implements **BE-1 — Backend Foundation** only for the verifAI / RefCheck AI Generative AI course project.

The backend is the central orchestration layer in the fixed architecture:

```text
Frontend -> Backend -> AI/ML/RAG -> Backend -> Frontend
AI/ML/RAG -> Backend -> External Academic Sources
```

Frontend teams should call only backend APIs under `/api/v1/*`. Internal RAG, GenAI, and academic metadata integrations are intentionally deferred to later phases.

## Implemented in BE-1

- FastAPI application foundation
- `/api/v1` router prefix
- Swagger/OpenAPI docs
- CORS for local frontend development
- request ID middleware with `X-Request-ID`
- global response wrapper
- global error wrapper
- validation, HTTP, application, and unhandled exception handlers
- structured JSON logging with request ID, method, path, status, and duration
- environment-based configuration through `.env`
- SQLite local database connection foundation with SQLAlchemy
- base declarative model and timestamp mixin for BE-2+
- file storage directory readiness check
- health and readiness endpoints
- BE-1 mock/stub document endpoints for frontend connection
- pytest tests for foundation endpoints and wrappers

## Intentionally deferred to later phases

The following are **not** implemented in BE-1:

- full database schema (**BE-2**)
- PDF/text extraction pipeline (**BE-3**)
- reference and DOI extraction (**BE-4**)
- DOI metadata lookup (**BE-5**)
- claim and citation management (**BE-6**)
- evidence packages (**BE-7**)
- exact/semantic verification cache (**BE-8**)
- RAG/ML retrieval internals (**BE-9**)
- GenAI verification orchestration (**BE-10**)
- safety/confidence scoring (**BE-11**)
- reports and feedback (**BE-12**)
- production authentication and full hardening (**BE-13**)

## Project structure

```text
app/
  main.py
  api/v1/
    router.py
    health.py
    documents.py
  core/
    config.py
    errors.py
    exception_handlers.py
    logging.py
    middleware.py
    responses.py
  db/
    base.py
    session.py
  schemas/
    common.py
    documents.py
    health.py
  services/
    document_stub_service.py
  repositories/
  clients/
tests/
.env.example
requirements.txt
README.md
```

## Setup

Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create local configuration:

```bash
cp .env.example .env
```

For local demo mode, the default SQLite database is enough:

```env
DATABASE_URL="sqlite:///./data/refcheck_be1.db"
FILE_STORAGE_DIR="./data/uploads"
```

Do not add a real `GROQ_API_KEY` to source control.

## Run the backend

```bash
uvicorn app.main:app --reload
```

Open Swagger docs:

```text
http://127.0.0.1:8000/docs
```

Open OpenAPI JSON:

```text
http://127.0.0.1:8000/openapi.json
```

## Core BE-1 endpoints

```text
GET  /api/v1/health
GET  /api/v1/health/readiness
POST /api/v1/documents/upload
POST /api/v1/documents/text
GET  /api/v1/documents/{document_id}
GET  /api/v1/documents/{document_id}/status
```

All responses use this wrapper shape:

```json
{
  "success": true,
  "data": {},
  "message": "Request completed successfully",
  "errors": [],
  "request_id": "req_12345"
}
```

Errors use:

```json
{
  "success": false,
  "data": null,
  "message": "Validation failed",
  "errors": [
    {
      "code": "VALIDATION_ERROR",
      "field": "file",
      "detail": "Field required"
    }
  ],
  "request_id": "req_12345"
}
```

## Example calls

Health:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Readiness:

```bash
curl http://127.0.0.1:8000/api/v1/health/readiness
```

Text submission stub:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/text \
  -H "Content-Type: application/json" \
  -d '{"title":"Demo paper","text":"This is a BE-1 text stub."}'
```

PDF upload stub:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload \
  -F "file=@sample.pdf" \
  -F "document_title=Demo PDF" \
  -F "uploaded_by=demo-user"
```

## Tests and validation

Run:

```bash
python -m compileall app
python -c "from app.main import app; print(app.title, app.version)"
python - <<'PY'
from app.main import app
schema = app.openapi()
print(schema['info']['title'])
print(len(schema['paths']))
PY
pytest -q
```

## BE-1 note

Document endpoints are mock/stub endpoints only. They let frontend teams connect early, but they do not parse PDFs, extract references, verify DOIs, retrieve evidence, run GenAI, or generate reports.
