# vector_store.py — SCRUM-186

## What it does

`vector_store.py` is the dense-retrieval step of the RAG pipeline.

Given a set of embedded source-paper chunks (output of `embedder.py`) and an
embedded claim query, it:

1. Builds a temporary in-memory FAISS index from the chunk vectors.
2. Searches the index to find candidates by cosine similarity.
3. Multiplies each raw cosine score by a **section priority weight** so that
   evidence-rich sections (Results, Methods) rank higher than background
   sections (Related Work, Future Work).
4. Returns the top-k chunks ranked by weighted score.

The FAISS index is **not persisted** — it is built per request inside `search()`
and garbage-collected when the function returns.  We own no storage; the backend
stores the results we return.

---

## How to use it

```python
from rag.retrieval.embedder import embed_chunks
from rag.retrieval.vector_store import search
from rag.retrieval.models import EmbedderInput, VectorStoreInput

# Step 1 — embed the source-paper chunks
embedder_output = embed_chunks(EmbedderInput(chunks=my_chunks, doi="10.1234/paper"))

# Step 2 — embed the claim (same model, same API call pattern)
claim_vector = embed_single_text("Exercise reduces heart disease risk by 35%")

# Step 3 — search the vector store
result = search(VectorStoreInput(
    embedder_output=embedder_output,   # direct handoff — no conversion needed
    query_embedding=claim_vector,
    top_k=5,
))

for rc in result.top_chunks:
    print(f"Rank {rc.rank}  weighted={rc.weighted_score:.3f}  "
          f"raw={rc.raw_score:.3f}  section={rc.chunk.section}")
    print(rc.chunk.chunk_text[:120])
    print()
```

### Input / output types

| Type | Fields |
|---|---|
| `VectorStoreInput` | `embedder_output: EmbedderOutput`, `query_embedding: list[float]`, `top_k: int = 5` |
| `VectorStoreOutput` | `doi`, `top_chunks: list[RetrievedChunk]`, `total_indexed`, `retrieved_k` |
| `RetrievedChunk` | `chunk: ChunkMetadata`, `raw_score`, `weighted_score`, `rank` |

---

## Key design decisions

### Cosine similarity via IndexFlatIP + L2 normalisation

FAISS's `IndexFlatIP` computes **exact inner products** (dot products).  
If every vector is first L2-normalised to unit length, then:

```
dot(u, v) = |u| × |v| × cos(θ) = 1 × 1 × cos(θ) = cosine similarity
```

This approach is:
- **Exact** — no approximation, unlike HNSW or IVF indices.
- **Simple** — no training step, no parameter tuning.
- **Correct for our use case** — we have at most a few hundred chunks per
  paper, so brute-force exact search is fast enough.

### Oversample then re-rank

We first fetch `top_k × OVERSAMPLE_FACTOR` (default: `top_k × 3`) candidates
from FAISS by raw cosine score.  After applying section weights we take the
final top-k from this larger pool.

Why?  Consider:

| Chunk | Section | Weight | Raw cosine | Weighted |
|---|---|---|---|---|
| A | results | 1.3 | 0.70 | **0.91** |
| B | related_work | 0.8 | 0.85 | 0.68 |

Chunk A would not be in the strict top-1 by raw cosine, but it *should* win
after weighting.  Oversampling ensures it is in the candidate pool.

### Section priority weights

Defined in `SECTION_WEIGHTS` (matches CLAUDE.md):

| Section | Weight |
|---|---|
| results / methods / experiments | 1.3 |
| discussion / conclusion | 1.1 |
| introduction / abstract / unknown | 1.0 |
| related_work / future_work | 0.8 |

Any section name not in the map gets `DEFAULT_WEIGHT = 1.0`.

### Clean pipeline handoff

`VectorStoreInput` wraps `EmbedderOutput` directly.  The caller passes the
output of `embed_chunks()` straight in without any intermediate conversion:

```python
result = search(VectorStoreInput(embedder_output=embed_chunks(...), ...))
```

---

## Module-level constants

| Constant | Value | Purpose |
|---|---|---|
| `SECTION_WEIGHTS` | dict | Priority multipliers per section name |
| `DEFAULT_WEIGHT` | `1.0` | Fallback for unknown sections |
| `OVERSAMPLE_FACTOR` | `3` | How many × top_k to fetch from FAISS before re-ranking |
