# Backend Setup Guide — BE-13 Final Demo-Ready Backend

## 1. Prerequisites

- Python 3.11+ recommended
- `pip`
- SQLite for local demo, PostgreSQL optional
- No real Groq/RAG/CrossRef credentials are required for mock demo mode

## 2. Install

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 3. Configure `.env`

For a deterministic local demo:

```env
DEMO_MODE=true
RAG_MOCK_MODE=true
GENAI_MOCK_MODE=true
CACHE_SEMANTIC_ENABLED=false
DATABASE_URL=sqlite:///./data/refcheck_demo.db
FILE_STORAGE_DIR=./data/uploads
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

Do not commit real API keys.

## 4. Initialize database

```bash
python scripts/init_db.py
```

For a clean demo database:

```bash
python scripts/reset_demo_db.py
```

## 5. Run backend

```bash
uvicorn app.main:app --reload
```

Open:

- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/v1/health`
- Readiness: `http://127.0.0.1:8000/api/v1/health/readiness`

## 6. Run tests

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
```

## 7. Run backend checks

```bash
python scripts/run_backend_checks.py
```

## 8. Run demo pipeline

```bash
python scripts/reset_demo_db.py
python scripts/run_demo_pipeline.py
```

## 9. Validate uploaded research PDFs

```bash
python scripts/validate_uploaded_pdfs_be13.py --reset-db \
  /path/to/IRRDOLPUBLISHEDARTICLE.pdf \
  /path/to/Impact_of_Ease_of_Use_Usefulness_Attitude_and_Trus.pdf \
  /path/to/SeminarPaper_20.01..pdf
```

## 10. Troubleshooting

- If external metadata lookup times out, use mock/demo mode and verify that failures are handled safely.
- If Groq is not configured, use `GENAI_MOCK_MODE=true`.
- If RAG service is unavailable, use `RAG_MOCK_MODE=true`.
- If database errors occur, reset the demo DB with `python scripts/reset_demo_db.py`.
- If tests behave inconsistently because of external pytest plugins, use `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
