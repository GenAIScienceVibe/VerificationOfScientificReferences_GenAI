# BE-1 Integration Note

BE-1 — Backend Foundation has been added into the existing project under `backend/`.

## What was added

- `backend/app/main.py`
- `backend/app/api/v1/*`
- `backend/app/core/*`
- `backend/app/db/*`
- `backend/app/schemas/*`
- `backend/app/services/document_stub_service.py`
- `backend/tests/*`
- `backend/validation/*`
- `backend/.env.example`
- `backend/pytest.ini`
- updated `backend/requirements.txt`
- updated `backend/README.md`

## What was not changed

- Frontend implementation was not changed.
- RAG implementation was not changed.
- No later backend phases were implemented.
- No real AI/ML/RAG calls were added.
- No real DOI/reference/claim extraction was added.

## How to run

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## How to test

```bash
cd backend
pytest -q
```
