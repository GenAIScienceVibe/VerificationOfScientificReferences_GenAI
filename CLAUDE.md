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

## REPO STRUCTURE (our folder)
```
rag/
├── ingestion/       ← text cleaning + chunking (SCRUM-178, SCRUM-179)
├── retrieval/       ← embedding + vector store (SCRUM-180, SCRUM-186)
├── prompts/         ← prompt templates (future)
├── verification/    ← LLM verdict (future)
├── evaluation/      ← benchmarking + latency (SCRUM-184, SCRUM-185)
└── README.md
```

---

## GIT RULES
- NEVER push to `main`
- Always work on branch: `rag_dev_zac`
- Commit message format: `[RAG] SCRUM-XXX: short description`
- Example: `[RAG] SCRUM-178: implement text cleaning module`

---

## TECH STACK (our sub-group only)
- Language: Python 3.11+
- Text splitting: langchain-text-splitters (RecursiveCharacterTextSplitter)
- Token counting: tiktoken
- Embedding model: text-embedding-3-small (OpenAI API)
- Vector store: FAISS (faiss-cpu) — runtime only, built per request, discarded after use
- Keyword search: rank_bm25
- Reranking: flashrank
- LLM: Groq API (model: meta-llama/llama-4-scout-17b-16e-instruct)
- Prompt templates: Jinja2
- Output validation: Pydantic
- Config/secrets: python-dotenv (.env file)
NOTE: PostgreSQL / SQLAlchemy are NOT our responsibility — backend owns all storage.

---

## ENVIRONMENT VARIABLES
All secrets go in `.env` file (never commit this file). Use `.env.example` as template.
```
OPENAI_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
DATABASE_URL=postgresql://user:password@localhost:5432/verifai
```

---

## INPUT / OUTPUT CONTRACT WITH BACKEND
The backend calls us through two internal endpoints.

### What we receive (Door 1 — RAG retrieval):
```json
{
  "claim_id": "claim_001",
  "reference_id": "ref_001",
  "claim_text": "Exercise reduces heart disease risk by 35%",
  "citation_text": "(Johnson et al., 2019)",
  "doi": "10.1234/example.2019.001",
  "doi_status": "VALID",
  "source_evidence": {
    "evidence_availability": "ABSTRACT_AVAILABLE",
    "text": "Abstract text of the source paper...",
    "source_url": "https://doi.org/10.1234/example.2019.001"
  }
}
```

### What we return (Door 1):
```json
{
  "claim_id": "claim_001",
  "reference_id": "ref_001",
  "retrieval_status": "SUCCEEDED",
  "top_chunks": [
    {
      "chunk_id": "chunk_001",
      "chunk_text": "participants showed a 28% reduction...",
      "similarity_score": 0.84,
      "evidence_type": "ABSTRACT"
    }
  ],
  "overall_similarity_score": 0.82,
  "retrieval_confidence": 0.81
}
```

### What we receive (Door 2 — LLM verification):
```json
{
  "claim_text": "Exercise reduces heart disease risk by 35%",
  "citation_text": "(Johnson et al., 2019)",
  "doi_status": "VALID",
  "metadata": {
    "title": "Cardiovascular effects of exercise",
    "abstract": "Abstract text..."
  },
  "retrieved_evidence": [
    {
      "chunk_id": "chunk_001",
      "chunk_text": "participants showed a 28% reduction...",
      "similarity_score": 0.84
    }
  ],
  "overall_similarity_score": 0.82
}
```

### What we return (Door 2):
```json
{
  "support_status": "PARTIALLY_SUPPORTED",
  "confidence": 0.72,
  "explanation": "The source reports 28% reduction, not 35% as claimed.",
  "evidence_used": ["chunk_001"],
  "limitations": "Only abstract-level evidence was available.",
  "human_review_required": true
}
```

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

### Door 1 — RAG Retrieval (our job)
```
Receive from backend: claim + DOI + source text + metadata + evidence availability
  ↓
1. Citation preprocessing — strip author names, keep factual statement only
2. Citation type classification — RESULT_COMPARISON / METHOD / BACKGROUND etc.
3. Section-aware chunking (see chunking rules below)
4. Embed source chunks → temporary FAISS index (runtime only, not persisted)
5. Embed the claim → same embedding model
6. Hybrid retrieval — dense (cosine similarity) + BM25 keyword search combined
7. Neural reranking — FlashRank reorders top chunks by true relevance
Return to backend: top chunks + similarity scores + retrieval confidence
Backend stores: chunks and scores in their DB
```

### Door 2 — LLM Verification (our job)
```
Receive from backend: claim + selected chunks + metadata/context
  ↓
8. Prompt engineering — Jinja2 template with claim + chunks + section context, temperature=0
9. LLM verdict — Groq + Llama 4 Scout
Return to backend: verdict + confidence + explanation
Backend stores: verification result
Backend applies: safety rules (missing DOI → NEEDS_HUMAN_REVIEW,
                 low similarity → NEEDS_HUMAN_REVIEW,
                 no evidence → INSUFFICIENT_EVIDENCE,
                 LLM/RAG conflict → NEEDS_HUMAN_REVIEW)
```

---

## CHUNKING RULES (implement exactly as designed)

### Section detection
Detect headings by looking for:
- Lines under 60 characters
- All-caps or title-case text
- Numbered patterns: `1.`, `2.1`, `III.`
- Followed by blank line or indented paragraph

### Section name normalization (map to standard names)
```python
SECTION_MAP = {
    # Methods variations
    "methodology": "methods",
    "materials and methods": "methods",
    "materials & methods": "methods",
    "experimental setup": "methods",
    "experimental methods": "methods",
    "approach": "methods",
    "procedure": "methods",
    "implementation": "methods",
    "system design": "methods",
    # Results variations
    "findings": "results",
    "experimental results": "results",
    "outcomes": "results",
    "evaluation": "results",
    "performance": "results",
    "experiments": "results",
    "experimental evaluation": "results",
    # Discussion variations
    "analysis": "discussion",
    "interpretation": "discussion",
    "implications": "discussion",
    "results and discussion": "discussion",
    # Related work variations
    "literature review": "related_work",
    "background": "related_work",
    "prior work": "related_work",
    "previous work": "related_work",
    "state of the art": "related_work",
    # Conclusion variations
    "conclusions": "conclusion",
    "summary": "conclusion",
    "concluding remarks": "conclusion",
    "conclusions and future work": "conclusion",
    # Introduction variations
    "overview": "introduction",
    "motivation": "introduction",
    "problem statement": "introduction",
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

### Section priority weights for similarity search
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

### Chunk size rules
- Minimum paragraph size: 50 tokens → if smaller, merge with next
- Target chunk size: 512 tokens
- Overlap: 50–75 tokens
- Splitter: RecursiveCharacterTextSplitter with separators: ["\n\n", "\n", ". ", " "]
- Token counter: tiktoken (encoding: cl100k_base)

### Chunk metadata (every chunk must carry this)
```python
{
    "chunk_id": "doi_chunk_003",
    "section": "results",
    "priority": 1.3,
    "chunk_index": 3,
    "paper_doi": "10.1234/...",
    "evidence_type": "FULL_TEXT"  # or ABSTRACT
}
```

### Fallback rule
If no sections detected → apply token window to full text, tag all chunks:
`section: "unknown"`, `priority: 1.0`

---

## CODE STYLE RULES
- Every function must have a docstring
- Every module must have a module-level docstring explaining what it does
- Use type hints on all function signatures
- Use Pydantic models for all input/output data structures
- Keep functions small — one function does one thing
- Add inline comments for non-obvious logic
- No hardcoded values — use constants or config

---

## FILE NAMING CONVENTIONS
```
rag/ingestion/
├── __init__.py
├── cleaner.py         ← SCRUM-178: text cleaning
├── chunker.py         ← SCRUM-179: section-aware chunking
└── models.py          ← Pydantic models for ingestion

rag/retrieval/
├── __init__.py
├── embedder.py        ← SCRUM-180: chunk-to-vector conversion
├── vector_store.py    ← SCRUM-186: FAISS store + metadata
├── bm25_retriever.py  ← BM25 keyword search
├── hybrid_retriever.py← combines dense + BM25 + reranking
└── models.py          ← Pydantic models for retrieval

rag/evaluation/
├── __init__.py
├── benchmark.py       ← SCRUM-184: retrieval accuracy benchmark
└── latency.py         ← SCRUM-185: latency + cost per embedding call
```

---

## TASK ORDER — DO ONE AT A TIME
Work in this exact order. Do not move to the next task until the current one
is complete, tested, and committed.

### Task 1 — SCRUM-178: Text Cleaning (rag/ingestion/cleaner.py)
Build a module that:
- Takes raw source text already extracted by the backend (received in Door 1 as source_evidence.text)
- Removes noise: excessive whitespace, page numbers, headers/footers
- Detects and removes the references/bibliography section
- Returns clean plain text ready for chunking
- Write unit tests in tests/rag/test_cleaner.py
NOTE: We do NOT parse any PDF files. The backend extracts text from PDFs and sends it to us as plain text.

### Task 2 — SCRUM-179: Chunking (rag/ingestion/chunker.py)
Build a module that:
- Detects sections using heading patterns
- Normalizes section names using SECTION_MAP
- Skips sections in SKIP_SECTIONS
- Splits paragraphs within each section
- Applies token window when paragraph exceeds 512 tokens
- Tags every chunk with section + priority + metadata
- Falls back to blind chunking if no sections detected
- Write unit tests in tests/rag/test_chunker.py

### Task 3 — SCRUM-180: Embedding (rag/retrieval/embedder.py)
Build a module that:
- Takes a list of chunks (with metadata)
- Calls OpenAI text-embedding-3-small API
- Returns list of vectors paired with their chunk metadata
- Handles API errors and rate limits gracefully
- Write unit tests with a mock API response

### Task 4 — SCRUM-186: Vector Store (rag/retrieval/vector_store.py)
Build a module that:
- Builds a temporary FAISS index at runtime from embedded chunks
- FAISS index is NOT persisted to disk — it is built per request and discarded after use
- Performs cosine similarity search, returns top-k chunks with metadata
- Applies section priority weights to similarity scores
- Write unit tests in tests/rag/test_vector_store.py
NOTE: We do NOT own any persistent storage. The backend stores all results.

### Task 5 — SCRUM-184: Retrieval Benchmark (rag/evaluation/benchmark.py)
Build a script that:
- Takes a small set of test papers with known claim-evidence pairs
- Runs our retrieval pipeline on each
- Measures: did the correct chunk appear in top-3 results?
- Reports accuracy as a percentage
- Saves results to data/evaluation/benchmark_results.json

### Task 6 — SCRUM-185: Latency & Cost (rag/evaluation/latency.py)
Build a script that:
- Runs the embedding pipeline on 10 test chunks
- Measures time per embedding call (ms)
- Calculates cost per call (OpenAI pricing: $0.02 per 1M tokens)
- Reports average latency and estimated cost per paper
- Saves results to data/evaluation/latency_results.json

---

## IMPORTANT NOTES
- Always use environment variables for API keys — never hardcode
- Always set temperature=0 on all LLM calls
- Always validate LLM output with Pydantic before returning
- The FAISS index is temporary per paper — built at runtime, used for search, then discarded. We do NOT persist it to disk.
- For now we use abstract only if full text is unavailable — log a warning when this happens
- If DOI status is INVALID or UNRESOLVABLE — return INSUFFICIENT_EVIDENCE immediately, skip pipeline
- When confidence < 0.5 OR verdict = PARTIALLY_SUPPORTED → set human_review_required = True

---

## DOCUMENTATION REQUIREMENT
Every module must have a corresponding entry in `docs/rag/` explaining:
- What the module does
- How to use it (with example)
- Key design decisions and why
This is a course deliverable — documentation is graded.

---

## WORKFLOW RULES

### 1. Plan Before Acting
- For ANY non-trivial task (3+ steps or architectural decisions) — write a plan first
- Save the plan to `tasks/todo.md` with checkable items
- Check in with Saqer before starting implementation
- If something goes wrong mid-task — STOP and re-plan, do not keep pushing

### 2. Track Progress
- Mark items complete in `tasks/todo.md` as you go
- Give a high-level summary at each step
- Add a review section to `tasks/todo.md` when done

### 3. Self-Improvement Loop
- After ANY correction from Saqer — update `tasks/lessons.md` with what went wrong
- Write a rule for yourself that prevents the same mistake
- Review `tasks/lessons.md` at the start of each session

### 4. Never Mark a Task Done Without Proving It Works
- Always run tests before saying a task is complete
- Check logs and verify behavior
- Ask yourself: "Would a senior developer approve this?"

### 5. Autonomous Bug Fixing
- When given a bug — just fix it, do not ask for hand-holding
- Point at the error, find the root cause, resolve it
- Do not ask Saqer to explain how to fix it — figure it out

### 6. Minimal Impact
- Only touch code that is necessary for the current task
- Do not refactor or change things that are not broken
- Every change should be as small and focused as possible

### 7. Demand Elegance
- For non-trivial changes — pause and ask "is there a more elegant way?"
- If a fix feels hacky — implement the clean solution instead
- Skip this for simple obvious fixes — do not over-engineer

---

## TASK FILES STRUCTURE
```
tasks/
├── todo.md       ← current task plan with checkable items
└── lessons.md    ← mistakes made + rules to prevent them
```
