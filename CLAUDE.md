# CLAUDE.md — verifAi RAG Sub-group
# TUM Campus Heilbronn · Foundations and Applications of Generative AI · SoSe 2026

---

## WHO YOU ARE WORKING WITH
You are helping Saqer Terkawi (AI & Prompt Engineer) build the RAG pipeline
for the verifAi project. This is a university group project. The code must be
clean, well-documented, and educational — Saqer is learning while building.

Always explain what you are doing and why before writing code.
Keep explanations simple and brief.

---

## PROJECT OVERVIEW
verifAi is a web application that verifies whether scientific claims in a
document are actually supported by their cited sources. It detects:
1. Completely made-up citations (DOI does not resolve)
2. Incorrectly cited sources (source exists but is misattributed)
3. Sources that don't support the claim (source exists but says something different)

---

## OUR SUB-GROUP SCOPE
We own the RAG pipeline inside the `rag/` folder. We do NOT touch:
- `backend/` — owned by Jona and Sanilka
- `frontend/` — owned by Alma, Wiktoria, Leona
- `tests/` — shared, but we write tests for our own modules only

---

## CURRENT PROJECT STATUS
All 13 tasks across SCRUM-178 to SCRUM-253 are COMPLETE and committed.
The integration handoff layer (rag/api.py) is COMPLETE and committed.
Full test suite: 323/323 tests passing on branch rag_dev_zac.

### What is built and working:
- rag/ingestion/cleaner.py         ← SCRUM-178 ✅
- rag/ingestion/chunker.py         ← SCRUM-179 ✅
- rag/retrieval/embedder.py        ← SCRUM-180 ✅
- rag/retrieval/vector_store.py    ← SCRUM-186 ✅ (dense FAISS only)
- rag/evaluation/benchmark.py      ← SCRUM-184 ✅
- rag/evaluation/latency.py        ← SCRUM-185 ✅
- rag/prompts/config.py            ← SCRUM-254 ✅ (LLM_TEMPERATURE=0)
- rag/prompts/classifier.py        ← SCRUM-252 ✅
- rag/prompts/verifier.py          ← SCRUM-193/195/196 ✅
- rag/prompts/templates/verify.j2  ← SCRUM-195 ✅
- rag/verification/models.py       ← SCRUM-194 ✅
- rag/verification/validator.py    ← SCRUM-253 ✅
- rag/api.py                       ← Integration handoff layer ✅

### What is NOT built yet (current sprint):
- rag/retrieval/bm25_retriever.py  ← SCRUM-257 (TODO)
- rag/retrieval/hybrid_retriever.py← SCRUM-258 + SCRUM-259 (TODO)

---

## CURRENT BRANCH
You are working on branch: `rag_dev_zac_hybrid`
This is a NEW branch created from `rag_dev_zac`.
NEVER push to `main`. NEVER push to `rag_dev_zac` from this branch.

The reason for the separate branch: we need to test the pipeline
BEFORE (rag_dev_zac) and AFTER (rag_dev_zac_hybrid) adding hybrid
retrieval, to prove the new features improve retrieval quality.

---

## REPO STRUCTURE (our folder)
```
rag/
├── ingestion/         ← text cleaning + chunking
├── retrieval/         ← embedding + vector store + BM25 + hybrid (new)
├── prompts/           ← classifier + verifier + templates
├── verification/      ← output schema + validator
├── evaluation/        ← benchmarking + latency
└── api.py             ← integration handoff layer for backend
```

---

## GIT RULES
- NEVER push to `main`
- NEVER push to `rag_dev_zac` from this branch
- Always work on branch: `rag_dev_zac_hybrid`
- Commit message format: `[RAG] SCRUM-XXX: short description`
- Example: `[RAG] SCRUM-257: implement BM25 keyword retriever`

---

## TECH STACK (our sub-group only)
- Language: Python 3.11+
- Text splitting: langchain-text-splitters (RecursiveCharacterTextSplitter)
- Token counting: tiktoken
- Embedding model: text-embedding-3-small (OpenAI API via OpenRouter)
- Vector store: FAISS (faiss-cpu) — runtime only, built per request, discarded after use
- Keyword search: rank_bm25
- Reranking: flashrank
- LLM: meta-llama/llama-4-scout via OpenRouter
- Prompt templates: Jinja2
- Output validation: Pydantic
- Config/secrets: python-dotenv (.env file)
NOTE: PostgreSQL / SQLAlchemy are NOT our responsibility — backend owns all storage.

---

## ENVIRONMENT VARIABLES
All secrets go in `.env` file (never commit this file). Use `.env.example` as template.
```
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

## API CONFIGURATION — IMPORTANT
We use OpenRouter as our API provider. OpenRouter gives access to all models
through one single API key and one base URL.

NEVER call OpenAI or Groq directly. Always use OpenRouter.

### How to initialize the client in code:
```python
import openai
from dotenv import load_dotenv
import os

load_dotenv()

client = openai.OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url=os.getenv("OPENROUTER_BASE_URL")
)
```

### Model names to use (via OpenRouter):
```python
EMBEDDING_MODEL = "openai/text-embedding-3-small"
LLM_MODEL = "meta-llama/llama-4-scout"
```

---

## INPUT / OUTPUT CONTRACT WITH BACKEND
The backend calls us through rag/api.py. Two public functions only.

### retrieve_evidence() — Door 1
Input: RetrieveEvidenceRequest (claim + DOI + source text)
Output: RetrieveEvidenceResponse (top chunks + scores + retrieval status)

### verify_claim() — Door 2
Input: VerifyClaimRequest (claim + chunks from Door 1 + metadata)
Output: VerifyClaimResponse (verdict + confidence + explanation + human_review flag)

Full JSON schemas are in rag/api.py docstrings and docs/rag/api.md.
DO NOT change the API contract — only internal pipeline logic changes.

---

## VERDICT LABELS (must match backend schema exactly)
```
SUPPORTED
PARTIALLY_SUPPORTED
NOT_SUPPORTED
INSUFFICIENT_EVIDENCE
NEEDS_HUMAN_REVIEW
```

---

## PIPELINE OVERVIEW (full flow)

### IMPORTANT: We are a processing engine, not a storage system.
We receive → process → return. The backend owns ALL storage.
FAISS is built at runtime per paper and discarded after use.

### Door 1 — RAG Retrieval
```
Receive from backend: claim + DOI + source text
  ↓
1. Text cleaning (cleaner.py)
2. Section-aware chunking (chunker.py)
3. Embed source chunks → temporary FAISS index (embedder.py + vector_store.py)
4. Embed the claim
5. Dense retrieval — cosine similarity + section priority weights (vector_store.py)
6. BM25 keyword retrieval (bm25_retriever.py) ← NEW
7. Hybrid merge — combine dense + BM25 with RRF (hybrid_retriever.py) ← NEW
8. FlashRank neural reranking (hybrid_retriever.py) ← NEW
Return to backend: top chunks + scores + retrieval confidence
```

### Door 2 — LLM Verification
```
Receive from backend: claim + selected chunks + metadata
  ↓
1. Citation type classification (classifier.py)
2. Jinja2 prompt with chain-of-thought (verify.j2)
3. LLM call via OpenRouter, temperature=0 (verifier.py)
4. Pydantic validation + human review flag (validator.py)
Return to backend: verdict + confidence + explanation
```

---

## CURRENT SPRINT — HYBRID RETRIEVAL

### Task 1 — SCRUM-257: BM25 Keyword Retrieval (rag/retrieval/bm25_retriever.py)
Build a BM25 keyword search module that:
- Takes the same chunks (list of ChunkMetadata) as input — same format as vector_store.py
- Builds a BM25 index from chunk texts using rank_bm25
- Takes the claim text as query
- Returns top-k chunks with BM25 scores
- Applies the same section priority weights as vector_store.py
- Falls back gracefully if index is empty
- Write unit tests in tests/rag/test_bm25_retriever.py
- Write docs in docs/rag/bm25_retriever.md
- Commit: [RAG] SCRUM-257: implement BM25 keyword retriever

### Task 2 — SCRUM-258: Hybrid Retrieval Merger (rag/retrieval/hybrid_retriever.py)
Build a hybrid retrieval module that:
- Takes output from vector_store.py (dense results) and bm25_retriever.py (keyword results)
- Merges and deduplicates chunks from both
- Applies Reciprocal Rank Fusion (RRF) to combine scores from both sources
- Returns unified ranked list ready for reranking
- Write unit tests in tests/rag/test_hybrid_retriever.py
- Write docs in docs/rag/hybrid_retriever.md
- Commit: [RAG] SCRUM-258: implement hybrid retrieval with RRF merging

### Task 3 — SCRUM-259: FlashRank Neural Reranking (inside hybrid_retriever.py)
Extend hybrid_retriever.py to add FlashRank reranking:
- Takes the merged chunk list from SCRUM-258
- Runs FlashRank to reorder by true semantic relevance
- Returns final top-k chunks in reranked order
- Update unit tests in tests/rag/test_hybrid_retriever.py
- Commit: [RAG] SCRUM-259: add FlashRank neural reranking

### Task 4 — SCRUM-260: Plug hybrid retriever into rag/api.py
Update retrieve_evidence() in rag/api.py:
- Replace the dense-only Step 5 block with the hybrid pipeline
- Import and call hybrid_retriever.py instead of vector_store.py directly
- The API contract (input/output) does NOT change
- Re-run full test suite — all 323 tests must still pass
- Update docs/rag/api.md to confirm hybrid retrieval is now active
- Commit: [RAG] SCRUM-260: plug hybrid retrieval into api.py

---

## CHUNKING RULES (already implemented — do not change)

### Section priority weights
```python
SECTION_WEIGHTS = {
    "results": 1.3,
    "methods": 1.3,
    "experiments": 1.3,
    "discussion": 1.1,
    "conclusion": 1.1,
    "introduction": 1.0,
    "abstract": 1.0,
    "related_work": 0.8,
    "future_work": 0.8,
    "unknown": 1.0,
}
```

### Sections to SKIP entirely
```python
SKIP_SECTIONS = [
    "references", "bibliography", "acknowledgements", "acknowledgments",
    "author contributions", "funding", "conflict of interest",
    "appendix", "supplementary material", "about the authors",
    "copyright", "license"
]
```

---

## CODE STYLE RULES
- Every function must have a docstring
- Every module must have a module-level docstring explaining what it does
- Use type hints on all function signatures
- Use Pydantic models for all input/output data structures
- Keep functions small — one function does one thing
- Add inline comments for non-obvious logic
- No hardcoded values — use constants or config
- Import LLM_TEMPERATURE from rag/prompts/config.py — never hardcode 0

---

## FILE NAMING CONVENTIONS
```
rag/retrieval/
├── embedder.py          ← SCRUM-180 ✅
├── vector_store.py      ← SCRUM-186 ✅ (dense FAISS)
├── bm25_retriever.py    ← SCRUM-257 (build this first)
├── hybrid_retriever.py  ← SCRUM-258 + SCRUM-259 (build after BM25)
└── models.py            ← Pydantic models for retrieval ✅
```

---

## DOCUMENTATION REQUIREMENT
Every new module must have a corresponding entry in `docs/rag/` explaining:
- What the module does
- How to use it (with example)
- Key design decisions and why
This is a course deliverable — documentation is graded.

---

## WORKFLOW RULES

### 1. Plan Before Acting
- For ANY non-trivial task — write a plan first
- Save the plan to `tasks/todo.md` with checkable items
- Check in with Saqer before starting implementation
- If something goes wrong mid-task — STOP and re-plan

### 2. Track Progress
- Mark items complete in `tasks/todo.md` as you go
- Give a high-level summary at each step
- Add a review section to `tasks/todo.md` when done

### 3. Self-Improvement Loop
- After ANY correction from Saqer — update `tasks/lessons.md`
- Write a rule for yourself that prevents the same mistake
- Review `tasks/lessons.md` at the start of each session

### 4. Never Mark a Task Done Without Proving It Works
- Always run tests before saying a task is complete
- Full test suite must stay at 323+ passing after every task

### 5. Autonomous Bug Fixing
- When given a bug — just fix it, do not ask for hand-holding
- Point at the error, find the root cause, resolve it

### 6. Minimal Impact
- Only touch code that is necessary for the current task
- Do not refactor or change things that are not broken

### 7. Demand Elegance
- For non-trivial changes — pause and ask "is there a more elegant way?"
- If a fix feels hacky — implement the clean solution instead

---

## TASK FILES STRUCTURE
```
tasks/
├── todo.md       ← current task plan with checkable items
└── lessons.md    ← mistakes made + rules to prevent them
```
