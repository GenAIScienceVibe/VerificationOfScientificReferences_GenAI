# hybrid_retriever.py — SCRUM-258 + SCRUM-259

## What it does

`hybrid_retriever.py` merges the two retrieval signals — dense (`vector_store.py`)
and keyword (`bm25_retriever.py`) — into a single unified ranking using
**Reciprocal Rank Fusion (RRF)**, then reorders the top candidates by true
semantic relevance using **FlashRank neural reranking**.

Given:
- the `VectorStoreOutput` from a dense FAISS search,
- the `Bm25RetrieverOutput` from a BM25 keyword search, and
- the claim text itself

for the same claim, it:

1. Deduplicates chunks by `chunk_id` (a chunk may appear in one list, the
   other, or both).
2. For each unique chunk, sums its RRF contribution from each source it
   appeared in: `1 / (RRF_K + rank)`.
3. Sorts all unique chunks by combined `rrf_score` descending.
4. Takes an oversampled candidate pool (`top_k × RERANK_OVERSAMPLE_FACTOR`)
   from that RRF ranking and reranks just those candidates against the
   claim with FlashRank — a small cross-encoder model that reads the actual
   claim and chunk text, not just rank positions.
5. Returns the final top-k, ordered by FlashRank's `rerank_score` (or by
   RRF order if FlashRank reranking fails for any reason).

---

## How to use it

```python
from rag.retrieval.vector_store import search as dense_search
from rag.retrieval.bm25_retriever import search as bm25_search
from rag.retrieval.hybrid_retriever import merge
from rag.retrieval.models import HybridRetrieverInput, VectorStoreInput, Bm25RetrieverInput

claim_text = "Exercise reduces heart disease risk by 35%"

dense_results = dense_search(VectorStoreInput(embedder_output=..., query_embedding=..., top_k=10))
bm25_results = bm25_search(Bm25RetrieverInput(chunks=my_chunks, query=claim_text, top_k=10))

result = merge(HybridRetrieverInput(
    dense_results=dense_results,
    bm25_results=bm25_results,
    claim=claim_text,
    top_k=5,
))

for hc in result.top_chunks:
    print(f"Rank {hc.rank}  rerank={hc.rerank_score}  rrf={hc.rrf_score:.5f}  "
          f"dense_rank={hc.dense_rank}  bm25_rank={hc.bm25_rank}")
    print(hc.chunk.chunk_text[:120])
    print()
```

### Input / output types

| Type | Fields |
|---|---|
| `HybridRetrieverInput` | `dense_results: VectorStoreOutput`, `bm25_results: Bm25RetrieverOutput`, `claim: str`, `top_k: int = 5` |
| `HybridRetrieverOutput` | `top_chunks: list[HybridRetrievedChunk]`, `total_unique` |
| `HybridRetrievedChunk` | `chunk: ChunkMetadata`, `rrf_score`, `dense_rank: int \| None`, `bm25_rank: int \| None`, `rerank_score: float \| None`, `rank` |

`dense_rank` / `bm25_rank` are `None` when the chunk wasn't returned by that
retriever at all — useful for debugging why a chunk surfaced (keyword match
only, semantic match only, or both). `rerank_score` is `None` if reranking
was skipped or failed — the chunk's position then reflects RRF order only.

---

## Key design decisions

### Why rank-based fusion instead of combining raw scores?

Dense cosine similarity (0–1) and BM25 scores (unbounded, can be negative
for tiny corpora) live on incompatible scales — you cannot average or sum
them directly without one dominating arbitrarily. RRF sidesteps this
entirely by only looking at each chunk's **rank position** in each list,
which is always comparable regardless of the underlying scoring scheme.

### RRF_K = 60

This is the standard smoothing constant from the original RRF paper
(Cormack, Clarke & Buettcher, 2009) and the de facto default used across
hybrid search implementations. A larger `RRF_K` flattens the curve so the
gap between rank 1 and rank 2 matters less; this prevents a chunk that is
merely rank 1 in one retriever from automatically beating a chunk that is
rank 2–3 in *both* retrievers, which is usually the stronger evidence.

### No penalty for missing from one source

A chunk found by only one retriever still gets that retriever's RRF
contribution — it isn't penalised for "missing" from the other list. Being
found by either a strong semantic match or a strong keyword match is
useful signal on its own; double-coverage is a bonus, not a requirement.

### Deduplication by chunk_id

Both `vector_store.py` and `bm25_retriever.py` operate over the exact same
`ChunkMetadata` objects (same `chunk_id` scheme from `chunker.py`), so
merging by `chunk_id` is exact — no fuzzy text matching needed.

### Why rerank at all, after RRF already produced a ranking?

RRF only ever sees rank *positions* — it has no idea whether a chunk's text
actually answers the claim, only that it scored well on cosine similarity
or keyword overlap. FlashRank's cross-encoder reads the claim and chunk
text together and scores their true semantic relevance, which can reorder
results RRF got wrong (e.g. a chunk that matched keywords incidentally but
isn't actually relevant).

### Reranking only the oversampled pool, not every unique chunk

`RERANK_OVERSAMPLE_FACTOR = 3` means we only ever rerank `top_k × 3`
candidates — the same oversample-then-rerank shape `vector_store.py` uses
for section weighting. Running the neural model over every retrieved chunk
would add latency for no benefit, since RRF has already pushed clearly
irrelevant chunks far down the list.

### Lazy ranker, never built at import time

`_build_ranker()` constructs the `Ranker` only when `merge()` actually
needs to rerank, mirroring the lazy-client pattern in
`embedder.py`/`classifier.py`. Importing `hybrid_retriever.py` never
triggers a model download — only calling `merge()` with real reranking
enabled does.

### Reranking failure never breaks the pipeline

If FlashRank raises for any reason (model unavailable, malformed input),
`merge()` catches the exception, logs a warning, and returns the RRF-only
ordering with `rerank_score=None` on every chunk. The hybrid retriever
never raises just because the reranking step failed.

---

## Module-level constants

| Constant | Value | Purpose |
|---|---|---|
| `RRF_K` | `60` | Smoothing constant in the RRF formula `1 / (RRF_K + rank)` |
| `RERANK_MODEL` | `"ms-marco-TinyBERT-L-2-v2"` | Small, fast default FlashRank cross-encoder model |
| `RERANK_OVERSAMPLE_FACTOR` | `3` | How many × top_k candidates from the RRF ranking get reranked |
