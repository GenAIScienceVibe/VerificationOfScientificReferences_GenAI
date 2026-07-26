# verifAI — AI-assisted Scientific Citation and Evidence Verification

verifAI is a full-stack Generative AI course project for checking whether scientific claims in a document are supported by their cited sources. The system accepts scientific PDFs or plain text, extracts claims and references, resolves DOI and metadata information, builds evidence packages, retrieves relevant source evidence through a RAG/ML layer, runs GenAI-assisted verification, applies deterministic backend safety rules, and presents transparent verification results to the user.

The project is implemented as a monorepo containing a React/Vite frontend, a FastAPI backend, and an in-process RAG/ML package. The backend is the source of truth: the frontend never calls RAG, GenAI, academic providers, the database, or file storage directly.

---

## 1. Repository Structure

```text
VerificationOfScientificReferences_GenAI/
├── backend/                 # FastAPI backend, database models, orchestration, APIs, scripts, tests
├── frontend/app/            # React + Vite frontend application
├── rag/                     # RAG/ML and GenAI verification adapter package used by backend
├── tests/rag/               # RAG package tests
├── docs/                    # Project and integration documentation
├── qa/                      # QA findings, revalidation reports, and acceptance reports
├── requirements.txt         # Root Python dependency manifest for backend + RAG deployment
├── requirements-integrated.txt
├── .env.example             # Root-level AI provider example variables
└── README.md                # Main project setup and run instructions
```

Detailed component documentation is available in:

```text
backend/README.md            # Backend + RAG adapter setup and API validation
frontend/app/README.md       # Frontend setup and development notes
rag/README.md                # RAG package notes, if maintained
```

---

## 2. Architecture Summary

The system follows a backend-controlled architecture:

```text
User → Frontend → Backend API → Backend Workflow Orchestrator
                         ↓
        Academic Metadata / Full-text Providers
                         ↓
              Internal RAG/ML + GenAI Layer
                         ↓
        Backend Safety & Confidence Policy
                         ↓
       Database / File Storage / Cache / Reports
                         ↓
                    Frontend Results
```

Main architectural principles:

- **Frontend is presentation-only**: upload, dashboard, result viewing, report export, and user feedback.
- **Backend owns orchestration**: document processing, references, DOI lookup, claims, evidence packages, cache, RAG calls, GenAI calls, safety rules, reports, and persistence.
- **RAG/ML is internal**: the backend imports the root-level `rag` package through the adapter layer; no separate public RAG HTTP API is exposed to the frontend.
- **Safety is backend-controlled**: GenAI output is validated and then passed through deterministic safety and confidence rules before final user-facing status is returned.
- **Traceability is preserved**: documents, references, claims, evidence packages, retrieval results, verification results, reports, feedback, and audit details are stored by the backend.

Final support statuses used by the system are:

```text
SUPPORTED
PARTIALLY_SUPPORTED
NOT_SUPPORTED
INSUFFICIENT_EVIDENCE
NEEDS_HUMAN_REVIEW
```

---

## 3. Prerequisites

Recommended local environment:

- Python **3.12**
- Node.js **18.x** or Higher
- npm
- Git
- Optional:  Render/Railway CLI for deployment workflows

The repository includes a `.python-version` file to guide Python version selection.

---

## 4. Backend + RAG/ML Setup

Run backend setup from the **repository root**, not from inside `backend/`, because the backend imports the root-level `rag/` package.

### 4.1 Create Python environment

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r requirements.txt
```

`requirements.txt` is the deployment-friendly combined dependency manifest for both the backend and the RAG/ML layer.

### 4.2 Configure backend environment

```bash
cp backend/.env.example backend/.env
```

For local deterministic development, keep the following defaults or set them explicitly in `backend/.env`:

```env
RAG_SERVICE_ENABLED=true
RAG_MOCK_MODE=true
GENAI_MOCK_MODE=true
METADATA_LOOKUP_ENABLED=false
METADATA_MOCK_MODE=true
DEMO_MODE=true
ENABLE_RAW_TEXT_DEBUG_ENDPOINT=false
```

This mode runs the backend pipeline without requiring live external metadata, embedding, or LLM API calls.

For staged real-RAG validation with mock GenAI:

```env
RAG_MOCK_MODE=false
GENAI_MOCK_MODE=true
METADATA_LOOKUP_ENABLED=false
```

For live external RAG/GenAI modes, configure the required provider variables such as:

```env
OPENROUTER_API_KEY=<your_openrouter_key>
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
GROQ_API_KEY=<your_groq_key_if_used>
```

Live metadata/full-text retrieval may also require:

```env
CROSSREF_MAILTO=<contact_email>
UNPAYWALL_EMAIL=<contact_email>
CORE_API_KEY=<optional_core_key>
```

Do not commit real `.env` files or API keys.

### 4.3 Initialize local database

```bash
cd backend
.venv/bin/python scripts/init_db.py
```

Optional demo seed/reset commands:

```bash
.venv/bin/python scripts/seed_demo_data.py
.venv/bin/python scripts/reset_demo_db.py
```

### 4.4 Run backend API

From `backend/`:

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health checks:

```text
http://127.0.0.1:8000/api/v1/health
http://127.0.0.1:8000/api/v1/health/readiness
```

OpenAPI documentation, when enabled by FastAPI defaults:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/openapi.json
```

---

## 5. Frontend Setup

The frontend lives under `frontend/app`.

```bash
cd frontend/app
npm ci
```

Create a local frontend environment file:

```bash
cat > .env.local <<'ENV'
VITE_API_BASE_URL=http://127.0.0.1:8000
ENV
```

Start the development server:

```bash
npm run dev
```

The Vite development URL is usually:

```text
http://127.0.0.1:5173
```

Make sure the backend `CORS_ORIGINS` includes the frontend development URL.

Build and preview production frontend locally:

```bash
npm run build
npm run preview -- --host 0.0.0.0 --port 4173
```

---

## 6. Typical Local Development Flow

Start backend:

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Start frontend in another terminal:

```bash
cd frontend/app
npm run dev
```

Then use the frontend to:

1. Upload a PDF or plain text document.
2. Start the verification pipeline.
3. Review extracted references, claims, and verification results.
4. Inspect evidence, confidence, and review status.
5. Export or view generated reports where available.

---

## 7. Backend Validation and QA Commands

From `backend/`:

```bash
.venv/bin/python -m compileall app scripts
.venv/bin/pytest -q
.venv/bin/python scripts/validate_openapi.py
.venv/bin/python scripts/run_backend_checks.py
.venv/bin/python scripts/run_demo_pipeline.py
.venv/bin/python scripts/run_integrated_rag_checks.py
```

From the repository root, run RAG tests:

```bash
backend/.venv/bin/python -m pytest tests/rag -q --tb=short
```

Run full-text pipeline tests:

```bash
cd backend
.venv/bin/pytest -q tests/test_full_text_pipeline.py --tb=short
```

Run release packaging tests:

```bash
cd backend
.venv/bin/pytest -q tests/unit/test_release_packaging.py --tb=short
```

---

## 8. Uploaded PDF Validation Modes

The backend contains validation tooling for real uploaded PDFs and staged RAG/GenAI modes.

Mock RAG + Mock GenAI validation:

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

Real RAG adapter + Mock GenAI validation:

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

Private PDF fixtures are local-only and must not be committed or included in release packages.

---

## 9. Release Packaging and Privacy Checks

The project includes a release package builder to avoid shipping local/private artifacts.

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

The release package should exclude:

- `.git/`, `.idea/`, `.venv/`, `node_modules/`
- `.env` files and secrets
- uploaded/private PDFs
- SQLite/runtime databases
- cache folders and `*.pyc`
- local backup folders and previous release ZIPs

---

## 10. Deployment Notes

### 10.1 Backend deployment

For Railway or similar platforms, deploy the backend service from the **repository root** so that the backend can import the root-level `rag/` package.

Recommended backend service configuration:

```text
Root directory: /
Build command: pip install -r requirements.txt
Start command: cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
Healthcheck path: /api/v1/health
```

Suggested safe demo environment:

```env
ENVIRONMENT=production
API_PREFIX=/api/v1
DATABASE_URL=sqlite:///./data/refcheck_railway.db
FILE_STORAGE_DIR=./data/uploads
CORS_ORIGINS=https://<frontend-domain>
RAG_SERVICE_ENABLED=true
RAG_MOCK_MODE=true
GENAI_MOCK_MODE=true
METADATA_LOOKUP_ENABLED=false
METADATA_MOCK_MODE=true
DEMO_MODE=true
ENABLE_RAW_TEXT_DEBUG_ENDPOINT=false
```

For persistent SQLite and uploads on Railway, attach a volume to:

```text
/app/backend/data
```

For production-grade persistence, a managed database should be considered.

### 10.2 Frontend deployment

Deploy the frontend as a separate service from:

```text
frontend/app
```

Recommended frontend service configuration:

```text
Root directory: frontend/app
Build command: npm run build
Start command: npm run preview -- --host 0.0.0.0 --port $PORT
```

Frontend environment variable:

```env
VITE_API_BASE_URL=https://<backend-domain>
```

After changing `VITE_API_BASE_URL`, rebuild/redeploy the frontend because Vite environment variables are injected at build time.

---

## 11. Troubleshooting

### Backend cannot import `rag`

Run backend setup from the repository root and install root dependencies:

```bash
backend/.venv/bin/python -m pip install -r requirements.txt
```

Do not deploy the backend with root directory set to `backend/` if the platform excludes the root-level `rag/` package.

### Railway cannot find nested requirements files

Use the self-contained root `requirements.txt`. Avoid deployment-only manifests that depend on nested `-r` includes if the build system copies only the root manifest during dependency installation.

### Frontend calls localhost after deployment

Set:

```env
VITE_API_BASE_URL=https://<backend-domain>
```

Then redeploy the frontend.

### CORS error in browser

Add the deployed frontend domain to backend `CORS_ORIGINS` and redeploy the backend.

### Live RAG or GenAI fails

Check that the relevant API keys and provider base URLs are configured. For demo/offline validation, keep:

```env
RAG_MOCK_MODE=true
GENAI_MOCK_MODE=true
METADATA_LOOKUP_ENABLED=false
```

---

## 12. Security and Data Handling

- Do not commit `.env` files or real API keys.
- Do not commit uploaded PDFs, private research PDFs, or runtime databases.
- Keep private validation PDFs in ignored local-only folders.
- Use the release packaging script before sharing the repository externally.
- Backend safety rules remain responsible for final user-facing support decisions.
- RAG and GenAI components are internal support layers, not standalone decision makers.

---

## 13. Useful Commands Summary

```bash
# Backend + RAG setup
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r requirements.txt
cp backend/.env.example backend/.env
cd backend && .venv/bin/python scripts/init_db.py

# Run backend
cd backend
.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run frontend
cd frontend/app
npm ci
npm run dev

# Backend validation
cd backend
.venv/bin/pytest -q
.venv/bin/python scripts/run_integrated_rag_checks.py

# RAG tests
backend/.venv/bin/python -m pytest tests/rag -q --tb=short

# Release package
backend/.venv/bin/python backend/scripts/build_release_package.py --root . --output /tmp/verifai_release.zip
```

---

## 14. Project Status

The submitted project includes:

- React/Vite frontend MVP
- FastAPI backend with document, reference, claim, evidence, verification, report, feedback, and health APIs
- In-process RAG/ML adapter package
- Mock and staged real-RAG validation modes
- Backend safety and confidence policy
- UAT/demo support
- Release packaging and privacy safeguards

For frontend-specific implementation details and instructions, see `frontend/README.md`.

For backend-specific implementation details and deeper API validation instructions, see `backend/README.md`.
