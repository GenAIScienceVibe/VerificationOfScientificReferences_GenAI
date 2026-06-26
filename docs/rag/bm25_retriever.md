# bm25_retriever.py — SCRUM-257

## What it does

`bm25_retriever.py` is the keyword-search step of the RAG pipeline — the
counterpart to `vector_store.py`'s dense (embedding) search.

Given the same chunks (`list[ChunkMetadata]`) used by `vector_store.py` and
the claim text as a query, it:

1. Tokenizes every chunk's text and builds a temporary in-memory BM25 index
   (`rank_bm25.BM25Okapi`).
2. Tokenizes the claim and scores it against every chunk.
3. Multiplies each raw BM25 score by the same **section priority weight**
   used by `vector_store.py`, so keyword and dense scores are biased the
   same way before `hybrid_retriever.py` merges them.
4. Returns the top-k chunks ranked by weighted score.

The BM25 index is **not persisted** — it is built per request inside
`search()` and discarded when the function returns, matching the
"processing engine, not storage system" rule for this sub-group.

---

## How to use it

```python
from rag.retrieval.bm25_retriever import search
from rag.retrieval.models import Bm25RetrieverInput

result = search(Bm25RetrieverInput(
    chunks=my_chunks,            # list[ChunkMetadata], from chunker.py
    query="Exercise reduces heart disease risk by 35%",
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
| `Bm25RetrieverInput` | `chunks: list[ChunkMetadata]`, `query: str`, `top_k: int = 5` |
| `Bm25RetrieverOutput` | `top_chunks: list[Bm25RetrievedChunk]`, `total_indexed`, `retrieved_k` |
| `Bm25RetrievedChunk` | `chunk: ChunkMetadata`, `raw_score`, `weighted_score`, `rank` |

Note: unlike `VectorStoreInput`, this module takes raw chunks and a plain
query string directly — there is no embedding step in keyword search, so
there is no `EmbedderOutput` to wrap.

---

## Key design decisions

### Why BM25 alongside dense retrieval?

Dense embeddings are good at semantic similarity but can blur exact term
matches — specific numbers, model names, acronyms, or rare technical terms
that a claim quotes verbatim from the source. BM25 catches those exact
matches that embeddings sometimes miss. `hybrid_retriever.py` (SCRUM-258)
combines both signals with Reciprocal Rank Fusion.

### Shared section weights with vector_store.py

`SECTION_WEIGHTS` and `DEFAULT_WEIGHT` are **imported from `vector_store.py`**,
not duplicated. Both retrieval methods must bias toward the same sections
(Results, Methods, Experiments) so that when their results are merged, the
section-priority signal isn't inconsistent between the two score streams.

### Simple tokenisation

Tokenisation lower-cases text and splits on `\w+` (word characters). BM25
only needs token overlap counting, not linguistic understanding, so a
lightweight regex tokenizer is enough — it keeps this module's only new
dependency as `rank_bm25` itself.

### Negative BM25 scores are expected, not a bug

Okapi BM25's IDF term can go negative for a word that appears in *every*
document of a very small corpus (the classic case: 1-2 chunks, both
containing the query term). This is mathematically correct BM25 behaviour,
not a defect — it only shows up with tiny corpora. With realistic chunk
counts per paper (dozens+), IDF stays positive for any term that isn't
a true stopword.

### Graceful empty-index fallback

An empty `chunks` list returns an empty `Bm25RetrieverOutput` with
`total_indexed=0` instead of raising, exactly mirroring
`vector_store.search()`'s empty-chunks behaviour.

---

## Module-level constants

This module has no constants of its own — `SECTION_WEIGHTS` and
`DEFAULT_WEIGHT` are reused directly from `rag/retrieval/vector_store.py` to
keep the two retrieval methods' section bias in sync.
