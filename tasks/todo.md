# verifAi RAG — Task Tracker

## Current Sprint

### SCRUM-178: Text Cleaning (`rag/ingestion/cleaner.py`)

- [x] Create `rag/__init__.py` and `rag/ingestion/__init__.py`
- [x] Write `rag/ingestion/models.py` — Pydantic models (CleanerInput, CleanerOutput, EvidenceAvailability)
- [x] Write `rag/ingestion/cleaner.py` — 5-step cleaning pipeline
  - [x] `_normalize_whitespace` — CRLF, tabs, multi-spaces
  - [x] `_remove_page_numbers` — regex for page number lines
  - [x] `_remove_repeated_lines` — frequency-based header/footer detection
  - [x] `_remove_references_section` — cut from last "References" heading
  - [x] `_collapse_blank_lines` — max 2 consecutive blank lines
  - [x] `clean_text` — orchestrator with logging
- [x] Write `tests/rag/test_cleaner.py` — 30 unit tests
- [x] Run tests — **30/30 passed**
- [x] Write `docs/rag/cleaner.md` — module documentation
- [x] Commit on `feature/rag-ingestion`

**Status: COMPLETE ✓**

---

### SCRUM-179: Chunking (`rag/ingestion/chunker.py`)

- [x] Add `ChunkMetadata`, `ChunkerInput`, `ChunkerOutput` to `models.py`
- [x] Write `rag/ingestion/chunker.py` — section-aware chunking
  - [x] `_looks_like_heading` / `_is_heading` — heading detection with context
  - [x] `normalize_section_name` — SECTION_MAP lookup with prefix stripping
  - [x] `should_skip_section` — SKIP_SECTIONS filter
  - [x] `split_into_sections` — full text → list of (name, content) pairs
  - [x] `_merge_short_paragraphs` — merge paragraphs < 50 tokens
  - [x] `_chunk_section` — RecursiveCharacterTextSplitter + metadata tagging
  - [x] `chunk_text` — orchestrator with fallback detection
- [x] Write `tests/rag/test_chunker.py` — 72 unit tests
- [x] Run tests — **72/72 passed** (102/102 total across both modules)
- [x] Write `docs/rag/chunker.md` — module documentation
- [x] Commit on `rag_dec_zac`

**Status: COMPLETE ✓**

---

---

### SCRUM-186: Vector Store (`rag/retrieval/vector_store.py`)

- [x] Add `VectorStoreInput`, `RetrievedChunk`, `VectorStoreOutput` to `rag/retrieval/models.py`
- [x] Write `rag/retrieval/vector_store.py` — FAISS-based cosine search with section weighting
  - [x] `_to_float32` — convert list[list[float]] to float32 numpy array
  - [x] `_normalise` — L2-normalise a copy of a float32 matrix
  - [x] `_get_section_weight` — look up section priority from SECTION_WEIGHTS
  - [x] `_build_index` — build an in-memory IndexFlatIP from normalised vectors
  - [x] `search` — orchestrator: build index → oversample search → apply weights → re-rank → return top-k
- [x] Write `tests/rag/test_vector_store.py` — 29 unit tests (real FAISS, no mocking)
- [x] Run tests — **29/29 passed** (147/147 total across all modules)
- [x] Write `docs/rag/vector_store.md` — module documentation
- [x] Installed `numpy` and `faiss-cpu` (were missing from environment)

**Status: COMPLETE ✓**

---

---

### SCRUM-184: Retrieval Benchmark (`rag/evaluation/benchmark.py`)

- [x] Create `rag/evaluation/__init__.py`
- [x] Write `rag/evaluation/benchmark.py` — hit@3 accuracy evaluation script
  - [x] Pydantic models: `BenchmarkCase`, `TopChunkPreview`, `CaseResult`, `BenchmarkReport`
  - [x] `BENCHMARK_CASES` — 5 synthetic papers with known claim-evidence pairs
  - [x] `_build_client` — OpenRouter client builder
  - [x] `_embed_text` — embed a single claim string
  - [x] `_check_hit` — whitespace-normalised substring match against top-K chunks
  - [x] `_run_case` — full pipeline (clean → chunk → embed → search) for one case
  - [x] `_save_report` — write JSON report with configurable output path
  - [x] `run_benchmark` — orchestrator with error handling + console summary
- [x] Write `tests/rag/test_benchmark.py` — 22 unit tests (no API calls)
- [x] Run tests — **22/22 passed** (169/169 total across all modules)
- [x] Write `docs/rag/benchmark.md` — module documentation
- [x] Installed `python-dotenv` (was missing from environment)
- [x] Fixed `_check_hit` to normalise whitespace before matching (source text line-wraps inside evidence phrases)

**Status: COMPLETE ✓**

---

## Upcoming Tasks

| ID        | Module              | Branch                  | Status  |
|-----------|---------------------|-------------------------|---------|
| SCRUM-178 | cleaner.py          | rag_dev_zac             | ✓ Done  |
| SCRUM-179 | chunker.py          | rag_dev_zac             | ✓ Done  |
| SCRUM-180 | embedder.py         | rag_dev_zac             | ✓ Done  |
| SCRUM-186 | vector_store.py     | rag_dev_zac             | ✓ Done  |
| SCRUM-184 | benchmark.py        | rag_dev_zac             | ✓ Done  |
| SCRUM-185 | latency.py          | rag_dev_zac             | Pending |
