# BE-3 — Document Upload and Text Processing

## Scope

BE-3 accepts PDF uploads and pasted text submissions, stores document metadata safely, extracts text from text-based PDFs, cleans text, detects broad document sections, persists `Document` and `DocumentSection` records, and exposes document status/section/raw-text endpoints for frontend and developer integration.

BE-3 intentionally does **not** implement reference extraction, DOI extraction, DOI metadata lookup, claim extraction, citation mapping, RAG retrieval, GenAI verification, report generation, feedback logic, or final safety scoring.

## Architecture boundary

```text
Frontend → Backend → AI/ML/RAG → Backend → Frontend
AI/ML/RAG → Backend → External Academic Sources
```

The frontend uploads documents only to backend APIs. BE-3 does not send raw documents to AI/RAG services or external academic sources.

## Configuration

Use `.env`:

```env
DATABASE_URL="sqlite:///./data/refcheck_be3.db"
FILE_STORAGE_DIR="./data/uploads"
MAX_UPLOAD_SIZE_BYTES="10485760"
```

SQLite is used for local/demo runs. PostgreSQL can be configured later by changing `DATABASE_URL`.

## PDF dependency

BE-3 uses PyMuPDF:

```text
PyMuPDF>=1.24,<2.0
```

Only text-based PDF extraction is implemented. OCR for scanned/image-only PDFs is out of scope.

## Endpoints

### POST `/api/v1/documents/upload`

Accepts `multipart/form-data`:

- `file`: PDF file
- `document_title`: optional
- `uploaded_by`: optional

Behavior:

1. Validates file is present.
2. Validates extension/content type.
3. Validates size using `MAX_UPLOAD_SIZE_BYTES`.
4. Stores the file using an internal `document_id.pdf` filename under `FILE_STORAGE_DIR`.
5. Creates a `Document` record.
6. Extracts PDF text using PyMuPDF.
7. Cleans text.
8. Detects broad sections.
9. Stores `DocumentSection` rows.
10. Returns the standard API wrapper.

The public response does **not** expose local filesystem paths.

### POST `/api/v1/documents/text`

Accepts JSON:

```json
{
  "title": "Sample Scientific Text",
  "text": "Abstract\n...\nReferences\n..."
}
```

Behavior:

1. Validates text exists and is not too short.
2. Cleans text.
3. Creates a `Document` row with `upload_type = TEXT`.
4. Detects broad sections.
5. Stores `DocumentSection` rows.
6. Returns `document_id`, status, and section count.

### GET `/api/v1/documents/{document_id}`

Returns metadata only:

- document ID
- filename
- title
- upload type
- status
- pages count
- references count
- claims count
- sections count
- timestamps

BE-3 does not fake reference or claim counts.

### GET `/api/v1/documents/{document_id}/status`

Returns frontend-friendly status:

- `UPLOAD`
- `TEXT_EXTRACTION`
- `SECTION_DETECTION`
- `COMPLETED`
- `FAILED`

### GET `/api/v1/documents/{document_id}/sections`

Returns broad stored sections. By default it returns previews only.

Use this optional developer flag to include full section text:

```text
/api/v1/documents/{document_id}/sections?include_text=true
```

### GET `/api/v1/documents/{document_id}/raw-text`

Developer/debug endpoint returning raw and cleaned text. Do not expose it as a public file download feature.

## Section detection rules

BE-3 uses simple rule-based headings. It detects broad sections such as:

- Title
- Abstract
- Introduction
- Body
- Methods
- Results
- Discussion
- Conclusion
- References

It does not split individual references. That belongs to BE-4.

## Text cleaning rules

The cleaning step:

- normalizes line endings
- removes excessive whitespace
- merges safe PDF line wraps
- preserves paragraph boundaries
- preserves DOI strings
- preserves APA citations like `(Smith, 2023)`
- preserves bracket citations like `[1]`
- preserves section headings

## Error codes added/used in BE-3

- `DOCUMENT_NOT_FOUND`
- `FILE_REQUIRED`
- `INVALID_FILE_TYPE`
- `FILE_TOO_LARGE`
- `PDF_READ_FAILED`
- `TEXT_REQUIRED`
- `TEXT_TOO_SHORT`
- `TEXT_EXTRACTION_FAILED`
- `SECTION_DETECTION_FAILED`
- `FILE_STORAGE_FAILED`
- `DATABASE_UNAVAILABLE`
- `VALIDATION_ERROR`
- `INTERNAL_SERVER_ERROR`

## Run setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/init_db.py
uvicorn app.main:app --reload
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

## Run tests

```bash
python -m compileall app
python scripts/init_db.py
pytest -q
```

## Deferred phases

- BE-4: Reference and DOI extraction
- BE-5: DOI metadata lookup
- BE-6: Claim and citation management
- BE-7: Evidence package builder
- BE-8: Verification cache layer
- BE-9: RAG/ML integration
- BE-10: GenAI verification orchestration
- BE-11: Safety and confidence rules
- BE-12: Report generation and feedback
- BE-13: Testing, logging, and demo hardening
