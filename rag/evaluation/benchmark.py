"""
Retrieval benchmark for the verifAi RAG pipeline (SCRUM-184).

Runs the full retrieval pipeline (clean → chunk → embed → search) on a small
set of synthetic papers where the correct evidence chunk is known in advance.

Metric: hit@3 — did the chunk containing the expected evidence appear in the
top-3 results returned by the vector store?

Usage:
    python -m rag.evaluation.benchmark

Output:
    - Console summary per case (HIT / MISS)
    - data/evaluation/benchmark_results.json  (detailed JSON report)

Requires OPENROUTER_API_KEY in .env (real API calls are made to embed text).
"""

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from rag.ingestion.cleaner import clean_text
from rag.ingestion.chunker import chunk_text
from rag.ingestion.models import CleanerInput, ChunkerInput, EvidenceAvailability
from rag.retrieval.embedder import embed_chunks
from rag.retrieval.models import EmbedderInput, VectorStoreInput
from rag.retrieval.vector_store import search

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

EMBEDDING_MODEL = "openai/text-embedding-3-small"

# hit@K: the correct chunk must appear within the top K results to count as a hit.
TOP_K = 3

DEFAULT_OUTPUT_PATH = Path("data/evaluation/benchmark_results.json")


# ── Pydantic models ────────────────────────────────────────────────────────────


class BenchmarkCase(BaseModel):
    """One evaluation test case with a known claim-evidence pair."""

    case_id: str = Field(..., description="Unique identifier for this case")
    doi: str = Field(..., description="Synthetic DOI used for chunk metadata")
    claim: str = Field(..., description="Scientific claim to verify")
    expected_evidence: str = Field(
        ...,
        description=(
            "Phrase that must appear verbatim (case-insensitive) in the source text "
            "and inside the chunk that should be retrieved."
        ),
    )
    source_text: str = Field(..., description="Full synthetic paper text")


class TopChunkPreview(BaseModel):
    """Compact preview of a single retrieved chunk, for JSON output."""

    rank: int
    section: str
    weighted_score: float
    text_preview: str = Field(..., description="First 200 characters of chunk text")


class CaseResult(BaseModel):
    """Result of running the full pipeline on one BenchmarkCase."""

    case_id: str
    claim: str
    hit: bool = Field(..., description="True if expected evidence found in top-K chunks")
    rank_if_found: int | None = Field(
        ..., description="Rank of the matching chunk (1-based), or None if not found"
    )
    top_chunks: list[TopChunkPreview]
    total_chunks_indexed: int = Field(..., description="Total chunks the source was split into")
    error: str | None = Field(None, description="Error message if the pipeline failed")


class BenchmarkReport(BaseModel):
    """Full benchmark run report saved to JSON."""

    total_cases: int
    total_hits: int
    total_errors: int
    accuracy_pct: float = Field(..., description="hit@K accuracy as a percentage (0–100)")
    top_k: int = Field(..., description="K used for hit@K evaluation")
    embedding_model: str
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp of the run")
    results: list[CaseResult]


# ── Benchmark cases ────────────────────────────────────────────────────────────

BENCHMARK_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        case_id="case_001",
        doi="10.0000/benchmark.aerobic.2024",
        claim="Regular aerobic exercise reduces cardiovascular disease risk by 35%.",
        expected_evidence=(
            "participants who performed regular aerobic exercise showed a 35 percent "
            "reduction in cardiovascular disease risk"
        ),
        source_text="""\
ABSTRACT

Cardiovascular disease is the leading cause of mortality globally. This study
evaluates whether a structured aerobic exercise program reduces cardiovascular
disease risk in middle-aged adults over a 24-month intervention period.

INTRODUCTION

Sedentary behaviour has been consistently linked to elevated cardiovascular
mortality. Despite broad consensus on the benefits of physical activity, the
precise magnitude of risk reduction attributable to aerobic exercise alone
remains uncertain. Previous meta-analyses have reported wide ranges, partly
due to inconsistent exercise definitions and outcome measures.

METHODS

We conducted a randomised controlled trial with 1,200 adults aged 40 to 65.
Participants were assigned to either a structured aerobic exercise programme
(150 minutes of moderate-intensity exercise per week) or a sedentary control
condition for 24 months. The primary outcome was a validated composite
cardiovascular disease risk score assessed at baseline and end of trial.

RESULTS

After 24 months, participants who performed regular aerobic exercise showed a
35 percent reduction in cardiovascular disease risk compared to sedentary
controls. Secondary outcomes including resting blood pressure, LDL cholesterol,
and fasting glucose all improved significantly in the exercise group. Adherence
to the exercise protocol was 87 percent across the intervention arm.

DISCUSSION

A 35 percent risk reduction is clinically meaningful and aligns with prior
meta-analytic estimates. The improvement in lipid profiles and blood pressure
suggests multiple complementary mechanisms. Limitations include self-reported
adherence and the exclusion of participants with pre-existing cardiac conditions.

CONCLUSION

Structured aerobic exercise substantially reduces cardiovascular disease risk.
Healthcare providers should routinely prescribe physical activity as a primary
prevention strategy for patients with elevated cardiovascular risk profiles.
""",
    ),
    BenchmarkCase(
        case_id="case_002",
        doi="10.0000/benchmark.vitamind.2024",
        claim="Vitamin D supplementation increases bone mineral density in elderly patients.",
        expected_evidence=(
            "patients receiving daily vitamin D supplementation exhibited a significant "
            "increase in bone mineral density"
        ),
        source_text="""\
ABSTRACT

Osteoporosis affects millions of elderly individuals worldwide. This randomised
trial examines whether daily vitamin D supplementation improves bone mineral
density in patients aged 65 and older over a 12-month period.

INTRODUCTION

Vitamin D plays a crucial role in calcium absorption and bone mineralisation.
Deficiency is common in the elderly due to reduced sun exposure and decreased
cutaneous synthesis. While observational studies suggest a positive association
between vitamin D levels and bone health, high-quality interventional evidence
in elderly populations is limited.

METHODS

Adults aged 65 and above with confirmed vitamin D deficiency (serum 25-OH-D
below 50 nmol/L) were enrolled and randomly assigned to receive either 2000 IU
of vitamin D3 daily or a matched placebo for 12 months. Bone mineral density
was measured at the lumbar spine and total hip using dual-energy X-ray
absorptiometry at baseline and study completion.

RESULTS

At 12 months, patients receiving daily vitamin D supplementation exhibited a
significant increase in bone mineral density at both the lumbar spine and total
hip compared to the placebo group. Mean lumbar spine bone mineral density
increased by 2.4 percent in the vitamin D group versus 0.1 percent in the
control arm. Hip density showed a 1.8 percent improvement. No significant
adverse events were attributable to supplementation.

DISCUSSION

These results confirm that vitamin D supplementation meaningfully improves
bone mineral density in deficient elderly patients. The effect size at the
lumbar spine exceeds the minimum clinically important difference, suggesting
practical relevance for fracture risk reduction. Longer follow-up studies
are needed to determine whether these gains are sustained beyond 12 months.

CONCLUSION

Daily vitamin D supplementation is a safe and effective intervention to
improve bone health in elderly patients with confirmed deficiency.
""",
    ),
    BenchmarkCase(
        case_id="case_003",
        doi="10.0000/benchmark.sleep.2024",
        claim="Twenty-four hours of sleep deprivation significantly impairs working memory.",
        expected_evidence=(
            "subjects who underwent 24 hours of total sleep deprivation showed "
            "significant impairment in working memory performance"
        ),
        source_text="""\
ABSTRACT

Sleep deprivation is pervasive in modern society. This experimental study
investigates the effects of 24-hour total sleep deprivation on working memory
and sustained attention in healthy young adults.

INTRODUCTION

Working memory, the cognitive system that temporarily holds and manipulates
information, is central to executive function and academic performance.
Adequate sleep is believed to be necessary for the consolidation and
maintenance of working memory capacity, yet the direct causal relationship
under controlled conditions has rarely been isolated.

METHODS

Forty healthy adult volunteers aged 18 to 35 completed a within-subjects
counterbalanced design. Each participant completed a standard battery of
working memory tasks (n-back task, digit span, and spatial working memory)
under two conditions: after a full night of normal sleep (baseline) and after
36 hours of continuous wakefulness. Order was counterbalanced. All testing was
conducted in a controlled laboratory environment.

RESULTS

Subjects who underwent 24 hours of total sleep deprivation showed significant
impairment in working memory performance across all three measures compared
to their baseline rested condition. Mean n-back accuracy declined by 22
percent, digit span decreased by 1.8 items, and spatial working memory
error rates doubled. Sustained attention deficits, measured by the
Psychomotor Vigilance Task, showed the largest effect size of all outcomes.

DISCUSSION

The magnitude of working memory impairment observed after a single night of
total sleep deprivation is comparable to the effects of a blood alcohol level
of 0.05 percent. These findings underscore the occupational and safety
implications of sleep deprivation in high-stakes environments such as medicine,
aviation, and transportation.

CONCLUSION

Even a single episode of 24-hour sleep deprivation produces robust and
clinically significant impairments in working memory. Sleep hygiene
interventions should be treated as a public health priority.
""",
    ),
    BenchmarkCase(
        case_id="case_004",
        doi="10.0000/benchmark.hygiene.2024",
        claim="Enhanced hospital hand hygiene protocols reduce healthcare-acquired infections by 40%.",
        expected_evidence=(
            "implementation of enhanced hand hygiene protocols led to a 40 percent "
            "reduction in hospital-acquired infection rates"
        ),
        source_text="""\
ABSTRACT

Healthcare-associated infections impose a major burden on hospital systems.
This prospective study evaluates whether a multifaceted hand hygiene
improvement programme reduces hospital-acquired infection rates across
general wards in a tertiary care hospital.

INTRODUCTION

Hand hygiene is the single most effective intervention for preventing the
transmission of healthcare-associated pathogens. However, compliance rates
among healthcare workers typically fall below 50 percent in routine clinical
practice. Multifaceted intervention programmes combining education, audit
and feedback, and accessible alcohol-based hand rub have shown promise but
evidence from large-scale prospective studies remains limited.

METHODS

A 24-month prospective interrupted time-series study was conducted across
eight general wards in a 900-bed tertiary hospital. The intervention comprised
targeted staff education sessions, installation of bedside alcohol-based hand
rub dispensers, and monthly compliance audits with individualised feedback.
Hospital-acquired infection rates per 1,000 patient-days were tracked using
active microbiological surveillance.

RESULTS

Implementation of enhanced hand hygiene protocols led to a 40 percent
reduction in hospital-acquired infection rates compared to the pre-intervention
period. The largest reductions were observed for catheter-associated urinary
tract infections (52 percent) and surgical site infections (38 percent).
Hand hygiene compliance rates increased from 43 percent at baseline to 81
percent at 24 months.

DISCUSSION

A 40 percent reduction in hospital-acquired infections is clinically and
economically significant. Improved compliance was the primary driver, consistent
with the dose-response relationship established in prior literature. Sustained
improvement required ongoing audit feedback, suggesting that single-session
training alone is insufficient.

CONCLUSION

Multifaceted hand hygiene programmes substantially reduce hospital-acquired
infection burden. Continuous compliance monitoring and feedback are essential
components of any effective implementation strategy.
""",
    ),
    BenchmarkCase(
        case_id="case_005",
        doi="10.0000/benchmark.mediterranean.2024",
        claim="Mediterranean diet adherence reduces cognitive decline risk by 30% in elderly adults.",
        expected_evidence=(
            "elderly adults who adhered strictly to a Mediterranean dietary pattern "
            "showed a 30 percent reduction in cognitive decline risk"
        ),
        source_text="""\
ABSTRACT

Cognitive decline is a growing public health challenge as populations age.
This prospective cohort study examines the association between adherence to
a Mediterranean dietary pattern and the incidence of cognitive decline in
adults aged 65 and older over a 10-year follow-up period.

INTRODUCTION

Dietary patterns have emerged as modifiable risk factors for neurodegenerative
disease. The Mediterranean diet, characterised by high consumption of fruits,
vegetables, whole grains, legumes, olive oil, and fish, has been associated
with reduced cardiovascular risk and is hypothesised to exert neuroprotective
effects through anti-inflammatory and antioxidant mechanisms.

METHODS

A total of 4,500 community-dwelling adults aged 65 and above were enrolled at
baseline. Dietary intake was assessed using a validated food frequency
questionnaire, and a Mediterranean diet adherence score was computed. Cognitive
function was evaluated annually using the Mini-Mental State Examination and
the Montreal Cognitive Assessment. Incident cognitive decline was defined as
a decline of 3 or more points on either measure over 10 years. Covariates
including age, sex, education, physical activity, and baseline cognitive
function were adjusted for in multivariable analyses.

RESULTS

After 10 years of follow-up, elderly adults who adhered strictly to a
Mediterranean dietary pattern showed a 30 percent reduction in cognitive
decline risk compared to those with low adherence, after adjusting for all
covariates. The association was strongest for the fish, olive oil, and
vegetable components of the diet. No significant interaction was found by sex
or baseline cognitive status.

DISCUSSION

A 30 percent risk reduction represents a substantial effect for a dietary
intervention. The consistency of findings across cognitive domains and the
dose-response relationship between adherence score and outcome strengthen
the causal interpretation. However, residual confounding from unmeasured
lifestyle variables cannot be excluded in an observational design.

CONCLUSION

High adherence to the Mediterranean diet is associated with meaningfully
lower risk of cognitive decline in elderly adults. Dietary counselling
should be incorporated into cognitive ageing prevention programmes.
""",
    ),
]


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
            "running the benchmark."
        )
    return OpenAI(api_key=api_key, base_url=base_url)


def _embed_text(client: OpenAI, text: str) -> list[float]:
    """Embed a single text string and return its vector.

    Used to embed the claim before searching the vector store.

    Args:
        client: Authenticated OpenRouter-backed OpenAI client.
        text:   The text string to embed.

    Returns:
        A list of floats representing the embedding vector.
    """
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def _check_hit(
    top_chunks: list,
    expected_evidence: str,
) -> tuple[bool, int | None]:
    """Check whether the expected evidence phrase appears in the top-K results.

    Matching is case-insensitive substring search so minor whitespace differences
    between the original text and the chunk text do not cause false misses.

    Args:
        top_chunks:         Retrieved chunks from VectorStoreOutput.top_chunks.
        expected_evidence:  The phrase that must appear inside the correct chunk.

    Returns:
        A (hit, rank) tuple. `hit` is True if found; `rank` is the 1-based rank
        of the matching chunk, or None if not found in the top-K results.
    """
    # Collapse all whitespace (newlines, tabs, multiple spaces) to a single
    # space before comparing. Source texts have line-wrapped phrases, so the
    # chunk text may contain "\n" where the expected phrase has a space.
    def _normalise_ws(s: str) -> str:
        return re.sub(r"\s+", " ", s).lower().strip()

    needle = _normalise_ws(expected_evidence)
    for rc in top_chunks:
        if needle in _normalise_ws(rc.chunk.chunk_text):
            return True, rc.rank
    return False, None


# ── Pipeline runner ────────────────────────────────────────────────────────────


def _run_case(case: BenchmarkCase, client: OpenAI) -> CaseResult:
    """Run the full retrieval pipeline for one BenchmarkCase.

    Pipeline: clean_text → chunk_text → embed_chunks → embed claim → search.

    Args:
        case:   The benchmark test case to evaluate.
        client: Authenticated OpenRouter client for claim embedding.

    Returns:
        CaseResult with hit/miss outcome, rank, and top chunk previews.
    """
    logger.info("Running case %s: %s", case.case_id, case.claim[:60])

    # ── 1. Clean ───────────────────────────────────────────────────────────────
    cleaner_out = clean_text(
        CleanerInput(
            raw_text=case.source_text,
            evidence_availability=EvidenceAvailability.FULL_TEXT_AVAILABLE,
            doi=case.doi,
        )
    )

    # ── 2. Chunk ───────────────────────────────────────────────────────────────
    chunker_out = chunk_text(
        ChunkerInput(
            clean_text=cleaner_out.clean_text,
            doi=case.doi,
            evidence_availability=EvidenceAvailability.FULL_TEXT_AVAILABLE,
        )
    )

    if not chunker_out.chunks:
        logger.warning("Case %s produced 0 chunks — marking as miss.", case.case_id)
        return CaseResult(
            case_id=case.case_id,
            claim=case.claim,
            hit=False,
            rank_if_found=None,
            top_chunks=[],
            total_chunks_indexed=0,
        )

    # ── 3. Embed chunks ────────────────────────────────────────────────────────
    embedder_out = embed_chunks(
        EmbedderInput(chunks=chunker_out.chunks, doi=case.doi)
    )

    # ── 4. Embed claim ─────────────────────────────────────────────────────────
    claim_vector = _embed_text(client, case.claim)

    # ── 5. Search ──────────────────────────────────────────────────────────────
    store_out = search(
        VectorStoreInput(
            embedder_output=embedder_out,
            query_embedding=claim_vector,
            top_k=TOP_K,
        )
    )

    # ── 6. Check hit ───────────────────────────────────────────────────────────
    hit, rank = _check_hit(store_out.top_chunks, case.expected_evidence)

    previews = [
        TopChunkPreview(
            rank=rc.rank,
            section=rc.chunk.section,
            weighted_score=rc.weighted_score,
            text_preview=rc.chunk.chunk_text[:200],
        )
        for rc in store_out.top_chunks
    ]

    return CaseResult(
        case_id=case.case_id,
        claim=case.claim,
        hit=hit,
        rank_if_found=rank,
        top_chunks=previews,
        total_chunks_indexed=store_out.total_indexed,
    )


# ── Report I/O ─────────────────────────────────────────────────────────────────


def _save_report(
    report: BenchmarkReport,
    output_path: Path | None = None,
) -> Path:
    """Serialise the BenchmarkReport to JSON and write it to disk.

    Creates the parent directory if it does not exist.

    Args:
        report:      The completed benchmark report.
        output_path: Destination file path. Defaults to DEFAULT_OUTPUT_PATH.

    Returns:
        The path where the file was written.
    """
    if output_path is None:
        output_path = DEFAULT_OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Benchmark report saved to %s", output_path)
    return output_path


# ── Public entry point ─────────────────────────────────────────────────────────


def run_benchmark(output_path: Path | None = None) -> BenchmarkReport:
    """Run the full benchmark and return a BenchmarkReport.

    Iterates over BENCHMARK_CASES, runs the complete retrieval pipeline for
    each, collects hit/miss outcomes, and saves a JSON report.  Pipeline errors
    for individual cases are caught and recorded so the benchmark continues.

    Args:
        output_path: Where to save results JSON. Defaults to DEFAULT_OUTPUT_PATH.

    Returns:
        BenchmarkReport with per-case results and overall hit@K accuracy.
    """
    load_dotenv()
    client = _build_client()

    print(f"\nverifAi Retrieval Benchmark — hit@{TOP_K}\n{'─' * 44}")

    results: list[CaseResult] = []

    for case in BENCHMARK_CASES:
        try:
            result = _run_case(case, client)
        except Exception as exc:  # noqa: BLE001
            logger.error("Case %s raised an unexpected error: %s", case.case_id, exc)
            result = CaseResult(
                case_id=case.case_id,
                claim=case.claim,
                hit=False,
                rank_if_found=None,
                top_chunks=[],
                total_chunks_indexed=0,
                error=str(exc),
            )

        label = "HIT " if result.hit else "MISS"
        rank_str = f"(rank {result.rank_if_found})" if result.rank_if_found else ""
        print(f"  [{label}] {case.case_id}: {case.claim[:55]}… {rank_str}")
        results.append(result)

    total_hits = sum(1 for r in results if r.hit)
    total_errors = sum(1 for r in results if r.error is not None)
    accuracy = (total_hits / len(results) * 100) if results else 0.0

    report = BenchmarkReport(
        total_cases=len(results),
        total_hits=total_hits,
        total_errors=total_errors,
        accuracy_pct=round(accuracy, 1),
        top_k=TOP_K,
        embedding_model=EMBEDDING_MODEL,
        timestamp=datetime.now(timezone.utc).isoformat(),
        results=results,
    )

    saved_to = _save_report(report, output_path)

    print(f"\n{'─' * 44}")
    print(f"  Accuracy (hit@{TOP_K}): {report.accuracy_pct:.1f}%  "
          f"({total_hits}/{len(results)} hits)")
    if total_errors:
        print(f"  Errors:  {total_errors} case(s) failed — see {saved_to}")
    print(f"  Results: {saved_to}\n")

    return report


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_benchmark()
