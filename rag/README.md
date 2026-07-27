
# verifAi — RAG Pipeline



---

## Overview

The RAG (Retrieval-Augmented Generation) pipeline is the core verification engine of verifAi. It receives a scientific claim, a DOI, and the full source paper text, and returns a structured verdict on whether the claim is actually supported by the cited source.

The pipeline is a **processing engine only** — it receives, processes, and returns. All storage is owned by the backend team.

---

## What It Does

Given a claim like:

> *"VAEs enable efficient generation of new samples through a latent space representation."*

...and the cited paper's full text, the pipeline returns:

```json
{
  "support_status": "PARTIALLY_SUPPORTED",
  "confidence": 0.85,
  "human_review_required": false,
  "evidence_used": ["chunk_003", "chunk_007"],
  "explanation": "The source confirms the VAE architecture and latent space, but does not explicitly state that generation is efficient."
}
```

---

## Pipeline Architecture

```
Claim + DOI + Source Paper Text
            ↓
    ┌───────────────────┐
    │   DOOR 1: RAG     │  retrieve_evidence()
    │   RETRIEVAL       │
    └───────────────────┘
         ↓
1. Text Cleaning         (cleaner.py)       — removes noise, strips references section
2. Section-Aware Chunking (chunker.py)      — splits paper, weights by section importance
3. Embedding             (embedder.py)      — text-embedding-3-small via OpenRouter
4. Dense Retrieval       (vector_store.py)  — FAISS cosine similarity search
5. BM25 Retrieval        (bm25_retriever.py)— keyword search
6. RRF Merge             (hybrid_retriever.py) — rank fusion, scale-independent
7. FlashRank Reranking   (hybrid_retriever.py) — neural reranker (TinyBERT-based)
8. Score Normalization   (api.py)           — all scores normalized to 0–1
         ↓
    Top chunks + scores returned to backend
         ↓
    ┌───────────────────┐
    │   DOOR 2: LLM     │  verify_claim()
    │   VERIFICATION    │
    └───────────────────┘
         ↓
1. Citation Type Classification (classifier.py) — 6 types (Background, Method, etc.)
2. Jinja2 Prompt Generation     (verify.j2)     — chain-of-thought + few-shot examples
3. LLM Call                     (verifier.py)   — llama-4-scout via Groq, temperature=0
4. Output Validation            (validator.py)  — Pydantic schema + JSON extraction
         ↓
    Verdict + confidence + explanation returned to backend
```

---

## Verdict Labels

| Verdict | Meaning |
|---|---|
| `SUPPORTED` | Claim is fully backed by the source |
| `PARTIALLY_SUPPORTED` | Core claim is in the source, but adds unsupported framing |
| `NOT_SUPPORTED` | Claim contradicts or is absent from the source |
| `INSUFFICIENT_EVIDENCE` | Not enough evidence retrieved to decide |
| `NEEDS_HUMAN_REVIEW` | Internally used; always mapped to `INSUFFICIENT_EVIDENCE` at the API layer |

> **Note:** `NEEDS_HUMAN_REVIEW` never reaches the backend. It is always returned as `INSUFFICIENT_EVIDENCE` with `human_review_required: true`.

---

## Section Priority Weights

Results, Methods, and Experiments sections are weighted higher during retrieval:

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

---

## API — Two Public Functions

The backend imports directly from `rag/api.py`. No HTTP service, no Docker, no URL.

### `retrieve_evidence(request: RetrieveEvidenceRequest) → RetrieveEvidenceResponse`

**Input:**
```json
{
  "claim_text": "string",
  "doi": "string",
  "source_text": "string"
}
```

**Output:**
```json
{
  "retrieval_status": "SUCCEEDED | FAILED",
  "chunks": [...],
  "overall_similarity_score": 0.85,
  "retrieval_confidence": 0.9,
  "low_confidence": false
}
```

---

### `verify_claim(request: VerifyClaimRequest) → VerifyClaimResponse`

**Input:**
```json
{
  "claim_text": "string",
  "doi": "string",
  "chunks": [...],
  "citation_type": "string"
}
```

**Output:**
```json
{
  "support_status": "SUPPORTED | PARTIALLY_SUPPORTED | NOT_SUPPORTED | INSUFFICIENT_EVIDENCE",
  "confidence": 0.85,
  "human_review_required": false,
  "evidence_used": ["chunk_003", "chunk_007"],
  "explanation": "string"
}
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

```env
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
GROQ_API_KEY=your_groq_key_here
GROQ_BASE_URL=https://api.groq.com/openai/v1
```

> **Note:** OpenRouter is used for embeddings (`text-embedding-3-small`). Groq is used for the LLM (`meta-llama/llama-4-scout-17b-16e-instruct`). Groq was chosen after testing confirmed OpenRouter's DeepInfra routing silently drops responses for this model on large prompts.

### 3. Run tests

```bash
pytest tests/rag/ -v
```

All 356 tests should pass.

---

## File Structure

```
rag/
├── api.py                          ← two public functions for backend
├── ingestion/
│   ├── cleaner.py                  ← strips noise, removes references section
│   ├── chunker.py                  ← section-aware chunking with priority weights
│   └── models.py
├── retrieval/
│   ├── embedder.py                 ← embeds chunks via text-embedding-3-small
│   ├── vector_store.py             ← FAISS cosine search + section weighting
│   ├── bm25_retriever.py           ← BM25 keyword search
│   ├── hybrid_retriever.py         ← RRF merge + FlashRank reranking
│   └── models.py
├── prompts/
│   ├── config.py                   ← LLM_TEMPERATURE=0, model constants
│   ├── classifier.py               ← citation type classifier (6 types)
│   ├── verifier.py                 ← LLM call + retry logic
│   └── templates/
│       └── verify.j2               ← chain-of-thought prompt + 10 few-shot examples
├── verification/
│   ├── models.py                   ← Pydantic output schema (5 verdicts)
│   └── validator.py                ← JSON extraction + schema validation
└── evaluation/
    ├── benchmark.py                ← Hit@3 retrieval accuracy benchmark
    └── latency.py                  ← latency + cost measurement
```

---

## Benchmark Results

Evaluated on `benchmark_dataset_v4.json` — 16 real arXiv papers, all 6 citation types, all 5 verdict types.

| Pipeline | Accuracy |
|---|---|
| Dense-only baseline (`rag_dev_zac`) | 9/16 = 56.2% |
| Hybrid pipeline (`rag_dev_zac_hybrid`) | 10/16 = 62.5% |

**Per-verdict accuracy (hybrid):**

| Verdict | Accuracy |
|---|---|
| NOT_SUPPORTED | 83% |
| INSUFFICIENT_EVIDENCE | 67% |
| SUPPORTED | 50% |
| PARTIALLY_SUPPORTED | 40% |

---

## Key Design Decisions

- **FAISS is runtime-only** — built per request, discarded after use. Backend owns all storage.
- **Temperature = 0** — deterministic, reproducible verdicts. Shared constant in `config.py`.
- **RRF over score averaging** — dense and BM25 scores are on different scales; RRF uses rank positions instead.
- **Retry logic in verifier.py** — up to 3 attempts if the LLM API returns null content (provider-routing issue on OpenRouter/DeepInfra confirmed via testing).
- **Gibberish defense in api.py** — content quality gate rejects fake/garbage paper text before it reaches the LLM.
- **NEEDS_HUMAN_REVIEW mapped at API layer** — never surfaces to backend; always returned as `INSUFFICIENT_EVIDENCE` with `human_review_required: true`.

---

## Future Improvements

- **SkillOpt** — automated prompt optimization for `verify.j2` instead of manual tuning
- **NLI-based verdict classification** — replace the generative LLM for SUPPORTED/PARTIALLY/NOT_SUPPORTED with a fine-tuned RoBERTa model (as used by SemanticCite), keeping the LLM only for INSUFFICIENT_EVIDENCE and NEEDS_HUMAN_REVIEW

---

## Tech Stack

| Component | Library |
|---|---|
| Text splitting | `langchain-text-splitters` |
| Token counting | `tiktoken` |
| Embedding model | `text-embedding-3-small` (OpenRouter) |
| Vector store | `faiss-cpu` |
| Keyword search | `rank_bm25` |
| Reranking | `flashrank` |
| LLM | `meta-llama/llama-4-scout-17b-16e-instruct` (Groq) |
| Prompt templates | `Jinja2` |
| Output validation | `Pydantic` |
| Config/secrets | `python-dotenv` |
