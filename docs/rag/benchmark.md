# benchmark.py — SCRUM-184

## What it does

`benchmark.py` is a retrieval accuracy evaluation script.

It runs the **complete retrieval pipeline** (clean → chunk → embed → search)
on 5 synthetic scientific papers where the correct evidence chunk is known in
advance, then reports **hit@3 accuracy**: in what percentage of cases did the
correct chunk appear within the top-3 results returned by the vector store?

Results are printed to the console and saved to `data/evaluation/benchmark_results.json`.

---

## How to run it

```bash
# Make sure OPENROUTER_API_KEY is set in your .env file first.
python -m rag.evaluation.benchmark
```

Expected console output:

```
verifAi Retrieval Benchmark — hit@3
────────────────────────────────────────────
  [HIT ] case_001: Regular aerobic exercise reduces cardiovascular…  (rank 1)
  [HIT ] case_002: Vitamin D supplementation increases bone mineral… (rank 2)
  [HIT ] case_003: Twenty-four hours of sleep deprivation significa… (rank 1)
  [HIT ] case_004: Enhanced hospital hand hygiene protocols reduce … (rank 1)
  [HIT ] case_005: Mediterranean diet adherence reduces cognitive de… (rank 2)

────────────────────────────────────────────
  Accuracy (hit@3): 100.0%  (5/5 hits)
  Results: data/evaluation/benchmark_results.json
```

---

## How it works

### Benchmark cases

5 synthetic papers are hardcoded in `BENCHMARK_CASES`. Each has:

| Field | Description |
|---|---|
| `case_id` | Unique identifier (e.g. `case_001`) |
| `doi` | Synthetic DOI used for chunk metadata |
| `claim` | The scientific claim to verify |
| `expected_evidence` | Phrase that must appear verbatim in the correct chunk |
| `source_text` | Multi-section synthetic paper (~400–600 words) |

The `expected_evidence` phrase is placed in the **results section** of each
paper.  This is the hardest test: the results section receives a priority weight
of 1.3, so the search must both semantically match the claim *and* correctly
surface that high-priority chunk above others.

### Hit detection

A case is a **HIT** if any of the top-3 retrieved chunks contains the
`expected_evidence` phrase as a case-insensitive substring.

```python
needle = expected_evidence.lower().strip()
for rc in top_chunks[:3]:
    if needle in rc.chunk.chunk_text.lower():
        return True, rc.rank
return False, None
```

### Pipeline flow per case

```
source_text
  │
  ▼ clean_text()         → removes noise, normalises whitespace
  │
  ▼ chunk_text()         → section-aware splitting, metadata tagging
  │
  ▼ embed_chunks()       → OpenRouter text-embedding-3-small
  │
  ▼ _embed_text(claim)   → same model, one vector for the claim
  │
  ▼ search()             → FAISS cosine + section-priority reranking
  │
  ▼ _check_hit()         → substring match against expected_evidence
```

---

## Key design decisions

### Why synthetic papers?

Real papers would require downloading PDFs and manually annotating which chunk
contains the correct evidence — time-consuming and non-reproducible.
Synthetic papers give us full control: we know exactly which sentence is the
ground-truth evidence, so the hit check is deterministic.

### Why hit@3 and not hit@1?

The pipeline is designed to retrieve a pool of candidates for an LLM to
reason over — not to return a single correct answer.  Hit@3 is the right
metric for this use case: if the evidence is anywhere in the top-3, the
downstream LLM verification step will have access to it.

### Why expected_evidence in the results section?

The results section has the highest priority weight (1.3).  If retrieval works
correctly, the results chunk should naturally rise to the top.  Placing the
evidence there tests both semantic similarity *and* the priority reranking.

---

## Output format (`benchmark_results.json`)

```json
{
  "total_cases": 5,
  "total_hits": 5,
  "total_errors": 0,
  "accuracy_pct": 100.0,
  "top_k": 3,
  "embedding_model": "openai/text-embedding-3-small",
  "timestamp": "2026-06-15T10:00:00+00:00",
  "results": [
    {
      "case_id": "case_001",
      "claim": "Regular aerobic exercise reduces...",
      "hit": true,
      "rank_if_found": 1,
      "top_chunks": [
        {
          "rank": 1,
          "section": "results",
          "weighted_score": 1.197,
          "text_preview": "After 24 months, participants who performed regular..."
        }
      ],
      "total_chunks_indexed": 6,
      "error": null
    }
  ]
}
```
