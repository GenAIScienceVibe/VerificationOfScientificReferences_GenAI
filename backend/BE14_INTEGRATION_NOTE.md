# BE-14 Integration Note — Full-Text Evidence Pipeline

BE-14 is integrated on top of the BE-13 baseline and the merged RAG hybrid retrieval pipeline (`rag_dev_zac_hybrid`). It does not change the RAG internals, the frontend, or any existing database schema. It extends the metadata lookup chain to retrieve full paper text wherever possible, and adds a manual fallback for paywalled papers.

---

## Preserved baseline

- BE4.2 DOI Attachment + Reference Quality
- BE-5 DOI Metadata Lookup
- BE-6 Claim and Citation Management
- BE-7 Evidence Package Builder
- BE-8 Verification Cache Layer
- BE-9 RAG/ML Integration
- BE-10 GenAI Verification Orchestration
- BE-11 Safety Confidence Rules
- BE-12 Report Generation + Feedback
- BE-13 Testing, Logging, Demo Hardening
- RAG hybrid pipeline (FAISS + BM25 + RRF + FlashRank) from `rag_dev_zac_hybrid`
- RAG integration defect fixes (SCRUM-262/263/264)

---

## Main additions

### Unpaywall integration
- After the standard CrossRef → OpenAlex → SemanticScholar metadata lookup chain, the system now queries the **Unpaywall API** (`https://api.unpaywall.org/v2/{doi}?email={email}`) to find a legal open-access PDF URL.
- If a PDF URL is found, the PDF is streamed via `httpx` and text is extracted using **PyMuPDF** (`pymupdf`).
- Extracted text (up to `FULLTEXT_MAX_CHARS`, default 150,000 characters) is stored in `SourceMetadata.raw_metadata_json["full_text"]`.
- Evidence packages built after this step show `evidence_availability: FULL_TEXT_AVAILABLE` instead of `ABSTRACT_AVAILABLE` or `METADATA_ONLY`, allowing the RAG pipeline to retrieve from the full paper body.
- Requires `UNPAYWALL_EMAIL` in `.env` (Unpaywall's terms of service require a contact email).

### arXiv DOI support
- CrossRef does not index arXiv preprints. DOIs in the form `10.48550/arXiv.XXXX.XXXXX` previously failed the entire lookup chain.
- Added `_ARXIV_DOI_RE` pattern detection in `doi_metadata_lookup.py`.
- For arXiv DOIs: metadata is fetched from **SemanticScholar** using its `arXiv:{id}` paper identifier format (new method `SemanticScholarClient.lookup_by_arxiv_id()`).
- Full text is always fetched from `https://arxiv.org/pdf/{arxiv_id}` — arXiv PDFs are always publicly accessible.
- arXiv PDF URL takes priority over Unpaywall in the full-text fallback chain.

### User PDF upload endpoint
New endpoint: `POST /api/v1/references/{reference_id}/upload-source-pdf`

For papers that are paywalled and cannot be reached automatically (e.g. Elsevier journals where Unpaywall returns no PDF URL), a user can upload the PDF themselves.

- Accepts a `.pdf` file upload (max size: `FULLTEXT_MAX_BYTES`, default 15 MB).
- Extracts text with PyMuPDF and stores it in `SourceMetadata` under `raw_metadata_json["full_text"]` with source tag `user_upload:{filename}`.
- Preserves all existing metadata fields (title, authors, DOI, abstract, etc.) — only `full_text` is added/overwritten.
- Response includes:
  - `chars_extracted` — how many characters were extracted
  - `full_text_preview` — first 300 characters of the extracted text
  - `affected_claims` — list of claims in the document that cite this reference, each with `claim_id`, `claim_text`, and `citation_raw`
  - `next_step` — instruction to run `POST /documents/{document_id}/prepare-evidence` to rebuild evidence packages

### `force_refresh` on verify-dois
- Added `force_refresh: bool` query parameter to `POST /documents/{document_id}/verify-dois`.
- When `true`, re-runs the full lookup chain (CrossRef → OpenAlex → SemanticScholar → Unpaywall → PDF extraction) even for DOIs that already have cached metadata.
- Necessary for documents processed before Unpaywall was integrated.

### Config and environment fixes
- `load_dotenv()` in `app/core/config.py` now uses an absolute path derived from `__file__`, so `UNPAYWALL_EMAIL` and other `.env` variables are always loaded correctly regardless of the working directory the server is started from.
- `FULLTEXT_MAX_CHARS` default increased from 50,000 to 150,000 characters.
- `.env.example` updated with all new keys: `UNPAYWALL_EMAIL`, `UNPAYWALL_BASE_URL`, `FULLTEXT_MAX_BYTES`, `FULLTEXT_MAX_CHARS`, `SEMANTIC_SCHOLAR_BASE_URL`.

---

## New and modified endpoints

| Method | Path | Status | What changed |
|--------|------|--------|--------------|
| `POST` | `/api/v1/references/{reference_id}/upload-source-pdf` | **New** | Accepts a PDF file upload, extracts full text, stores it in SourceMetadata |
| `POST` | `/api/v1/documents/{document_id}/verify-dois` | Modified | Added optional `force_refresh` query parameter |

All other API endpoints existed before BE-14 and were not modified.

---

## Files changed

| File | Change |
|------|--------|
| `app/core/config.py` | Absolute `load_dotenv()` path; `FULLTEXT_MAX_CHARS` default 150k; `FULLTEXT_MAX_BYTES` field |
| `app/clients/metadata_clients.py` | `SemanticScholarClient.lookup_by_arxiv_id()` method |
| `app/services/doi_metadata_lookup.py` | `_ARXIV_DOI_RE`, `_arxiv_pdf_url()`, `_extract_fulltext_from_url()`, `_extract_fulltext_from_bytes()`, arXiv + Unpaywall fallback chain in `_verify_reference()`, `inject_fulltext_from_uploaded_pdf()` service method |
| `app/api/v1/documents.py` | `force_refresh` query param on `verify-dois` |
| `app/api/v1/references.py` | New `upload_source_pdf` endpoint |
| `.env.example` | New config keys |

---

## New dependencies

| Package | Purpose |
|---------|---------|
| `pymupdf` | PDF text extraction (streaming from URL and from uploaded bytes) |
| `httpx` | Async-compatible HTTP client used for streaming PDF downloads |

Both must be present in the venv. Install with `pip install pymupdf httpx`.

---

## Evidence availability hierarchy (unchanged, now more reachable)

```
FULL_TEXT_AVAILABLE   ← Unpaywall OA PDF, arXiv PDF, or user upload  ✅ best
ABSTRACT_AVAILABLE    ← OpenAlex / SemanticScholar abstract only
METADATA_ONLY         ← CrossRef title/authors/year, no text
SOURCE_UNAVAILABLE    ← DOI did not resolve at all
```

Only `FULL_TEXT_AVAILABLE` allows the RAG pipeline to retrieve from the paper body and produce a clean `SUPPORTED` or `NOT_SUPPORTED` verdict. The other levels cap the LLM confidence score via the BE-11 safety policy.

---

## Known limitations

- **Elsevier Gold OA**: Unpaywall may report `is_oa: true` but return no `url_for_pdf`. Elsevier requires a separate Text and Data Mining (TDM) API key for programmatic PDF access. In this case the system falls back to abstract-only, and the user can upload the PDF manually via the new endpoint.
- **CORE API**: Considered for broader OA coverage but not implemented (rate limit: 1,000 req/day).
- **Semantic Cache (BE-8)**: `SemanticCacheClient` exists as a class but performs no real embedding-based similarity lookup — it is a stub. The verification cache uses exact claim-ID matching instead. This is sufficient for demo and correctness; a real vector-based semantic cache would be a future enhancement.

---

## Title-based DOI lookup fallback

Papers in management, law, and humanities journals often omit DOIs from their reference lists. Previously these references immediately received `doi_status: MISSING` and all claims citing them returned `NEEDS_HUMAN_REVIEW`.

A title-based fallback is now integrated into `_verify_reference()` in `doi_metadata_lookup.py`. When a reference has no extractable DOI but does have an extracted title, the system queries **Semantic Scholar's paper search API** (`/graph/v1/paper/search`) before marking the reference as missing.

### How it works

1. `SemanticScholarClient.search_by_title(title, authors, year)` sends the extracted title to SS search.
2. The top result is evaluated against three false-match guards (all must pass):
   - **Title similarity ≥ 0.95** — measured as `max(SequenceMatcher ratio, word-coverage ratio)`. The word-coverage component (fraction of shorter title's words that appear in the longer) handles the common case where the extracted title lacks a subtitle but all its words are in the SS title.
   - **Year mismatch check** — if both reference and SS result have a year, they must agree within 1 year.
   - **Author overlap check** — if both sides have authors, at least one last name must match.
3. If all guards pass and SS returns a DOI, the discovered DOI is set on `reference.extracted_doi` and the normal CrossRef → OpenAlex → SemanticScholar → Unpaywall lookup chain continues with it.
4. If no confident match is found, the reference is still marked `MISSING` as before.

### Practical effect

A Strategic Management Journal paper with 31/32 references that have no DOIs would previously result in all those claims getting `NEEDS_HUMAN_REVIEW`. With the title fallback, SS can resolve most of those references to DOIs, enabling full RAG verification.

### Files changed

| File | Change |
|------|--------|
| `app/clients/metadata_clients.py` | `import difflib`; `_normalize_title()`, `_title_similarity()`, `_authors_overlap()` helpers; `SemanticScholarClient.search_by_title()` method |
| `app/services/doi_metadata_lookup.py` | `_verify_reference()`: title-search block before the MISSING early-return |

---

## Post-merge integration fixes (integration/backend-rag-merge)

After merging `rag_dev_zac_hybrid` into the backend, the following additional fixes and changes were applied to make the full pipeline operational end-to-end.

### Real pipeline activation

`GENAI_MOCK_MODE` and `RAG_MOCK_MODE` both default to `true` in `config.py` (safe default from early development). Two things were needed to deactivate mock mode:

1. `.env` must set `GENAI_MOCK_MODE=false` and `RAG_MOCK_MODE=false`
2. `verification_orchestrator.py` line ~371 had `use_mock=True` **hardcoded** — changed to `use_mock=None` so it reads from settings

### Direct Python integration (no HTTP)

`rag/api.py` exposes two plain Python functions (`retrieve_evidence`, `verify_claim`). The backend does not call them over HTTP — it imports them directly. Two new client classes were added:

| Class | File | What it does |
|---|---|---|
| `RagDirectClient` | `app/services/rag_ml_integration.py` | Calls `rag.api.retrieve_evidence()` directly via Python import |
| `RealGenAiVerificationClient` | `app/services/genai_verification.py` | Calls `rag.api.verify_claim()` directly via Python import |

Both classes add the project root to `sys.path` so `rag/` is importable from the backend context.

`GenAiVerificationService.__init__()` now checks `settings.genai_mock_mode` and instantiates `RealGenAiVerificationClient` when mock mode is off.

### Bug fixes

| File | Bug | Fix |
|---|---|---|
| `app/services/doi_metadata_lookup.py` | `Citation` attribute `citation_text` does not exist | Changed to `raw_citation` |
| `app/services/doi_metadata_lookup.py` | `"filename"` used as key in `logger.info(extra={...})` — reserved `LogRecord` field | Renamed to `"upload_filename"` |
| `rag/api.py` | Embedding cache keyed by `doi` — papers with missing DOI (`doi=""`) all collide in the same cache slot, returning wrong chunks | Changed cache key to `reference_id` (always unique), with `doi` as fallback |

### New endpoint feature: `claim_ids` filter

`POST /documents/{document_id}/run-verification` previously processed all claims in a document (e.g. 77 claims × 10s = ~13 minutes). A `claim_ids: list[str] | None` field was added to `PipelineRunRequest` and wired through to the orchestrator, allowing a targeted single-claim run for testing and debugging.

| File | Change |
|---|---|
| `app/api/v1/verification.py` | Added `claim_ids: list[str] | None = None` to `PipelineRunRequest`; passed to orchestrator |
| `app/services/verification_orchestrator.py` | Added `claim_ids` parameter; filters `eligible_packages` before the verification loop |

### Performance characteristics (real pipeline)

With real LLM and embeddings active:

| Scenario | Estimated time |
|---|---|
| Single claim, FULL_TEXT_AVAILABLE | ~10–25 seconds |
| Full document, 10 claims, 8 unique references | ~2 minutes |
| Full document, 77 claims, 54 unique references (first run) | ~10–13 minutes |
| Re-run with `use_cache: true` (default) | < 5 seconds (DB cache hit) |

The embedding cache in `rag/api.py` (keyed by `reference_id`) ensures each unique paper is embedded only once per server process lifetime, not once per claim.
