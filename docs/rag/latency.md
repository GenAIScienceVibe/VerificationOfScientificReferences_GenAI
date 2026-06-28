# rag/evaluation/latency.py — Latency & Cost Profiler (SCRUM-185)

## What it does

Measures the real-world performance of the embedding API by running 10 synthetic
chunks through the pipeline — one chunk per API call — and recording how long
each call takes. It also makes a single batched call with all 10 chunks together
to quantify the speedup gained from batching.

**Metrics produced:**

| Metric | Description |
|---|---|
| Per-call latency (ms) | Min, max, mean, median, p95, stdev over 10 individual calls |
| Total tokens | Sum of cl100k_base tokens across all 10 chunks |
| Cost per call (USD) | token_count × $0.02 / 1,000,000 |
| Est. cost per paper (USD) | avg_cost_per_call × 100 (assumed chunks per paper) |
| Batch comparison | Latency + cost of sending all 10 chunks in one API request |

All numbers are saved to `data/evaluation/latency_results.json`.

---

## How to use it

```bash
python -m rag.evaluation.latency
```

Requires `OPENROUTER_API_KEY` in `.env`. The run takes ~15–30 seconds (11 API calls total).

**Example console output:**

```
verifAi Embedding Latency & Cost Profiler
────────────────────────────────────────────
Model : openai/text-embedding-3-small
Chunks: 10 test chunks (individual calls)

  Call  1:   14 tokens    382.5 ms  $0.0000003
  Call  2:   52 tokens    415.1 ms  $0.0000010
  ...
────────────────────────────────────────────
Batched call (all 10 chunks in one request):
  612 tokens  540.2 ms  $0.0000122

────────────────────────────────────────────
Latency statistics (10 individual calls):
  Mean   : 420.3 ms
  Median : 408.7 ms
  Min    : 350.1 ms
  Max    : 610.2 ms
  P95    : 590.5 ms
  Stdev  : 72.4 ms

Batch vs. individual (total wall time):
  10 individual calls : 4203.0 ms
  1 batched call      : 540.2 ms
  Speedup from batch  : 7.8×

Cost estimate (@ $0.02 / 1M tokens):
  Avg cost per call   : $0.0000012
  Est. cost per paper : $0.00012  (100 chunks assumed)

Results: data\evaluation\latency_results.json
```

---

## Output JSON structure

```json
{
  "embedding_model": "openai/text-embedding-3-small",
  "timestamp": "2026-06-15T12:00:00+00:00",
  "num_individual_calls": 10,
  "total_tokens_individual": 612,
  "total_cost_individual_usd": 1.224e-05,
  "avg_cost_per_call_usd": 1.224e-06,
  "estimated_cost_per_paper_usd": 0.0001224,
  "latency_stats": {
    "min_ms": 350.1,
    "max_ms": 610.2,
    "mean_ms": 420.3,
    "median_ms": 408.7,
    "p95_ms": 590.5,
    "stdev_ms": 72.4
  },
  "batch_comparison": {
    "total_tokens": 612,
    "latency_ms": 540.2,
    "cost_usd": 1.224e-05
  },
  "individual_calls": [
    {
      "call_index": 1,
      "chunk_preview": "This study investigates the effect of aerobic exercise...",
      "token_count": 14,
      "latency_ms": 382.5,
      "cost_usd": 2.8e-07
    }
  ]
}
```

---

## Key design decisions

### Why 10 individual calls instead of one batch?
The CLAUDE.md spec says "measure time per embedding call." A batch call gives one
latency number for N chunks. Ten individual calls give a distribution — min, max,
p95 — which is far more useful for understanding real API behaviour under normal
conditions (cache misses, network jitter, server variance).

### Why also include a batch call?
The batch call shows the efficiency ceiling: how much faster the pipeline could be
if we sent all chunks in a single request. The speedup factor tells us whether
batching is worth the added complexity for our use case.

### Why 100 chunks per paper for the cost extrapolation?
A typical scientific paper is 4,000–8,000 words. At ~512 tokens per chunk and
50-token overlap, a full-text paper produces roughly 80–120 chunks. 100 is the
midpoint. It is clearly labelled as an estimate in the JSON output.

### Why tiktoken cl100k_base?
The chunker uses the same encoding (`cl100k_base`) to enforce the 512-token
chunk size limit. Using the same encoder here keeps token counts consistent
between chunking and cost estimation.

### Cost model
`text-embedding-3-small` is priced at **$0.02 per 1,000,000 tokens** via
OpenRouter (as specified in CLAUDE.md). The constant `COST_PER_TOKEN_USD` in
the module encodes this exactly so it is easy to update if pricing changes.
