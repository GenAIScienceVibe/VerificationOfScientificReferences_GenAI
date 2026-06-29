# VerificationOfScientificReferences_GenAI

AI-powered web application for verifying scientific references via DOI matching and semantic claim validation against cited sources.

## Integrated Backend + RAG development setup

The current integration calls the repository-root `rag` package directly from the
FastAPI backend. Use one Python environment containing both dependency sets.

Before changing a local package without Git, make a manual backup from its parent
directory:

```bash
cp -r VerificationOfScientificReferences_GenAI VerificationOfScientificReferences_GenAI_BACKUP
```

From the repository root:

```bash
python -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r requirements-integrated.txt
```

`requirements-integrated.txt` includes both `backend/requirements.txt` and
`rag/requirements.txt`. The backend-only requirements remain available for mock
backend work, but they are not enough for `RagDirectClient`.

Verify import readiness without an API key:

```bash
backend/.venv/bin/python -c "from rag.api import retrieve_evidence, verify_claim; print('rag imports ok')"
PYTHONPATH=backend RAG_MOCK_MODE=false GENAI_MOCK_MODE=true backend/.venv/bin/python -c "from app.services.rag_ml_integration import RagDirectClient; RagDirectClient(); from rag.api import retrieve_evidence; print('real rag import ok')"
```

Imports and unit tests do not require `OPENROUTER_API_KEY`; clients are created
only when live embedding or Door 2 functions execute. Actual real-RAG retrieval
uses OpenRouter embeddings and therefore requires a configured key. Keep
`GENAI_MOCK_MODE=true` for staged Door 1 validation so real Door 2 is not called.

## Integrated validation

From `backend/` run:

```bash
.venv/bin/python scripts/run_integrated_rag_checks.py
```

The runner validates backend compile/import, backend pytest, OpenAPI, backend
checks, the demo pipeline, real RAG imports, and `tests/rag`. It ends with exactly
one aggregate state:

- `PASS` and exit code 0 when every required check passes.
- `FAIL` and exit code 1 when a required command fails.
- `BLOCKED` and exit code 2 when RAG dependencies are unavailable; RAG tests are
  explicitly reported as blocked rather than silently omitted.

The runner does not call embedding or LLM APIs. On a clean machine, tiktoken may
download its declared `cl100k_base` tokenizer asset the first time tokenization
runs; later runs use its local cache. Live real-RAG and real-GenAI modes remain
separate staged validations.
