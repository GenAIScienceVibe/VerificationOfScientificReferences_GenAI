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

### CORE full-text integration
- After Unpaywall, the system queries the **CORE API** (`https://api.core.ac.uk/v3/`) for papers that Unpaywall could not provide.
- `CoreClient.get_fulltext_by_doi()` returns the full text inline (no PDF download needed) for many open-access papers indexed by CORE.
- Active only when `CORE_API_KEY` is set in `.env`; gracefully skipped otherwise.
- Requires `CORE_API_KEY` and optionally `CORE_BASE_URL` in `.env`.

### `force_refresh` on verify-dois
- Added `force_refresh: bool` query parameter to `POST /documents/{document_id}/verify-dois`.
- When `true`, re-runs the full lookup chain (CrossRef → OpenAlex → SemanticScholar → Unpaywall → CORE → PDF extraction) even for DOIs that already have cached metadata.
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
| `app/clients/metadata_clients.py` | `SemanticScholarClient.lookup_by_arxiv_id()`; `CoreClient` with `search_by_title()` and `get_fulltext_by_doi()` |
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

## Evidence availability hierarchy (updated)

```
FULL_TEXT_AVAILABLE   ← Unpaywall OA PDF, arXiv PDF, or user upload  ✅ best
PREPRINT_AVAILABLE    ← SSRN working paper abstract (new)            ⚠️ human review required
ABSTRACT_AVAILABLE    ← OpenAlex / SemanticScholar abstract only
METADATA_ONLY         ← CrossRef title/authors/year, no text
SOURCE_UNAVAILABLE    ← DOI did not resolve at all
```

`FULL_TEXT_AVAILABLE` and `ABSTRACT_AVAILABLE` allow the RAG pipeline to retrieve text and produce a verdict. `PREPRINT_AVAILABLE` also retrieves text but caps confidence at 0.65 and always requires human review via the `PREPRINT_SOURCE` safety rule. `METADATA_ONLY` and `SOURCE_UNAVAILABLE` skip Door 1 entirely.

---

## Known limitations

- **Elsevier Gold OA**: Unpaywall may report `is_oa: true` but return no `url_for_pdf`. Elsevier requires a separate Text and Data Mining (TDM) API key for programmatic PDF access. In this case the system falls back to abstract-only, and the user can upload the PDF manually via the new endpoint.
- **CORE API**: Integrated as a fourth source in the title-search chain and as a full-text fallback after Unpaywall. Active only when `CORE_API_KEY` is set in `.env`; skipped gracefully otherwise. Rate limit: 1,000 req/day on the free tier.
- **Semantic Cache (BE-8)**: `SemanticCacheClient` exists as a class but performs no real embedding-based similarity lookup — it is a stub. The verification cache uses exact claim-ID matching instead. This is sufficient for demo and correctness; a real vector-based semantic cache would be a future enhancement.

---

## Title-based DOI lookup fallback (four-source chain)

Papers in management, law, and humanities journals often omit DOIs from their reference lists. Previously these references immediately received `doi_status: MISSING` and all claims citing them returned `NEEDS_HUMAN_REVIEW`.

A title-based fallback is now integrated into `_verify_reference()` in `doi_metadata_lookup.py`. When a reference has no extractable DOI but does have an extracted title, the system queries **four sources in sequence** before marking the reference as missing: CrossRef, OpenAlex, SemanticScholar, and CORE.

### How it works

For each source (CrossRef → OpenAlex → SemanticScholar → CORE):
1. Search by title and, if available, author/year.
2. Evaluate the top result against three false-match guards (all must pass):
   - **Title similarity ≥ 0.95** — `max(SequenceMatcher ratio, word-coverage ratio)`. The word-coverage component handles the common case where the extracted title lacks a subtitle.
   - **Year mismatch check** — both years must agree within 1 year (if both present).
   - **Author overlap check** — at least one last name must match (if both present).
3. HTML entities in titles (e.g. `&#8220;`) are decoded before comparison so `&amp;` and `"` match correctly.
4. If a confident match is found and the source returns a DOI, the discovered DOI is set on `reference.extracted_doi` and the normal lookup chain continues with it.
5. CORE is only queried when `CORE_API_KEY` is set in `.env` — it is skipped gracefully otherwise.
6. If no source produces a confident match, the reference is still marked `MISSING` as before.

### Full-text chain

After a DOI is resolved, the system attempts to obtain full text in this order:
1. **arXiv direct PDF** — for arXiv DOIs, always publicly available
2. **Unpaywall** — legal open-access PDF URL, streamed and parsed with PyMuPDF
3. **CORE** — returns full text inline in the JSON response for many papers (no PDF download required); falls back to a CORE download URL if only a URL is returned. Active only when `CORE_API_KEY` is set.

### Practical effect

A Strategic Management Journal paper with 31/32 references that have no DOIs would previously result in all those claims getting `NEEDS_HUMAN_REVIEW`. With the four-source title fallback, most of those references can be resolved to DOIs, enabling full RAG verification.

### Files changed

| File | Change |
|------|--------|
| `app/clients/metadata_clients.py` | `_normalize_title()`, `_title_similarity()`, `_authors_overlap()` helpers; `search_by_title()` on CrossRefClient, OpenAlexClient, SemanticScholarClient; new `CoreClient` class with `search_by_title()` and `get_fulltext_by_doi()` |
| `app/services/doi_metadata_lookup.py` | Four-source title-search chain in `_verify_reference()`; CORE full-text fallback after Unpaywall; HTML entity decoding before title comparison |

---

## SSRN / preprint source detection

SSRN working papers (DOI prefix `10.2139/ssrn.*`) and other preprint sources are now detected and handled as a distinct evidence tier, separate from peer-reviewed abstracts.

### What changed

**New enum value:** `PREPRINT_AVAILABLE` added to `EvidenceAvailability` (between `ABSTRACT_AVAILABLE` and `FULL_TEXT_AVAILABLE`).

**Detection:** `_is_preprint_source()` in `evidence_package_builder.py` checks three signals:
- DOI starts with `10.2139/ssrn.`
- URL contains `ssrn.com`
- `lookup_source` field contains `ssrn`

**Abstract fallback:** `SsrnClient` in `metadata_clients.py` scrapes the SSRN abstract page (`https://papers.ssrn.com/sol3/papers.cfm?abstract_id=XXXXXX`) when a reference has an SSRN DOI but no abstract yet. The client is used as a fourth fallback in `doi_metadata_lookup.py` after SemanticScholar.

**Safety rule:** `PREPRINT_SOURCE` rule added to `safety_policy.py`:
- Risk level: MEDIUM, status: WARNING
- Caps confidence at `SAFETY_MAX_CONFIDENCE_WITH_PREPRINT` (default 0.65)
- Always sets `human_review_required=True`
- Rationale: preprint text may differ from the final published version

**RAG layer:** `PREPRINT_AVAILABLE` maps to `ABSTRACT_AVAILABLE` in `_EVIDENCE_AVAIL_TO_RAG` — the retrieval pipeline treats it identically to an abstract. The distinction only matters at the safety policy layer.

**Warning in evidence package:** packages built for preprint sources include a `PREPRINT_SOURCE` warning with the message: *"Evidence is from a preprint (e.g. SSRN working paper). Text may differ from the final published version."*

### Files changed

| File | Change |
|------|--------|
| `app/models/enums.py` | `PREPRINT_AVAILABLE = "PREPRINT_AVAILABLE"` added to `EvidenceAvailability` |
| `app/clients/metadata_clients.py` | New `SsrnClient` class with `ssrn_id_from_doi()`, `get_abstract_for_doi()`, `_fetch_abstract()` |
| `app/core/config.py` | `safety_max_confidence_with_preprint: float = 0.65` field |
| `app/services/evidence_package_builder.py` | `_SSRN_DOI_PREFIX`, `_is_preprint_source()`, `PREPRINT_AVAILABLE` branch in `_source_evidence()`, `PREPRINT_SOURCE` warning in `_warnings_for_link()`, `preprint_available` counter in response |
| `app/services/safety_policy.py` | `PREPRINT_SOURCE` `elif` block after `SOURCE_UNAVAILABLE` |
| `app/services/doi_metadata_lookup.py` | `SsrnClient` import; SSRN abstract fallback block after SemanticScholar fallback |
| `app/services/rag_ml_integration.py` | `PREPRINT_AVAILABLE → ABSTRACT_AVAILABLE` in `_EVIDENCE_AVAIL_TO_RAG`; `PREPRINT_AVAILABLE` branch in `MockRagClient` |
| `.env.example` | `SAFETY_MAX_CONFIDENCE_WITH_PREPRINT=0.65` |

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

---

## Pre-existing test failures fixed (integration/backend-rag-merge)

Five test failures that existed before the integration branch were resolved:

| Test | Root cause | Fix |
|------|-----------|-----|
| `test_reference_extraction` | SQLite returns rows in non-deterministic order when `created_at` timestamps are identical; test assumed `references[0]` was always the Smith ref | Find Smith ref by DOI instead of by index |
| `test_rag_response_validator_rejects_wrong_claim_id_and_bad_scores` | Validator was intentionally changed to clamp `similarity_score > 1.0` to `1.0` (SCRUM-262) instead of raising `ValueError` | Assert `score == 1.0` instead of `pytest.raises` |
| `test_metadata_only_package_returns_metadata_chunk` | `METADATA_ONLY` was added to `_skip_availabilities` in BE-9 (Door 1 is bypassed entirely for these packages) | Assert `NO_RELEVANT_EVIDENCE_FOUND` and `top_chunks == []` |
| `test_pipeline_run_happy_path` | Live LLM call sometimes returns empty and falls back to `FALLBACK_NEEDS_REVIEW`; test asserted exactly `"RAG_PLUS_GENAI"` | Accept both `"RAG_PLUS_GENAI"` and `"FALLBACK_NEEDS_REVIEW"` |
| `test_be4_2_real_pdf_regression` | Windows default encoding is CP1252; fixture file `pdf2_be42_reference_section.txt` contains non-CP1252 characters | Add `encoding="utf-8"` to all `Path.read_text()` calls in the test |

All 130 backend tests pass after these fixes.

---

## Future optimizations / Outlook

### HyDE — Hypothetical Document Embeddings (TBD)

**What:** Instead of embedding the raw claim text as the Door 1 query, first use an LLM to generate a *hypothetical abstract paragraph* that would support the claim, then embed that paragraph.

**Why it helps:** A claim like *"AI tools improve academic writing productivity"* is short and lacks scientific vocabulary. A hypothetical document bridges the lexical gap between the query and the source chunks (abstract/full-text), producing better cosine similarity and therefore better retrieval recall.

**Trade-off:** +1 LLM call per claim before the embedding step. If the LLM generates a biased or incorrect hypothetical, retrieval quality can degrade instead of improve. An A/B test via `rag/evaluation/benchmark.py` would be needed before adopting this in production.

**Where to implement:** `rag/api.py` → `_embed_single_text()` — add an optional `use_hyde: bool` flag that calls a short LLM prompt to expand the claim before embedding.

### Parallel embedding on cache miss (TBD)

On the first claim for a new paper, `embed_chunks()` (source chunks) and `_embed_single_text()` (claim query) are two independent OpenRouter API calls that currently run sequentially. Running them concurrently with `ThreadPoolExecutor` would reduce Door 1 latency by ~40–50% on cache-miss paths. Risk: doubled instantaneous request rate may trigger OpenRouter rate limiting. Requires careful exception handling for both futures.
