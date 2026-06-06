# verifAI / RefCheck AI Backend

FastAPI backend for the verifAI / RefCheck AI Generative AI course project.

Current implementation status:

- BE-1 — Backend Foundation: implemented
- BE-2 — Database Design: implemented
- BE-3 to BE-13: intentionally deferred

## Backend scope

The backend is the central orchestrator:

```text
Frontend → Backend → AI/ML/RAG → Backend → Frontend
AI/ML/RAG → Backend → External Academic Sources
```

Frontend, RAG, GenAI, and external academic services must not write directly to the database.

## Implemented in BE-1

- FastAPI app
- `/api/v1` router
- health/readiness endpoints
- response/error wrapper
- request ID middleware
- structured logging foundation
- environment configuration
- SQLite local database connection foundation
- document stub endpoints

## Implemented in BE-2

- SQLAlchemy model set for the full backend verification workflow
- 18 database tables
- required enums/status constants
- relationships and indexes
- thin repository/data-access layer
- local/demo database initialization script
- seed/demo data script
- database-backed document stub endpoints
- database/model/repository tests

## Intentionally deferred

The following are not implemented yet:

- BE-3 PDF/text extraction
- BE-4 reference and DOI extraction
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
DATABASE_URL="sqlite:///./data/refcheck_be2.db"
FILE_STORAGE_DIR="./data/uploads"
GROQ_MODEL="meta-llama/llama-4-scout-17b-16e-instruct"
```

Do not commit real secrets such as `GROQ_API_KEY`.

## Initialize the database

```bash
python scripts/init_db.py
```

For demo data:

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

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/health/readiness
```

Submit text as a database-backed stub:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/text \
  -H "Content-Type: application/json" \
  -d '{"title":"Demo Paper","text":"This is BE-2 database-backed stub text."}'
```

Upload PDF as a database-backed stub:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload \
  -F "file=@sample.pdf" \
  -F "document_title=Demo PDF"
```

## Run validation

```bash
python -m compileall app
python -c "from app.main import app; print(app.title, app.version, len(app.openapi()['paths']))"
python scripts/init_db.py
pytest -q
```

## Database design document

See:

```text
docs/BE2_DATABASE_DESIGN.md
```
