# embedder.py — Chunk Embedding Module

**SCRUM-180 | rag/retrieval/embedder.py**

---

## What it does

`embedder.py` takes the list of text chunks produced by `chunker.py` and
converts each chunk's text into a **dense vector** (a list of 1536 numbers).
This vector is a mathematical representation of the chunk's meaning — two
chunks about the same topic will have vectors that point in a similar direction
in 1536-dimensional space.

These vectors are what goes into the FAISS index in the next step. Without
them, we can only do keyword search; with them, we can do **semantic search**
("find chunks that are about the same idea as the claim, even if they use
different words").

---

## How to use it

```python
from dotenv import load_dotenv
load_dotenv()  # loads OPENAI_API_KEY from .env

from rag.retrieval.embedder import embed_chunks
from rag.retrieval.models import EmbedderInput

# chunks come from chunk_text() in chunker.py
input_data = EmbedderInput(
    chunks=chunker_output.chunks,
    doi="10.1234/example.2019.001",
)

result = embed_chunks(input_data)

print(f"Embedded {result.total_embedded} chunks")
print(f"Model: {result.embedding_model}")
print(f"Vector dimensions: {result.embedding_dimensions}")

for ec in result.embedded_chunks:
    print(ec.chunk.chunk_id, len(ec.embedding))  # e.g. "...chunk_000  1536"
```

---

## How it works

### The embedding model

We use **`text-embedding-3-small`** from OpenAI. It produces 1536-dimensional
vectors and is optimised for retrieval tasks (finding documents relevant to a
query). It uses the same `cl100k_base` tokeniser as our chunker, so our
512-token chunk limit maps exactly to the model's input window.

### Batching

The API accepts up to 2048 texts per call, but we batch at **100 chunks** per
request. This keeps individual payloads small and makes retry logic simple —
if a batch fails, only 100 chunks need to be retried, not the whole paper.

```
chunks: [0..99]   → API call 1
chunks: [100..199] → API call 2
...
```

### Exponential backoff on rate limits

OpenAI enforces rate limits (requests per minute, tokens per minute). When a
`429 RateLimitError` is received, we do not give up immediately — we wait and
retry:

| Attempt | Wait before retry |
|---------|-------------------|
| 1       | 2 seconds         |
| 2       | 4 seconds         |
| 3       | 8 seconds         |
| 4+      | give up, re-raise |

This pattern is called **exponential backoff** and is the standard way to
handle metered APIs. Any other error (`APIError`) is not retried — it means
something is wrong (bad key, bad request) that waiting won't fix.

### Lazy client construction

The OpenAI client is built **inside** `embed_chunks()` when it is first called,
not at module import time. This means:
- Tests can import the module without needing `OPENAI_API_KEY` to be set.
- If the key is missing, the error is raised with a clear message exactly at
  the point where the network call would have happened.

---

## Data models

```
EmbedderInput
├── chunks: list[ChunkMetadata]   ← from chunker
└── doi: str

EmbedderOutput
├── doi: str
├── embedded_chunks: list[EmbeddedChunk]
│     └── EmbeddedChunk
│           ├── chunk: ChunkMetadata   ← original chunk, unchanged
│           └── embedding: list[float] ← 1536 floats from the API
├── total_embedded: int
├── embedding_model: str           ← "text-embedding-3-small"
└── embedding_dimensions: int      ← 1536
```

---

## Key design decisions

### Why not persist embeddings?
Per the project spec, we are a **processing engine, not a storage system**.
The FAISS index is built per-request and discarded. The backend stores
whatever it needs. We do not cache or save vectors to disk.

### Why `text-embedding-3-small` and not `large`?
`text-embedding-3-small` (1536 dims) gives excellent retrieval quality for
scientific text at roughly 5× lower cost than `text-embedding-3-large` (3072
dims). The performance difference on claim-evidence matching tasks is small
enough that `small` is the right default. If evaluations show recall is too
low, we can upgrade.

### Why mock the API in tests instead of calling it?
Real API calls in unit tests are slow (network latency), flaky (require a
key and internet), and cost money. A mock replaces the HTTP call with an
in-memory function that returns a pre-set response, making tests instant,
deterministic, and free. The mock is only needed in tests — the production
code calls the real API normally.

---

## Running the tests

```bash
python -m pytest tests/rag/test_embedder.py -v
```

16 tests. No API key required — all network calls are mocked.
