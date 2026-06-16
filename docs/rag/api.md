# api.py — integration handoff layer (for the backend team)

## What it does

`rag/api.py` is the only file the backend needs to import from our
sub-group. It exposes two plain Python functions — no HTTP, no FastAPI
routes on our side — that wrap our whole pipeline behind the exact JSON
shapes documented in `CLAUDE.md`:

| Function | Wraps | CLAUDE.md section |
|---|---|---|
| `retrieve_evidence()` | cleaner → chunker → embedder → vector store | "Door 1 — RAG Retrieval" |
| `verify_claim()` | citation classifier → prompt/LLM call → output validator | "Door 2 — LLM Verification" |

Call them directly from your FastAPI route handlers; everything in
between is our responsibility.

---

## How to use it

```python
from rag.api import (
    retrieve_evidence, verify_claim,
    RetrieveEvidenceRequest, VerifyClaimRequest,
)

# Door 1
result = retrieve_evidence(RetrieveEvidenceRequest(**door1_json_from_frontend))
db.save_retrieval(result.model_dump())

# Door 2 — feed it the chunks you stored from Door 1
result = verify_claim(VerifyClaimRequest(**door2_json_you_built))
db.save_verification(result.model_dump())
```

Both functions take a Pydantic model and return a Pydantic model. Call
`.model_dump()` (or `.model_dump_json()`) on the result to get a plain
dict/JSON string for your API response or DB write. FastAPI will also
accept/return these models directly as route type hints if you prefer.

---

## `retrieve_evidence()`

### Input — `RetrieveEvidenceRequest`

Mirrors CLAUDE.md's Door 1 input exactly:

| Field | Type | Notes |
|---|---|---|
| `claim_id` | `str` | echoed back unchanged |
| `reference_id` | `str` | echoed back unchanged |
| `claim_text` | `str` | the claim sentence |
| `citation_text` | `str` | raw in-text citation, e.g. `(Johnson et al., 2019)` |
| `doi` | `str` | |
| `doi_status` | `"VALID" \| "INVALID" \| "UNRESOLVABLE"` | |
| `source_evidence` | `{evidence_availability, text, source_url}` | `evidence_availability` is one of `FULL_TEXT_AVAILABLE`, `ABSTRACT_AVAILABLE`, `UNAVAILABLE` |

### Output — `RetrieveEvidenceResponse`

| Field | Type | Notes |
|---|---|---|
| `claim_id`, `reference_id` | `str` | echoed back |
| `retrieval_status` | `"SUCCEEDED" \| "FAILED"` | see edge cases below |
| `top_chunks` | list of `{chunk_id, chunk_text, similarity_score, evidence_type}` | up to 5 chunks, best first |
| `overall_similarity_score` | `float` | the single best chunk's score |
| `retrieval_confidence` | `float` | average score across all returned chunks |

### Edge cases

- `doi_status` is `INVALID` or `UNRESOLVABLE` → `retrieval_status: "FAILED"` immediately, nothing else runs.
- Cleaning/chunking yields zero chunks (e.g. empty source text) → `"FAILED"`.
- Anything in the pipeline throws (missing API key, a transient OpenRouter error, etc.) → caught and logged, response is `"FAILED"`. **We never raise an exception out of this function.**

### Known limitation: dense retrieval only

CLAUDE.md describes Door 1 retrieval as hybrid (dense FAISS search + BM25
keyword search, reranked by FlashRank). Only the dense FAISS step
(`rag/retrieval/vector_store.py`) exists today — the BM25 and reranking
modules haven't been built yet. `retrieve_evidence()` currently wraps the
dense-only pipeline. The contract above will not change when BM25/
reranking are added later; only the internal "Step 5" of `retrieve_evidence()`
will be swapped out.

---

## `verify_claim()`

### Input — `VerifyClaimRequest`

Mirrors CLAUDE.md's Door 2 input exactly:

| Field | Type | Notes |
|---|---|---|
| `claim_text` | `str` | |
| `citation_text` | `str` | |
| `doi_status` | `"VALID" \| "INVALID" \| "UNRESOLVABLE"` | |
| `metadata` | `{title, abstract}` | |
| `retrieved_evidence` | list of `{chunk_id, chunk_text, similarity_score}` | the chunks you selected after Door 1 |
| `overall_similarity_score` | `float` | carried over from Door 1's output |

Note: this contract has no `doi` field, only `doi_status`. We never need the
DOI string itself for verification — only whether it resolved.

### Output — `VerifyClaimResponse`

| Field | Type | Notes |
|---|---|---|
| `support_status` | `"SUPPORTED" \| "PARTIALLY_SUPPORTED" \| "NOT_SUPPORTED" \| "INSUFFICIENT_EVIDENCE" \| "NEEDS_HUMAN_REVIEW"` | |
| `confidence` | `float` (0–1) | |
| `explanation` | `str` | four-step chain-of-thought reasoning |
| `evidence_used` | `list[str]` | chunk_ids the LLM relied on |
| `limitations` | `str \| None` | |
| `human_review_required` | `bool` | |

### Edge cases

- `doi_status` is `INVALID` or `UNRESOLVABLE` → `support_status: "INSUFFICIENT_EVIDENCE"` immediately, no LLM call is made.
- The LLM call itself fails (missing API key, network error) → `support_status: "NEEDS_HUMAN_REVIEW"`, `confidence: 0.0`.
- The LLM's response is malformed JSON or doesn't match our schema → also `"NEEDS_HUMAN_REVIEW"` (handled by `rag/verification/validator.py`, which `verify_claim()` calls internally). **We never raise an exception out of this function.**
- `overall_similarity_score` is below 0.5 → `human_review_required: true`, even if the verdict itself looks confident. This reuses the same threshold `rag/retrieval/vector_store.py` applies internally, so a verdict built on weak evidence always gets flagged.

---

## Key design decisions

### Two extra Pydantic models per door, not a `dict`

`CLAUDE.md`'s Door 1/2 JSON shapes don't match our internal models
field-for-field — e.g. Door 2's output field is `support_status`, but our
internal `VerificationOutput` model calls the same concept `verdict`,
because that's the name the LLM prompt and `validate_output()` use
internally. Rather than bend our internal models to match the backend's
exact field names (which would leak API concerns into pipeline-internal
code), `api.py` defines its own request/response models
(`RetrieveEvidenceRequest/Response`, `VerifyClaimRequest/Response`) that
match the backend contract literally, and translates between them and our
internal models inside the two public functions. Where the shapes do
overlap, we reuse: `SourceEvidence` (from `rag/ingestion/models.py`) and
`Verdict` (from `rag/verification/models.py`) are imported directly rather
than redefined.

### Adapting the loose Door 2 evidence contract

Door 2's `retrieved_evidence` only carries `chunk_id`, `chunk_text`, and
`similarity_score` — it has no `section`, `priority`, or `paper_doi`. Our
internal `VerificationInput.chunks` expects full `ChunkMetadata` objects
because `verify.j2` prints each chunk's section label. `verify_claim()`
fills the missing fields with neutral placeholders (`section="unknown"`,
`priority=1.0`, `paper_doi=""`, `evidence_type="UNKNOWN"`) — these only
affect the prompt's section annotation, never the verdict logic itself.

### Reusing `embed_chunks()` to embed a single string

`rag/retrieval/embedder.py` only exposes `embed_chunks()`, which takes a
list of `ChunkMetadata`. To embed the claim text (a single string) with
the exact same model, `retrieve_evidence()` wraps it in a throwaway
`ChunkMetadata` and calls `embed_chunks()` with a one-item list, rather
than duplicating a second OpenAI-client-plus-retry implementation just for
single-string embedding.

### Every failure mode collapses to a safe response, never an exception

Both functions are designed so the backend never has to wrap the call in
a `try/except`. Pipeline exceptions (bad API key, network errors,
malformed LLM JSON) are all caught internally and converted into the
appropriate "could not verify" response — `"FAILED"` for Door 1,
`"NEEDS_HUMAN_REVIEW"` for Door 2 — matching the fail-safe pattern already
used by `classify_citation_type()` (falls back to `BACKGROUND`) and
`validate_output()` (falls back to `NEEDS_HUMAN_REVIEW`).
