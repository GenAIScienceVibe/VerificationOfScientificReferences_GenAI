"""
Latency and cost profiler for the verifAi embedding pipeline (SCRUM-185).

Runs the embedding API on 10 synthetic test chunks, one at a time, to measure
real per-call latency. Also runs a single batch call with all 10 chunks to
show the cost-efficiency of batching versus individual calls.

Metrics reported:
  - Latency (ms) per individual API call: min, max, mean, median, p95
  - Total tokens sent across all individual calls
  - Cost per individual call (USD) and estimated cost per paper
  - Comparison: individual calls vs. one batched call (latency + token count)

Cost model: OpenAI text-embedding-3-small via OpenRouter
  - $0.02 per 1,000,000 tokens (as specified in CLAUDE.md)

Usage:
    python -m rag.evaluation.latency

Output:
    - Console summary with latency statistics and cost estimates
    - data/evaluation/latency_results.json  (detailed JSON report)

Requires OPENROUTER_API_KEY in .env (real API calls are made).
"""

import logging
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

EMBEDDING_MODEL = "openai/text-embedding-3-small"

# Cost in USD per token (from $0.02 per 1,000,000 tokens).
COST_PER_TOKEN_USD = 0.02 / 1_000_000

# Typical medium-length paper has roughly 80–120 chunks; 100 is a reasonable
# estimate for the "cost per paper" extrapolation.
ESTIMATED_CHUNKS_PER_PAPER = 100

DEFAULT_OUTPUT_PATH = Path("data/evaluation/latency_results.json")


# ── Test data ──────────────────────────────────────────────────────────────────

# 10 synthetic chunks of varying length, representative of real paper sections.
TEST_CHUNKS: list[str] = [
    # 1 — short abstract sentence
    "This study investigates the effect of aerobic exercise on cardiovascular health.",
    # 2 — methods paragraph
    (
        "Participants were randomly assigned to either a structured exercise programme "
        "consisting of 150 minutes of moderate-intensity aerobic activity per week, or a "
        "sedentary control condition, for a period of 24 months. Compliance was monitored "
        "via wrist-worn accelerometers and verified against weekly self-report diaries."
    ),
    # 3 — results paragraph
    (
        "After 24 months, the intervention group exhibited a 35 percent reduction in "
        "composite cardiovascular disease risk score compared to the control group. "
        "Secondary outcomes including resting blood pressure, LDL cholesterol, and "
        "fasting glucose all improved significantly. Adherence to the exercise protocol "
        "was 87 percent across the intervention arm."
    ),
    # 4 — discussion paragraph
    (
        "A 35 percent risk reduction is clinically meaningful and consistent with prior "
        "meta-analytic estimates. The improvement in lipid profiles and blood pressure "
        "suggests multiple complementary mechanisms are at work. Limitations of this "
        "study include self-reported adherence and exclusion of participants with "
        "pre-existing cardiac conditions, which may limit generalisability."
    ),
    # 5 — vitamin D results
    (
        "Patients receiving daily vitamin D supplementation exhibited a significant "
        "increase in bone mineral density at both the lumbar spine and total hip "
        "compared to the placebo group. Mean lumbar spine bone mineral density increased "
        "by 2.4 percent in the vitamin D group versus 0.1 percent in the control arm."
    ),
    # 6 — sleep deprivation results
    (
        "Subjects who underwent 24 hours of total sleep deprivation showed significant "
        "impairment in working memory performance across all three measures compared to "
        "their baseline rested condition. Mean n-back accuracy declined by 22 percent, "
        "digit span decreased by 1.8 items, and spatial working memory error rates doubled."
    ),
    # 7 — infection control results
    (
        "Implementation of enhanced hand hygiene protocols led to a 40 percent reduction "
        "in hospital-acquired infection rates compared to the pre-intervention period. "
        "The largest reductions were observed for catheter-associated urinary tract "
        "infections (52 percent) and surgical site infections (38 percent)."
    ),
    # 8 — Mediterranean diet results
    (
        "After 10 years of follow-up, elderly adults who adhered strictly to a "
        "Mediterranean dietary pattern showed a 30 percent reduction in cognitive decline "
        "risk compared to those with low adherence, after adjusting for all covariates. "
        "The association was strongest for the fish, olive oil, and vegetable components."
    ),
    # 9 — long methods paragraph
    (
        "A total of 4,500 community-dwelling adults aged 65 and above were enrolled at "
        "baseline. Dietary intake was assessed using a validated 136-item food frequency "
        "questionnaire administered by trained dietitians during in-person visits. "
        "A Mediterranean diet adherence score ranging from 0 to 9 was computed for each "
        "participant based on consumption tertiles for each food group. Cognitive function "
        "was evaluated annually using two validated instruments: the Mini-Mental State "
        "Examination and the Montreal Cognitive Assessment. Incident cognitive decline "
        "was defined as a decline of 3 or more points on either measure sustained over "
        "two consecutive annual assessments. Covariates including age, sex, education "
        "level, physical activity, body mass index, smoking status, and baseline "
        "cognitive function were adjusted for in all multivariable regression analyses."
    ),
    # 10 — conclusion paragraph
    (
        "Structured aerobic exercise substantially reduces cardiovascular disease risk. "
        "Healthcare providers should routinely prescribe physical activity as a primary "
        "prevention strategy for patients with elevated cardiovascular risk profiles. "
        "Future research should examine the optimal exercise modality, intensity, and "
        "duration for risk reduction in diverse patient populations including older "
        "adults and those with comorbid metabolic conditions."
    ),
]


# ── Pydantic models ────────────────────────────────────────────────────────────


class CallResult(BaseModel):
    """Timing and cost data for a single embedding API call."""

    call_index: int = Field(..., description="1-based index of this call")
    chunk_preview: str = Field(..., description="First 80 characters of the chunk")
    token_count: int = Field(..., description="Tokens in this chunk (cl100k_base)")
    latency_ms: float = Field(..., description="Round-trip time for the API call in milliseconds")
    cost_usd: float = Field(..., description="Estimated cost of this call in USD")


class BatchCallResult(BaseModel):
    """Timing and cost data for a single batched call with all 10 chunks."""

    total_tokens: int = Field(..., description="Total tokens across all 10 chunks")
    latency_ms: float = Field(..., description="Round-trip time for the batched API call in ms")
    cost_usd: float = Field(..., description="Estimated cost of the batched call in USD")


class LatencyStats(BaseModel):
    """Descriptive statistics over the individual per-call latency measurements."""

    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float
    p95_ms: float = Field(..., description="95th-percentile latency (ms)")
    stdev_ms: float = Field(..., description="Standard deviation of per-call latency")


class LatencyReport(BaseModel):
    """Full latency and cost profiling report saved to JSON."""

    embedding_model: str
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp of the run")
    num_individual_calls: int = Field(..., description="Number of single-chunk API calls made")
    total_tokens_individual: int = Field(
        ..., description="Total tokens sent across all individual calls"
    )
    total_cost_individual_usd: float = Field(
        ..., description="Total cost of all individual calls in USD"
    )
    avg_cost_per_call_usd: float = Field(
        ..., description="Mean cost per individual embedding call in USD"
    )
    estimated_cost_per_paper_usd: float = Field(
        ...,
        description=(
            f"Extrapolated cost for a paper with {ESTIMATED_CHUNKS_PER_PAPER} chunks, "
            "using the mean per-call cost"
        ),
    )
    latency_stats: LatencyStats
    batch_comparison: BatchCallResult = Field(
        ..., description="Single batched call with all 10 chunks — for efficiency comparison"
    )
    individual_calls: list[CallResult]


# ── Private helpers ────────────────────────────────────────────────────────────


def _build_client() -> OpenAI:
    """Build and return an OpenAI-compatible client pointed at OpenRouter.

    Raises EnvironmentError if OPENROUTER_API_KEY is not set.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file before "
            "running the latency profiler."
        )
    return OpenAI(api_key=api_key, base_url=base_url)


def _count_tokens(text: str) -> int:
    """Count the number of tokens in a string using cl100k_base (same as the chunker).

    Args:
        text: The text to tokenise.

    Returns:
        Number of tokens.
    """
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def _embed_single(client: OpenAI, text: str) -> tuple[list[float], float]:
    """Embed one chunk and return the vector plus the wall-clock latency in ms.

    We time the raw API call (not any pre/post processing) so the measurement
    reflects network + server latency only.

    Args:
        client: Authenticated OpenRouter-backed OpenAI client.
        text:   The chunk text to embed.

    Returns:
        (embedding_vector, latency_ms) tuple.
    """
    t0 = time.perf_counter()
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return response.data[0].embedding, latency_ms


def _embed_batch(client: OpenAI, texts: list[str]) -> tuple[list[list[float]], float]:
    """Embed a list of texts in a single batched API call.

    Args:
        client: Authenticated OpenRouter-backed OpenAI client.
        texts:  List of chunk texts to embed.

    Returns:
        (list_of_vectors, latency_ms) tuple.
    """
    t0 = time.perf_counter()
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    vectors = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
    return vectors, latency_ms


def _compute_stats(latencies: list[float]) -> LatencyStats:
    """Compute descriptive statistics over a list of latency measurements.

    Args:
        latencies: List of per-call latency values in milliseconds.

    Returns:
        LatencyStats with min, max, mean, median, p95, and stdev.
    """
    sorted_lats = sorted(latencies)
    n = len(sorted_lats)
    # p95: index at the 95th percentile (ceiling, 0-based)
    p95_idx = min(int(n * 0.95), n - 1)
    return LatencyStats(
        min_ms=round(sorted_lats[0], 2),
        max_ms=round(sorted_lats[-1], 2),
        mean_ms=round(statistics.mean(latencies), 2),
        median_ms=round(statistics.median(latencies), 2),
        p95_ms=round(sorted_lats[p95_idx], 2),
        stdev_ms=round(statistics.stdev(latencies) if n > 1 else 0.0, 2),
    )


def _save_report(report: LatencyReport, output_path: Path | None = None) -> Path:
    """Serialise the LatencyReport to JSON and write it to disk.

    Creates the parent directory if it does not exist.

    Args:
        report:      The completed latency report.
        output_path: Destination file path. Defaults to DEFAULT_OUTPUT_PATH.

    Returns:
        The path where the file was written.
    """
    if output_path is None:
        output_path = DEFAULT_OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Latency report saved to %s", output_path)
    return output_path


# ── Public entry point ─────────────────────────────────────────────────────────


def run_latency_profile(output_path: Path | None = None) -> LatencyReport:
    """Run the full latency and cost profiling run.

    Makes 10 individual single-chunk API calls (one per TEST_CHUNK) then one
    batched call with all 10 chunks. Collects timing and token counts, computes
    statistics, and saves a JSON report.

    Args:
        output_path: Where to save the JSON report. Defaults to DEFAULT_OUTPUT_PATH.

    Returns:
        LatencyReport with per-call details and aggregate statistics.
    """
    load_dotenv()
    client = _build_client()

    print(f"\nverifAi Embedding Latency & Cost Profiler\n{'─' * 44}")
    print(f"Model : {EMBEDDING_MODEL}")
    print(f"Chunks: {len(TEST_CHUNKS)} test chunks (individual calls)\n")

    # ── Phase 1: individual calls ──────────────────────────────────────────────

    call_results: list[CallResult] = []
    latencies: list[float] = []

    for i, chunk_text in enumerate(TEST_CHUNKS, start=1):
        token_count = _count_tokens(chunk_text)
        _, latency_ms = _embed_single(client, chunk_text)
        cost_usd = token_count * COST_PER_TOKEN_USD

        call_results.append(
            CallResult(
                call_index=i,
                chunk_preview=chunk_text[:80],
                token_count=token_count,
                latency_ms=round(latency_ms, 2),
                cost_usd=round(cost_usd, 8),
            )
        )
        latencies.append(latency_ms)

        print(
            f"  Call {i:>2}: {token_count:>4} tokens  "
            f"{latency_ms:>7.1f} ms  "
            f"${cost_usd:.7f}"
        )

    # ── Phase 2: batch call ────────────────────────────────────────────────────

    print(f"\n{'─' * 44}")
    print("Batched call (all 10 chunks in one request):")
    _, batch_latency_ms = _embed_batch(client, TEST_CHUNKS)
    batch_total_tokens = sum(r.token_count for r in call_results)
    batch_cost_usd = batch_total_tokens * COST_PER_TOKEN_USD

    batch_result = BatchCallResult(
        total_tokens=batch_total_tokens,
        latency_ms=round(batch_latency_ms, 2),
        cost_usd=round(batch_cost_usd, 8),
    )

    print(
        f"  {batch_total_tokens} tokens  "
        f"{batch_latency_ms:.1f} ms  "
        f"${batch_cost_usd:.7f}"
    )

    # ── Statistics & extrapolation ─────────────────────────────────────────────

    stats = _compute_stats(latencies)
    total_tokens = sum(r.token_count for r in call_results)
    total_cost = sum(r.cost_usd for r in call_results)
    avg_cost_per_call = total_cost / len(call_results)
    cost_per_paper = avg_cost_per_call * ESTIMATED_CHUNKS_PER_PAPER

    # ── Report ─────────────────────────────────────────────────────────────────

    report = LatencyReport(
        embedding_model=EMBEDDING_MODEL,
        timestamp=datetime.now(timezone.utc).isoformat(),
        num_individual_calls=len(call_results),
        total_tokens_individual=total_tokens,
        total_cost_individual_usd=round(total_cost, 8),
        avg_cost_per_call_usd=round(avg_cost_per_call, 8),
        estimated_cost_per_paper_usd=round(cost_per_paper, 6),
        latency_stats=stats,
        batch_comparison=batch_result,
        individual_calls=call_results,
    )

    saved_to = _save_report(report, output_path)

    # ── Console summary ────────────────────────────────────────────────────────

    sum_individual_ms = sum(latencies)
    print(f"\n{'─' * 44}")
    print("Latency statistics (10 individual calls):")
    print(f"  Mean   : {stats.mean_ms:.1f} ms")
    print(f"  Median : {stats.median_ms:.1f} ms")
    print(f"  Min    : {stats.min_ms:.1f} ms")
    print(f"  Max    : {stats.max_ms:.1f} ms")
    print(f"  P95    : {stats.p95_ms:.1f} ms")
    print(f"  Stdev  : {stats.stdev_ms:.1f} ms")
    print(f"\nBatch vs. individual (total wall time):")
    print(f"  10 individual calls : {sum_individual_ms:.1f} ms")
    print(f"  1 batched call      : {batch_latency_ms:.1f} ms")
    speedup = sum_individual_ms / batch_latency_ms if batch_latency_ms > 0 else 0
    print(f"  Speedup from batch  : {speedup:.1f}×")
    print(f"\nCost estimate (@ $0.02 / 1M tokens):")
    print(f"  Avg cost per call   : ${avg_cost_per_call:.7f}")
    print(f"  Est. cost per paper : ${cost_per_paper:.5f}  "
          f"({ESTIMATED_CHUNKS_PER_PAPER} chunks assumed)")
    print(f"\nResults: {saved_to}\n")

    return report


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_latency_profile()
