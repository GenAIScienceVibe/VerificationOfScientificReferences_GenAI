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

## Upcoming Tasks

| ID        | Module              | Branch                  | Status  |
|-----------|---------------------|-------------------------|---------|
| SCRUM-178 | cleaner.py          | rag_dec_zac             | ✓ Done  |
| SCRUM-179 | chunker.py          | rag_dec_zac             | ✓ Done  |
| SCRUM-180 | embedder.py         | rag_dec_zac             | ✓ Done  |
| SCRUM-186 | vector_store.py     | rag_dec_zac             | Pending |
| SCRUM-184 | benchmark.py        | feature/rag-retrieval   | Pending |
| SCRUM-185 | latency.py          | feature/rag-retrieval   | Pending |
