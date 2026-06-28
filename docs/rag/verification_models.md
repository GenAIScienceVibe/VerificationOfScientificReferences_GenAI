# models.py (verification) — SCRUM-194

## What it does

`rag/verification/models.py` defines the Pydantic schema for Door 2 (LLM
verification): the data the verifier consumes (`VerificationInput`) and the
exact shape the backend expects back (`VerificationOutput`).

The `Verdict` enum pins the five labels the backend schema accepts. Using an
enum instead of a free-text string means an invalid label (e.g. a typo or a
hallucinated label from the LLM) fails validation immediately instead of
silently reaching the backend.

---

## How to use it

```python
from rag.verification.models import Verdict, VerificationInput, VerificationOutput

vi = VerificationInput(
    claim_text="Exercise reduces heart disease risk",
    citation_type="RESULT_COMPARISON",
    chunks=top_chunks,          # list[ChunkMetadata] from the retrieval step
    doi="10.1234/example.2019.001",
)

vo = VerificationOutput(
    verdict=Verdict.PARTIALLY_SUPPORTED,
    confidence=0.72,
    explanation="The source reports 28% reduction, not 35% as claimed.",
    evidence_used=["10_1234_example_2019_001_chunk_001"],
    limitations="Only abstract-level evidence was available.",
    human_review_required=True,
)
```

### Input / output types

| Type | Fields |
|---|---|
| `VerificationInput` | `claim_text: str`, `citation_type: str`, `chunks: list[ChunkMetadata]`, `doi: str` |
| `VerificationOutput` | `verdict: Verdict`, `confidence: float (0–1)`, `explanation: str`, `evidence_used: list[str] = []`, `limitations: str \| None = None`, `human_review_required: bool` |
| `Verdict` | `SUPPORTED`, `PARTIALLY_SUPPORTED`, `NOT_SUPPORTED`, `INSUFFICIENT_EVIDENCE`, `NEEDS_HUMAN_REVIEW` |

---

## Key design decisions

### `Verdict` as a `str, Enum`

Subclassing both `str` and `Enum` means `Verdict.SUPPORTED == "SUPPORTED"` is
`True` and the value serialises to plain JSON without a custom encoder —
important since the backend expects the exact string label, not an enum
repr.

### `confidence` bounded with `ge=0.0, le=1.0`

Pydantic rejects out-of-range confidence at the model boundary rather than
letting a malformed LLM output (e.g. `confidence: 1.5`) propagate downstream.

### `evidence_used` and `limitations` are optional with safe defaults

Not every verdict has supporting chunk IDs or limitations to report (e.g.
`INSUFFICIENT_EVIDENCE` with zero retrieved chunks), so these default to an
empty list and `None` respectively instead of being required.

### `chunks` reuses `ChunkMetadata` from `rag.ingestion.models`

`VerificationInput.chunks` is typed as `list[ChunkMetadata]` rather than a
new structure — the chunks handed to the verifier are the same retrieved
chunks (with `section`, `priority`, etc.) produced earlier in the pipeline,
so reusing the existing model avoids duplicate schemas drifting apart.

---

## Module-level constants

None — this module is schema-only (no business logic, no constants).
