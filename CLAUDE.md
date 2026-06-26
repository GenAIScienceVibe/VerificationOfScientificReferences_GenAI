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

### Branch: rag_dev_zac ✅ COMPLETE
All 13 tasks complete. 323/323 tests passing.
Dense-only retrieval pipeline (FAISS cosine similarity).

### Branch: rag_dev_zac_hybrid ✅ COMPLETE (ACTIVE — current work)
All 4 hybrid retrieval tasks complete. 350/350 tests passing.
Full pipeline: dense FAISS + BM25 + RRF merge + FlashRank reranking.

### What is built and working (rag_dev_zac_hybrid):
- rag/ingestion/cleaner.py           ← SCRUM-178 ✅
- rag/ingestion/chunker.py           ← SCRUM-179 ✅
- rag/retrieval/embedder.py          ← SCRUM-180 ✅
- rag/retrieval/vector_store.py      ← SCRUM-186 ✅ (dense FAISS)
- rag/retrieval/bm25_retriever.py    ← SCRUM-257 ✅ (BM25 keyword search)
- rag/retrieval/hybrid_retriever.py  ← SCRUM-258 + SCRUM-259 ✅ (RRF + FlashRank)
- rag/evaluation/benchmark.py        ← SCRUM-184 ✅
- rag/evaluation/latency.py          ← SCRUM-185 ✅
- rag/prompts/config.py              ← SCRUM-254 ✅ (LLM_TEMPERATURE=0)
- rag/prompts/classifier.py          ← SCRUM-252 ✅
- rag/prompts/verifier.py            ← SCRUM-193/195/196 ✅
- rag/prompts/templates/verify.j2    ← SCRUM-195 ✅
- rag/verification/models.py         ← SCRUM-194 ✅
- rag/verification/validator.py      ← SCRUM-253 ✅
- rag/api.py                         ← Integration handoff layer ✅

---

## CURRENT BRANCH
You are working on branch: `rag_dev_zac_hybrid`
NEVER push to `main`. NEVER push to `rag_dev_zac` from this branch.

---

## ⚠️ CURRENT SPRINT — BACKEND INTEGRATION FIXES (PRIORITY)
We must fix integration defects reported by the backend team.

The backend team did a full integration audit of rag/api.py and found bugs.
All fixes below are in rag/api.py only — no pipeline logic changes.
All fixes are safe and do not break the API contract or pipeline flow.

### P1 — BLOCKING (fix first, in this order)

**SCRUM-262 — Normalize all scores to 0-1**
Problem: Section priority weights (e.g. 1.3× for Results) push scores above 1.0.
Backend validators reject any score above 1.0.
Fix: Normalize similarity_score, overall_similarity_score, and retrieval_confidence
to 0-1 range before returning from retrieve_evidence().
Note: SIMILARITY_THRESHOLD = 0.5 check in Door 2 still works after normalization.

**SCRUM-263 — INSUFFICIENT_EVIDENCE must set human_review_required=True**
Problem: When DOI is INVALID or UNRESOLVABLE, we return human_review_required=False.
Backend safety policy requires human_review_required=True whenever a DOI
cannot be verified — a human must always review unverifiable citations.
Fix: In _insufficient_evidence() helper in api.py, change human_review_required=False
to human_review_required=True.

### P2 — IMPORTANT (fix after P1, before live demo)

**SCRUM-264 — Add per-DOI embedding cache**
Problem: If one paper has 10 claims all citing the same reference, we re-embed
the same source text 10 times — slow and costly.
Fix: Add an in-memory cache keyed by DOI inside retrieve_evidence().
Cache must be: in-memory only, per document run, never persisted.
Do NOT store anything — backend owns all storage.

### After all fixes are done:
- Run full test suite — must stay at 350+ passing
- Commit all fixes as: [RAG] fix: resolve backend integration defects (SCRUM-262/263/264)

### Do NOT start next task until I explicitly say so.

---

## REPO STRUCTURE (our folder)
```
rag/
├── ingestion/         ← text cleaning + chunking
├── retrieval/         ← embedding + vector store + BM25 + hybrid
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
DO NOT change the API contract field names or types — only fix values inside fields.

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
6. BM25 keyword retrieval (bm25_retriever.py)
7. Hybrid merge — combine dense + BM25 with RRF (hybrid_retriever.py)
8. FlashRank neural reranking (hybrid_retriever.py)
9. Normalize all scores to 0-1 ← INTEGRATION FIX (SCRUM-262)
Return to backend: top chunks + scores + retrieval confidence (all 0-1)
```

### Door 2 — LLM Verification
```
Receive from backend: claim + selected chunks + metadata
  ↓
1. Citation type classification (classifier.py)
2. Jinja2 prompt with chain-of-thought (verify.j2)
3. LLM call via OpenRouter, temperature=0 (verifier.py)
4. Pydantic validation + human review flag (validator.py)
5. If INSUFFICIENT_EVIDENCE → human_review_required=True ← INTEGRATION FIX (SCRUM-263)
Return to backend: verdict + confidence + explanation
```

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

### 2. Do Not Start Next Task Automatically
- After completing a task — stop and wait for Saqer's instruction
- Never move to the next task without explicit approval

### 3. Track Progress
- Mark items complete in `tasks/todo.md` as you go
- Give a high-level summary at each step
- Add a review section to `tasks/todo.md` when done

### 4. Self-Improvement Loop
- After ANY correction from Saqer — update `tasks/lessons.md`
- Write a rule for yourself that prevents the same mistake
- Review `tasks/lessons.md` at the start of each session

### 5. Never Mark a Task Done Without Proving It Works
- Always run tests before saying a task is complete
- Full test suite must stay at 350+ passing after every task

### 6. Autonomous Bug Fixing
- When given a bug — just fix it, do not ask for hand-holding
- Point at the error, find the root cause, resolve it

### 7. Minimal Impact
- Only touch code that is necessary for the current task
- Do not refactor or change things that are not broken

### 8. Demand Elegance
- For non-trivial changes — pause and ask "is there a more elegant way?"
- If a fix feels hacky — implement the clean solution instead

---

## TASK FILES STRUCTURE
```
tasks/
├── todo.md       ← current task plan with checkable items
└── lessons.md    ← mistakes made + rules to prevent them
```
