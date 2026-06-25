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

---

### SCRUM-185: Latency & Cost (`rag/evaluation/latency.py`)

- [x] Write `rag/evaluation/latency.py` — embedding latency and cost profiler
  - [x] Pydantic models: `CallResult`, `BatchCallResult`, `LatencyStats`, `LatencyReport`
  - [x] `TEST_CHUNKS` — 10 synthetic scientific text chunks of varying length
  - [x] `_build_client` — OpenRouter client builder
  - [x] `_count_tokens` — tiktoken cl100k_base token counter
  - [x] `_embed_single` — single-chunk API call with wall-clock timing
  - [x] `_embed_batch` — all-chunks-in-one-request API call with timing
  - [x] `_compute_stats` — min, max, mean, median, p95, stdev over latencies
  - [x] `_save_report` — write JSON report with configurable output path
  - [x] `run_latency_profile` — orchestrator: 10 individual calls + 1 batch call + stats
- [x] Write `tests/rag/test_latency.py` — 43 unit tests (no API calls)
- [x] Run tests — **43/43 passed** (212/212 total across all modules)
- [x] Write `docs/rag/latency.md` — module documentation

**Status: COMPLETE ✓**

---

---

### SCRUM-194: Output Schema (`rag/verification/models.py`)

- [x] Create `rag/verification/__init__.py`
- [x] Write `rag/verification/models.py`
  - [x] `Verdict` enum — 5 labels matching backend schema exactly
  - [x] `VerificationInput` — claim_text, citation_type, chunks, doi
  - [x] `VerificationOutput` — verdict, confidence (0–1), explanation, evidence_used, limitations, human_review_required
- [x] Write `tests/rag/test_verification_models.py` — 23 unit tests
- [x] Run tests — **23/23 passed** (243/243 total across all modules)
- [x] Write `docs/rag/verification_models.md` — module documentation

**Status: COMPLETE ✓**

---

### SCRUM-254: Temperature=0 Audit (`rag/prompts/config.py`)

- [x] Audit all existing LLM calls in the codebase
  - Found only `embeddings.create()` in `rag/retrieval/embedder.py` — embeddings API has no `temperature` param, so N/A
  - `classifier.py` (SCRUM-252) and `verifier.py` (SCRUM-193) not yet built — no chat-completion call sites exist yet
- [x] Create `rag/prompts/__init__.py`
- [x] Write `rag/prompts/config.py` — `LLM_TEMPERATURE = 0` shared constant with rationale comment
- [x] Write `tests/rag/test_prompts_config.py` — 2 unit tests
- [x] Run tests — **2/2 passed** (245/245 total across all modules)
- [x] Write `docs/rag/prompts_config.md` — module documentation
- [x] Future modules (classifier.py, verifier.py) must import `LLM_TEMPERATURE` instead of hardcoding `0`

**Status: COMPLETE ✓**

---

### SCRUM-252: Citation Type Classifier (`rag/prompts/classifier.py`)

- [x] Write `rag/prompts/classifier.py`
  - [x] `CitationType` enum — 6 labels (RESULT_COMPARISON, METHOD, BACKGROUND, MOTIVATION, EXTENSION, FUTURE_WORK)
  - [x] `SYSTEM_PROMPT` — instructs LLM to output exactly one label
  - [x] `_build_client` — OpenRouter client builder (lazy, mirrors embedder.py)
  - [x] `_parse_label` — strict parsing, raises ValueError on unknown label
  - [x] `classify_citation_type` — one LLM call at temperature=0 (via LLM_TEMPERATURE), falls back to BACKGROUND on any failure
- [x] Write `tests/rag/test_classifier.py` — 18 unit tests (mocked LLM responses, no real API calls)
- [x] Run tests — **18/18 passed** (263/263 total across all modules)
- [x] Write `docs/rag/classifier.md` — module documentation

**Status: COMPLETE ✓**

---

### SCRUM-193: Prompt Template + LLM Call (`rag/prompts/verifier.py`)

- [x] Add `jinja2==3.1.6` to `rag/requirements.txt` (was missing despite being in tech stack) and install it
- [x] Write `rag/prompts/templates/verify.j2` — claim + citation type + DOI + chunks (chunk_id, section, chunk_text), instructs JSON-only output matching VerificationOutput shape, handles empty chunks list
- [x] Write `rag/prompts/verifier.py`
  - [x] `_build_client` — OpenRouter client builder (lazy, mirrors embedder.py/classifier.py)
  - [x] `render_prompt` — pure function, renders verify.j2 from VerificationInput
  - [x] `generate_verdict` — one LLM call at temperature=0 (via LLM_TEMPERATURE), returns raw response text (no parsing — that's validator.py, SCRUM-253)
- [x] Write `tests/rag/test_verifier.py` — 13 unit tests (render_prompt tested directly, generate_verdict with mocked LLM)
- [x] Run tests — **13/13 passed** (276/276 total across all modules)
- [x] Write `docs/rag/verifier.md` — module documentation

**Status: COMPLETE ✓**

---

### SCRUM-195: Chain-of-Thought (`rag/prompts/templates/verify.j2`)

- [x] Updated `verify.j2` to require step-by-step reasoning inside the `explanation` field:
  1. What the claim says, 2. What the source evidence says, 3. Comparison, 4. Verdict reasoning
- [x] Updated `docs/rag/verifier.md` with the chain-of-thought section
- [x] Added 4 new tests to `tests/rag/test_verifier.py`
  - [x] `test_render_prompt_instructs_step_by_step_reasoning`
  - [x] `test_render_prompt_requires_four_part_reasoning_structure`
  - [x] `test_render_prompt_requires_reasoning_inside_explanation_field`
  - [x] `test_generate_verdict_preserves_four_step_reasoning_in_explanation`
- [x] Run tests — **17/17 passed** in test_verifier.py (280/280 total across all modules)

**Status: COMPLETE ✓**

---

### SCRUM-196: Confidence Score + Human Review Flag (`rag/prompts/verifier.py`)

- [x] Add `HUMAN_REVIEW_CONFIDENCE_THRESHOLD = 0.5` constant
- [x] Add `compute_human_review_required(verdict, confidence, low_confidence=False)` — pure function, applies the 3 OR conditions from CLAUDE.md
- [x] Add `attach_human_review_flag(raw_json, low_confidence=False)` — parses raw LLM JSON, injects the flag (does NOT handle malformed JSON/missing fields gracefully — that's validator.py, SCRUM-253)
- [x] Add 17 new tests to `tests/rag/test_verifier.py` covering all trigger conditions:
  - [x] no trigger → False
  - [x] confidence < 0.5 → True
  - [x] confidence == 0.5 (boundary) → False
  - [x] verdict == PARTIALLY_SUPPORTED (enum and string) → True
  - [x] low_confidence=True → True
  - [x] multiple triggers at once → True
  - [x] other verdicts with high confidence → False
  - [x] attach_human_review_flag success + malformed JSON + missing field cases
- [x] Run tests — **34/34 passed** in test_verifier.py (297/297 total across all modules)
- [x] Update `docs/rag/verifier.md` with the confidence/human-review section

**Status: COMPLETE ✓**

---

### SCRUM-253: Pydantic Output Validation (`rag/verification/validator.py`)

- [x] Write `rag/verification/validator.py`
  - [x] `_fallback_output` — builds a valid NEEDS_HUMAN_REVIEW VerificationOutput
  - [x] `validate_output` — parses raw LLM JSON via attach_human_review_flag (reused from verifier.py, SCRUM-196), then constructs VerificationOutput; catches JSONDecodeError, KeyError, and pydantic ValidationError, logging each and falling back to NEEDS_HUMAN_REVIEW
- [x] Write `tests/rag/test_validator.py` — 14 unit tests
  - [x] valid output (SUPPORTED, PARTIALLY_SUPPORTED, low_confidence flag, default fields)
  - [x] malformed JSON (incl. empty string) + logging
  - [x] missing required fields (verdict, confidence, explanation) + logging
  - [x] schema mismatches (unrecognised verdict label, out-of-range confidence) + logging
- [x] Run tests — **14/14 passed** (311/311 total across all modules)
- [x] Write `docs/rag/validator.md` — module documentation

**Status: COMPLETE ✓**

---

## SCRUM-192: Prompt Engineering — Sprint Review

All 7 subtasks (Tasks 7–13) complete: output schema, temperature audit,
citation classifier, prompt template + LLM call, chain-of-thought, confidence
+ human review flag, and Pydantic output validation. 311/311 tests passing.

The Door 2 pipeline is now fully wired end to end:
`VerificationInput` → `classify_citation_type()` → `generate_verdict()`
(CoT prompt, temp=0) → `attach_human_review_flag()` → `validate_output()`
→ `VerificationOutput`.

Notable decisions worth remembering:
- `rag/prompts/config.py` centralises `LLM_TEMPERATURE` so no call site can drift.
- The `human_review_required` rule lives once in `verifier.py` and is reused by `validator.py` — not duplicated.
- Chain-of-thought reasoning lives inside the `explanation` JSON field, not as separate output text, to keep the JSON-only response contract intact.
- `validator.py` never raises — every failure mode collapses to a safe `NEEDS_HUMAN_REVIEW` output.

---

## Upcoming Tasks

| ID        | Module              | Branch                  | Status  |
|-----------|---------------------|-------------------------|---------|
| SCRUM-178 | cleaner.py          | rag_dev_zac             | ✓ Done  |
| SCRUM-179 | chunker.py          | rag_dev_zac             | ✓ Done  |
| SCRUM-180 | embedder.py         | rag_dev_zac             | ✓ Done  |
| SCRUM-186 | vector_store.py     | rag_dev_zac             | ✓ Done  |
| SCRUM-184 | benchmark.py        | rag_dev_zac             | ✓ Done  |
| SCRUM-185 | latency.py          | rag_dev_zac             | ✓ Done  |
| SCRUM-194 | verification/models.py | rag_dev_zac           | ✓ Done  |
| SCRUM-254 | prompts/config.py    | rag_dev_zac             | ✓ Done  |
| SCRUM-252 | classifier.py        | rag_dev_zac             | ✓ Done  |
| SCRUM-193 | verifier.py           | rag_dev_zac             | ✓ Done  |
| SCRUM-195 | verify.j2 CoT          | rag_dev_zac             | ✓ Done  |
| SCRUM-196 | confidence + review flag | rag_dev_zac          | ✓ Done  |
| SCRUM-253 | validator.py           | rag_dev_zac             | ✓ Done  |

---

## Integration: Backend Handoff Layer (`rag/api.py`)

- [x] Write `rag/api.py` — two callable functions for the backend, no HTTP endpoints
  - [x] `retrieve_evidence()` — wraps cleaner → chunker → embedder → vector_store (Door 1)
  - [x] `verify_claim()` — wraps classifier → verifier → validator (Door 2)
  - [x] Request/response Pydantic models matching the CLAUDE.md JSON contracts literally (field names like `support_status` differ from our internal `verdict`, so these are new models, not reused internal ones)
  - [x] INVALID/UNRESOLVABLE doi_status short-circuits both doors before any pipeline call
  - [x] Pipeline exceptions in either door are caught and converted to a safe fallback (`FAILED` / `NEEDS_HUMAN_REVIEW`) — neither function raises
  - [x] `low_confidence` bridge in `verify_claim()`: Door 2 only gives `overall_similarity_score` (a float, not a flag), so the same `SIMILARITY_THRESHOLD` from `vector_store.py` is reapplied to derive it
- [x] Write `tests/rag/test_api.py` — 12 unit tests (pipeline functions mocked at the `rag.api` import boundary)
- [x] Run tests — **323/323 passed** across all modules
- [x] Write `docs/rag/api.md` — explains the handoff layer to Jona and Sanilka in plain language
- [x] **Known gap documented**: Door 1 only wraps dense FAISS retrieval — `bm25_retriever.py` and `hybrid_retriever.py` (mentioned in CLAUDE.md's file naming conventions) don't exist yet, so true hybrid retrieval + FlashRank reranking isn't wired in. `retrieve_evidence()`'s contract won't need to change when those land — only its internal Step 5.

**Status: COMPLETE ✓**

---

## Sprint: Hybrid Retrieval (branch `rag_dev_zac_hybrid`)

### SCRUM-257: BM25 Keyword Retrieval (`rag/retrieval/bm25_retriever.py`)

- [x] `pip install rank-bm25`
- [x] Added `Bm25RetrieverInput`, `Bm25RetrievedChunk`, `Bm25RetrieverOutput` to `rag/retrieval/models.py`
- [x] Wrote `rag/retrieval/bm25_retriever.py`
  - [x] Imports `SECTION_WEIGHTS`/`DEFAULT_WEIGHT` from `vector_store.py` (not duplicated)
  - [x] `_tokenize` — lowercase + `\w+` regex tokenizer
  - [x] `_build_index` — `BM25Okapi(tokenized_corpus)`
  - [x] `search` — tokenize chunks + query, score via BM25, multiply by section weight, sort, take top_k
  - [x] Empty-chunks fallback returns empty `Bm25RetrieverOutput`
- [x] Wrote `tests/rag/test_bm25_retriever.py` — 12 unit tests (tokenizer, section weight, empty input, ranking order, weighting math, top_k limiting)
- [x] Run tests — **12/12 passed** (335/335 total across all modules)
- [x] Caught and fixed a test-design issue: BM25 IDF can go negative for a term present in every doc of a tiny 2-chunk corpus, which inverts the expected section-weight ordering — not a bug in the retriever, just an edge case of tiny test corpora. Fixed by adding a filler chunk to the section-weight test so IDF stays positive.
- [x] Wrote `docs/rag/bm25_retriever.md`
- [x] Commit: `[RAG] SCRUM-257: implement BM25 keyword retriever`

**Status: COMPLETE ✓**

---

### SCRUM-258: Hybrid Retrieval Merger (`rag/retrieval/hybrid_retriever.py`)

- [x] Added `HybridRetrieverInput`, `HybridRetrievedChunk`, `HybridRetrieverOutput` to `rag/retrieval/models.py`
- [x] Wrote `rag/retrieval/hybrid_retriever.py`:
  - [x] `RRF_K = 60` constant (standard RRF smoothing constant; dampens the impact of rank 1 vs rank 2 so one retriever can't dominate)
  - [x] `_rrf_score(rank: int) -> float` — `1 / (RRF_K + rank)`
  - [x] `merge(input_data: HybridRetrieverInput) -> HybridRetrieverOutput` — dedupes by `chunk.chunk_id`, sums RRF contributions from whichever ranker(s) found each chunk (no penalty if absent from one), sorts by combined `rrf_score` descending, takes top_k
  - [x] Empty-input fallback returns empty `HybridRetrieverOutput`
- [x] Wrote `tests/rag/test_hybrid_retriever.py` — 10 unit tests (RRF math, empty inputs, dedup, score combination, ranking precedence, top_k limiting)
- [x] Run tests — **10/10 passed** (345/345 total across all modules)
- [x] Wrote `docs/rag/hybrid_retriever.md`
- [x] Commit: `[RAG] SCRUM-258: implement hybrid retrieval with RRF merging`

**Status: COMPLETE ✓**

---

### SCRUM-259: FlashRank Neural Reranking (extends `rag/retrieval/hybrid_retriever.py`)

- [x] `pip install flashrank` — confirmed it downloads its default model (`ms-marco-TinyBERT-L-2-v2`, ~3MB, lazy on first `Ranker()` call) and reranks correctly in a smoke test
- [x] Extended `rag/retrieval/models.py`: added `claim: str` to `HybridRetrieverInput`, `rerank_score: float | None` to `HybridRetrievedChunk`
- [x] Extended `rag/retrieval/hybrid_retriever.py`:
  - [x] `RERANK_MODEL = "ms-marco-TinyBERT-L-2-v2"`, `RERANK_OVERSAMPLE_FACTOR = 3`
  - [x] `_build_ranker()` — lazy `Ranker(model_name=RERANK_MODEL)` builder
  - [x] `_rerank(claim, candidates)` — builds `RerankRequest`, calls `ranker.rerank()`, returns `chunk_id -> score` map
  - [x] `merge()` now takes the RRF top `top_k × RERANK_OVERSAMPLE_FACTOR` candidate pool, reranks only those, returns final top_k by `rerank_score`
  - [x] Graceful fallback: FlashRank exceptions are caught, logged, and RRF-only ordering is kept (`rerank_score=None`)
- [x] Updated `tests/rag/test_hybrid_retriever.py` — autouse fixture makes `_build_ranker` raise by default (no real model calls in unit tests, mirrors `classifier.py`'s OpenAI mocking); 4 new tests cover real reordering by mocked rerank scores, oversample-pool-only coverage, fallback-on-exception, and rerank_score=None when disabled
- [x] Run tests — **349/349 passed** across all modules
- [x] Updated `docs/rag/hybrid_retriever.md` with the FlashRank section
- [x] Commit: `[RAG] SCRUM-259: add FlashRank neural reranking`

**Status: COMPLETE ✓ — Task 4 (SCRUM-260) on hold pending Saqer's go-ahead**
