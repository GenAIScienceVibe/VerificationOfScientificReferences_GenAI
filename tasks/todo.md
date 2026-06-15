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

### SCRUM-179: Chunking (`rag/ingestion/chunker.py`) — NEXT

- [ ] Detect sections using heading patterns
- [ ] Normalize section names with SECTION_MAP
- [ ] Skip sections in SKIP_SECTIONS list
- [ ] Split paragraphs within each section
- [ ] Apply 512-token window for large paragraphs
- [ ] Tag every chunk with section + priority + metadata
- [ ] Fallback: blind chunking if no sections detected
- [ ] Write unit tests in `tests/rag/test_chunker.py`
- [ ] Commit on `feature/rag-ingestion`

---

## Upcoming Tasks

| ID        | Module              | Branch                  | Status  |
|-----------|---------------------|-------------------------|---------|
| SCRUM-178 | cleaner.py          | feature/rag-ingestion   | ✓ Done  |
| SCRUM-179 | chunker.py          | feature/rag-ingestion   | Pending |
| SCRUM-180 | embedder.py         | feature/rag-retrieval   | Pending |
| SCRUM-186 | vector_store.py     | feature/rag-retrieval   | Pending |
| SCRUM-184 | benchmark.py        | feature/rag-retrieval   | Pending |
| SCRUM-185 | latency.py          | feature/rag-retrieval   | Pending |
