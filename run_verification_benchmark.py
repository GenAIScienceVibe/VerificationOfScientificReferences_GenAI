"""
End-to-end verification benchmark runner.

Loads benchmark_dataset.json, runs Door 1 + Door 2 for each active case
(skipping case_005 and case_016), and prints a full results report:
  - Overall accuracy
  - Per-verdict accuracy
  - Per-citation-type accuracy
  - Match/mismatch table
  - Verdict-type breakdown (genuine LLM vs fallback)

Run:
    python run_verification_benchmark.py
"""

import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Silence noisy loggers — we control our own output.
logging.basicConfig(level=logging.ERROR)

from rag.api import (
    DoiStatus,
    RetrieveEvidenceRequest,
    RetrieveEvidenceResponse,
    RetrievalStatus,
    RetrievedEvidenceItem,
    SourceMetadata,
    VerifyClaimRequest,
    VerifyClaimResponse,
    retrieve_evidence,
    verify_claim,
)
from rag.ingestion.models import EvidenceAvailability, SourceEvidence

# ── Config ────────────────────────────────────────────────────────────────────

DATASET_PATH = Path("data/evaluation/benchmark_dataset.json")
RESULTS_PATH = Path("data/evaluation/verification_benchmark_results.json")
SKIP_CASES = {"case_005", "case_016"}

# Delay between cases to avoid hammering rate limits.
INTER_CASE_DELAY_SECONDS = 2

# ── Verdict categorisation ────────────────────────────────────────────────────

# Verdicts returned by _insufficient_evidence() or _needs_human_review()
# in api.py — these are fallback paths, not genuine LLM verdicts.
# We detect them by checking the explanation prefix produced by those helpers.
FALLBACK_EXPLANATIONS = (
    "DOI status is",          # _insufficient_evidence — doi-gate
    "LLM verification call",  # _needs_human_review — LLM failure
    "No evidence chunks",     # _needs_human_review — empty retrieval
)

NEEDS_HUMAN_REVIEW_GROUND_TRUTHS = {"NEEDS_HUMAN_REVIEW"}


def _is_fallback(response: VerifyClaimResponse) -> bool:
    """Return True if this response came from a fallback path, not the LLM."""
    exp = response.explanation or ""
    return any(exp.startswith(prefix) for prefix in FALLBACK_EXPLANATIONS)


def _fallback_reason(response: VerifyClaimResponse) -> str:
    exp = response.explanation or ""
    if exp.startswith("DOI status is"):
        return "doi_gate"
    if exp.startswith("LLM verification call"):
        return "llm_failure"
    return "other_fallback"


# ── Match logic ───────────────────────────────────────────────────────────────

def _verdicts_match(predicted: str, ground_truth: str) -> bool:
    """
    Return True if predicted verdict matches ground truth.

    NEEDS_HUMAN_REVIEW in the ground truth is treated as matching
    INSUFFICIENT_EVIDENCE in the predicted output, because the pipeline
    maps NEEDS_HUMAN_REVIEW -> INSUFFICIENT_EVIDENCE at the API layer.
    """
    if ground_truth in NEEDS_HUMAN_REVIEW_GROUND_TRUTHS:
        return predicted == "INSUFFICIENT_EVIDENCE"
    return predicted == ground_truth


# ── Main runner ───────────────────────────────────────────────────────────────

def run() -> None:
    with open(DATASET_PATH, encoding="utf-8") as f:
        dataset = json.load(f)

    all_cases = dataset["cases"]
    active_cases = [c for c in all_cases if c["case_id"] not in SKIP_CASES]

    print(f"\nverifAi Verification Benchmark — {len(active_cases)} active cases")
    print(f"  Dataset: {dataset['dataset_name']} v{dataset['version']}")
    print(f"  Skipping: {', '.join(sorted(SKIP_CASES))}")
    print(f"  Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print("-" * 72)

    results = []

    for i, case in enumerate(active_cases):
        case_id = case["case_id"]
        claim_text = case["claim_text"]
        doi = case["doi"]
        doi_status_raw = case["doi_status"]
        source_ev_raw = case["source_evidence"]
        metadata_raw = case.get("metadata", {})
        ground_truth = case["ground_truth_verdict"]
        claim_type = case["claim_type"]

        print(f"\n[{i+1:02d}/{len(active_cases)}] {case_id}  ({claim_type})")
        print(f"  Claim : {claim_text[:90]}{'…' if len(claim_text) > 90 else ''}")
        print(f"  GT    : {ground_truth}")

        # ── Door 1 ────────────────────────────────────────────────────────────
        try:
            ev_avail_str = source_ev_raw.get("evidence_availability", "FULL_TEXT_AVAILABLE")
            try:
                ev_avail = EvidenceAvailability(ev_avail_str)
            except ValueError:
                ev_avail = EvidenceAvailability.FULL_TEXT_AVAILABLE

            source_evidence = SourceEvidence(
                evidence_availability=ev_avail,
                text=source_ev_raw.get("text", ""),
                source_url=source_ev_raw.get("source_url", ""),
            )

            d1_request = RetrieveEvidenceRequest(
                claim_id=case["claim_id"],
                reference_id=case["reference_id"],
                claim_text=claim_text,
                citation_text=case.get("citation_text", ""),
                doi=doi,
                doi_status=DoiStatus(doi_status_raw),
                source_evidence=source_evidence,
            )
            d1_response: RetrieveEvidenceResponse = retrieve_evidence(d1_request)
        except Exception as exc:
            print(f"  Door1 ERROR: {exc}")
            results.append({
                "case_id": case_id,
                "claim_type": claim_type,
                "ground_truth": ground_truth,
                "predicted": "INSUFFICIENT_EVIDENCE",
                "match": _verdicts_match("INSUFFICIENT_EVIDENCE", ground_truth),
                "confidence": 0.0,
                "human_review_required": True,
                "fallback": True,
                "fallback_reason": "door1_exception",
                "explanation": str(exc),
            })
            continue

        retrieval_ok = d1_response.retrieval_status == RetrievalStatus.SUCCEEDED
        print(f"  Door1 : {d1_response.retrieval_status.value}  "
              f"chunks={len(d1_response.top_chunks)}  "
              f"sim={d1_response.overall_similarity_score:.3f}")

        # ── Door 2 ────────────────────────────────────────────────────────────
        retrieved_evidence = [
            RetrievedEvidenceItem(
                chunk_id=ch.chunk_id,
                chunk_text=ch.chunk_text,
                similarity_score=ch.similarity_score,
            )
            for ch in d1_response.top_chunks
        ]

        d2_request = VerifyClaimRequest(
            claim_text=claim_text,
            citation_text=case.get("citation_text", ""),
            doi_status=DoiStatus(doi_status_raw),
            metadata=SourceMetadata(
                title=metadata_raw.get("title", ""),
                abstract=metadata_raw.get("abstract", ""),
            ),
            retrieved_evidence=retrieved_evidence,
            overall_similarity_score=d1_response.overall_similarity_score,
        )

        try:
            d2_response: VerifyClaimResponse = verify_claim(d2_request)
        except Exception as exc:
            print(f"  Door2 ERROR: {exc}")
            results.append({
                "case_id": case_id,
                "claim_type": claim_type,
                "ground_truth": ground_truth,
                "predicted": "INSUFFICIENT_EVIDENCE",
                "match": _verdicts_match("INSUFFICIENT_EVIDENCE", ground_truth),
                "confidence": 0.0,
                "human_review_required": True,
                "fallback": True,
                "fallback_reason": "door2_exception",
                "explanation": str(exc),
            })
            continue

        predicted = d2_response.support_status.value
        matched = _verdicts_match(predicted, ground_truth)
        is_fallback = _is_fallback(d2_response)
        fb_reason = _fallback_reason(d2_response) if is_fallback else None

        match_str = "MATCH   " if matched else "MISMATCH"
        fallback_tag = f" [fallback:{fb_reason}]" if is_fallback else " [llm]"
        print(f"  Door2 : predicted={predicted}  conf={d2_response.confidence:.2f}  "
              f"{match_str}{fallback_tag}")

        results.append({
            "case_id": case_id,
            "claim_type": claim_type,
            "ground_truth": ground_truth,
            "predicted": predicted,
            "match": matched,
            "confidence": d2_response.confidence,
            "human_review_required": d2_response.human_review_required,
            "fallback": is_fallback,
            "fallback_reason": fb_reason,
            "explanation": d2_response.explanation[:200] if d2_response.explanation else "",
        })

        if i < len(active_cases) - 1:
            time.sleep(INTER_CASE_DELAY_SECONDS)

    # ── Aggregate stats ───────────────────────────────────────────────────────
    n = len(results)
    n_match = sum(1 for r in results if r["match"])
    overall_acc = n_match / n * 100 if n else 0.0

    # per-verdict
    verdict_total: dict[str, int] = defaultdict(int)
    verdict_match: dict[str, int] = defaultdict(int)
    for r in results:
        gt = r["ground_truth"]
        verdict_total[gt] += 1
        if r["match"]:
            verdict_match[gt] += 1

    # per-citation-type
    type_total: dict[str, int] = defaultdict(int)
    type_match: dict[str, int] = defaultdict(int)
    for r in results:
        ct = r["claim_type"]
        type_total[ct] += 1
        if r["match"]:
            type_match[ct] += 1

    # fallback breakdown
    n_genuine = sum(1 for r in results if not r["fallback"])
    n_doi_gate = sum(1 for r in results if r["fallback_reason"] == "doi_gate")
    n_llm_fail = sum(1 for r in results if r["fallback_reason"] == "llm_failure")
    n_other_fb = sum(1 for r in results if r["fallback"] and r["fallback_reason"] not in ("doi_gate", "llm_failure"))

    # ── Print report ──────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  VERIFICATION BENCHMARK REPORT")
    print("=" * 72)

    print(f"\n  Overall accuracy : {n_match}/{n}  ({overall_acc:.1f}%)")

    print(f"\n  Verdict breakdown (genuine LLM vs fallback):")
    print(f"    Genuine LLM verdicts : {n_genuine}/{n}")
    print(f"    DOI-gate fallbacks   : {n_doi_gate}/{n}   (doi_status INVALID/UNRESOLVABLE → INSUFFICIENT_EVIDENCE)")
    print(f"    LLM-failure fallbacks: {n_llm_fail}/{n}   (call failed or null content → INSUFFICIENT_EVIDENCE)")
    print(f"    Other fallbacks      : {n_other_fb}/{n}")

    print(f"\n  Per-verdict accuracy:")
    for verdict in sorted(verdict_total):
        t = verdict_total[verdict]
        m = verdict_match[verdict]
        pct = m / t * 100 if t else 0.0
        print(f"    {verdict:<28} {m}/{t}  ({pct:.0f}%)")

    print(f"\n  Per-citation-type accuracy:")
    for ct in sorted(type_total):
        t = type_total[ct]
        m = type_match[ct]
        pct = m / t * 100 if t else 0.0
        print(f"    {ct:<20} {m}/{t}  ({pct:.0f}%)")

    print(f"\n  Match/Mismatch table:")
    print(f"  {'Case':<12} {'Type':<18} {'GT Verdict':<26} {'Predicted':<26} {'Conf':>5}  {'Verdict':<10}  {'Source'}")
    print("  " + "-" * 110)
    for r in results:
        status = "MATCH   " if r["match"] else "MISMATCH"
        source = "fallback:" + r["fallback_reason"] if r["fallback"] else "llm"
        gt_display = r["ground_truth"]
        # Show the mapping note for NEEDS_HUMAN_REVIEW ground truths
        if gt_display == "NEEDS_HUMAN_REVIEW":
            gt_display += " (→INSUFF)"
        print(f"  {r['case_id']:<12} {r['claim_type']:<18} {gt_display:<26} {r['predicted']:<26} {r['confidence']:>5.2f}  {status:<10}  {source}")

    # ── Save JSON ─────────────────────────────────────────────────────────────
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset.get("version"),
        "n_active_cases": n,
        "skipped_cases": sorted(SKIP_CASES),
        "overall_accuracy_pct": round(overall_acc, 1),
        "n_match": n_match,
        "n_genuine_llm": n_genuine,
        "n_doi_gate_fallback": n_doi_gate,
        "n_llm_failure_fallback": n_llm_fail,
        "n_other_fallback": n_other_fb,
        "per_verdict_accuracy": {
            v: {"match": verdict_match[v], "total": verdict_total[v]}
            for v in sorted(verdict_total)
        },
        "per_citation_type_accuracy": {
            ct: {"match": type_match[ct], "total": type_total[ct]}
            for ct in sorted(type_total)
        },
        "results": results,
    }
    RESULTS_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Results saved -> {RESULTS_PATH}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    run()
