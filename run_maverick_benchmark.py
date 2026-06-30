"""
Temporary Maverick vs Scout comparison benchmark.

Runs all 16 active cases (skipping case_005 and case_016) through
meta-llama/llama-4-maverick via OpenRouter.  Uses the same Door 1
pipeline (Scout embeddings on OpenRouter) and the same verify.j2 prompt
as the main benchmark — only the LLM model and its client change.

Nothing in config.py or verifier.py is modified.  The override is done
locally inside _call_maverick() by building a second OpenAI client
pointed at OpenRouter with the Maverick model ID.

Run:
    python run_maverick_benchmark.py
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
logging.basicConfig(level=logging.ERROR)

# Suppress validator schema-error noise so output stays clean.
logging.getLogger("rag.verification.validator").setLevel(logging.CRITICAL)

import openai
from jinja2 import Environment, FileSystemLoader, select_autoescape

from rag.api import (
    DoiStatus,
    RetrieveEvidenceRequest,
    RetrieveEvidenceResponse,
    RetrievalStatus,
    retrieve_evidence,
)
from rag.ingestion.models import EvidenceAvailability, SourceEvidence
from rag.prompts.classifier import classify_citation_type
from rag.prompts.config import LLM_TEMPERATURE
from rag.prompts.verifier import SYSTEM_PROMPT, render_prompt
from rag.verification.models import VerificationInput, Verdict
from rag.verification.validator import validate_output
from rag.ingestion.chunker import count_tokens
from rag.ingestion.models import ChunkMetadata

# ── Config ────────────────────────────────────────────────────────────────────

DATASET_PATH  = Path("data/evaluation/benchmark_dataset.json")
RESULTS_PATH  = Path("data/evaluation/maverick_benchmark_results.json")
SKIP_CASES    = {"case_005", "case_016"}
MAVERICK_MODEL = "meta-llama/llama-4-maverick"
INTER_CASE_DELAY = 3   # seconds between cases

NEEDS_HUMAN_REVIEW_GTS = {"NEEDS_HUMAN_REVIEW"}

# ── Maverick client (OpenRouter) ──────────────────────────────────────────────

def _build_maverick_client() -> openai.OpenAI:
    api_key  = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not api_key:
        raise EnvironmentError("OPENROUTER_API_KEY is not set.")
    return openai.OpenAI(api_key=api_key, base_url=base_url)


def _call_maverick(client: openai.OpenAI, prompt: str) -> tuple[str | None, str]:
    """
    Call Maverick via OpenRouter.  Returns (content, flag) where flag is one of:
      "llm"           — genuine model response
      "null_content"  — finish_reason=stop but content was None
      "api_error"     — exception from OpenRouter
    """
    try:
        response = client.chat.completions.create(
            model=MAVERICK_MODEL,
            temperature=LLM_TEMPERATURE,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        content = response.choices[0].message.content
        if content is None:
            return None, "null_content"
        return content, "llm"
    except Exception as exc:
        return None, f"api_error:{exc}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _verdicts_match(predicted: str, ground_truth: str) -> bool:
    if ground_truth in NEEDS_HUMAN_REVIEW_GTS:
        return predicted == "INSUFFICIENT_EVIDENCE"
    return predicted == ground_truth


def _is_fallback(explanation: str) -> bool:
    return any(explanation.startswith(p) for p in (
        "DOI status is", "LLM verification call", "No evidence chunks",
    ))


# ── Main runner ───────────────────────────────────────────────────────────────

def run() -> None:
    with open(DATASET_PATH, encoding="utf-8") as f:
        dataset = json.load(f)

    active_cases = [c for c in dataset["cases"] if c["case_id"] not in SKIP_CASES]
    maverick_client = _build_maverick_client()

    print(f"\nMaverick Benchmark ({MAVERICK_MODEL})")
    print(f"  {len(active_cases)} active cases  |  skipping: {', '.join(sorted(SKIP_CASES))}")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print("-" * 72)

    results = []
    null_content_count = 0
    schema_error_count = 0
    api_error_count    = 0

    for i, case in enumerate(active_cases):
        case_id     = case["case_id"]
        claim_text  = case["claim_text"]
        doi_status_raw = case["doi_status"]
        source_ev_raw  = case["source_evidence"]
        metadata_raw   = case.get("metadata", {})
        ground_truth   = case["ground_truth_verdict"]
        claim_type     = case["claim_type"]

        print(f"\n[{i+1:02d}/{len(active_cases)}] {case_id}  ({claim_type})")
        print(f"  Claim : {claim_text[:90]}{'...' if len(claim_text) > 90 else ''}")
        print(f"  GT    : {ground_truth}")

        # ── Door 1 (identical to main benchmark — Scout embeddings) ───────────
        ev_avail_str = source_ev_raw.get("evidence_availability", "FULL_TEXT_AVAILABLE")
        try:
            ev_avail = EvidenceAvailability(ev_avail_str)
        except ValueError:
            ev_avail = EvidenceAvailability.FULL_TEXT_AVAILABLE

        d1_req = RetrieveEvidenceRequest(
            claim_id=case["claim_id"],
            reference_id=case["reference_id"],
            claim_text=claim_text,
            citation_text=case.get("citation_text", ""),
            doi=case["doi"],
            doi_status=DoiStatus(doi_status_raw),
            source_evidence=SourceEvidence(
                evidence_availability=ev_avail,
                text=source_ev_raw.get("text", ""),
                source_url=source_ev_raw.get("source_url", ""),
            ),
        )

        try:
            d1: RetrieveEvidenceResponse = retrieve_evidence(d1_req)
        except Exception as exc:
            print(f"  Door1 ERROR: {exc}")
            results.append({
                "case_id": case_id, "claim_type": claim_type,
                "ground_truth": ground_truth,
                "predicted": "INSUFFICIENT_EVIDENCE",
                "match": _verdicts_match("INSUFFICIENT_EVIDENCE", ground_truth),
                "confidence": 0.0, "human_review_required": True,
                "fallback": True, "fallback_reason": "door1_exception",
                "issue": str(exc),
            })
            continue

        print(f"  Door1 : {d1.retrieval_status.value}  "
              f"chunks={len(d1.top_chunks)}  sim={d1.overall_similarity_score:.3f}")

        # ── DOI-gate short-circuit (same rule as api.py) ──────────────────────
        if d1.retrieval_status != RetrievalStatus.SUCCEEDED:
            # INVALID / UNRESOLVABLE doi — map straight to INSUFFICIENT_EVIDENCE
            predicted = "INSUFFICIENT_EVIDENCE"
            matched   = _verdicts_match(predicted, ground_truth)
            print(f"  Door2 : doi-gate fallback -> {predicted}  "
                  f"{'MATCH' if matched else 'MISMATCH'}")
            results.append({
                "case_id": case_id, "claim_type": claim_type,
                "ground_truth": ground_truth, "predicted": predicted,
                "match": matched, "confidence": 0.0,
                "human_review_required": True,
                "fallback": True, "fallback_reason": "doi_gate", "issue": None,
            })
            if i < len(active_cases) - 1:
                time.sleep(INTER_CASE_DELAY)
            continue

        # ── Door 2 — Maverick LLM call (bypass api.py entirely) ───────────────
        # Step 1: classify citation type (same classifier as main pipeline)
        citation_type = classify_citation_type(claim_text)

        # Step 2: adapt chunks from Door 1 into ChunkMetadata for the prompt
        chunks = [
            ChunkMetadata(
                chunk_id=ch.chunk_id,
                section="unknown",
                priority=1.0,
                chunk_index=idx,
                paper_doi="",
                evidence_type="UNKNOWN",
                chunk_text=ch.chunk_text,
                token_count=count_tokens(ch.chunk_text),
            )
            for idx, ch in enumerate(d1.top_chunks)
        ]

        verification_input = VerificationInput(
            claim_text=claim_text,
            citation_type=citation_type.value,
            chunks=chunks,
            doi="",
        )

        # Step 3: render the prompt (same verify.j2 as Scout)
        prompt = render_prompt(verification_input)

        # Step 4: call Maverick
        raw_response, call_flag = _call_maverick(maverick_client, prompt)

        issue = None
        if call_flag == "null_content":
            null_content_count += 1
            issue = "null_content"
            print(f"  Door2 : NULL CONTENT from OpenRouter")
        elif call_flag.startswith("api_error"):
            api_error_count += 1
            issue = call_flag
            print(f"  Door2 : API ERROR — {call_flag}")

        # Step 5: validate (same validator as main pipeline)
        from rag.retrieval.vector_store import SIMILARITY_THRESHOLD
        low_confidence = d1.overall_similarity_score < SIMILARITY_THRESHOLD
        output = validate_output(raw_response, low_confidence=low_confidence)

        # Track schema errors: validator falls back to NEEDS_HUMAN_REVIEW when
        # it can't parse the response.
        if output.verdict == Verdict.NEEDS_HUMAN_REVIEW and raw_response is not None and issue is None:
            schema_error_count += 1
            issue = "schema_error"

        # Step 6: NEEDS_HUMAN_REVIEW -> INSUFFICIENT_EVIDENCE mapping (same as api.py)
        predicted = output.verdict.value
        if output.verdict == Verdict.NEEDS_HUMAN_REVIEW:
            predicted = Verdict.INSUFFICIENT_EVIDENCE.value

        matched = _verdicts_match(predicted, ground_truth)
        is_fb   = _is_fallback(output.explanation or "")
        fb_reason = "doi_gate" if is_fb and (output.explanation or "").startswith("DOI") else (
                    "llm_failure" if is_fb else None)

        flag_str = f"[{issue}]" if issue else "[llm]"
        print(f"  Door2 : predicted={predicted}  conf={output.confidence:.2f}  "
              f"{'MATCH' if matched else 'MISMATCH'}  {flag_str}")

        results.append({
            "case_id": case_id, "claim_type": claim_type,
            "ground_truth": ground_truth, "predicted": predicted,
            "match": matched, "confidence": output.confidence,
            "human_review_required": output.human_review_required,
            "fallback": is_fb or issue is not None,
            "fallback_reason": fb_reason or issue,
            "issue": issue,
            "explanation": (output.explanation or "")[:200],
        })

        if i < len(active_cases) - 1:
            time.sleep(INTER_CASE_DELAY)

    # ── Aggregate stats ───────────────────────────────────────────────────────
    n       = len(results)
    n_match = sum(1 for r in results if r["match"])
    overall = n_match / n * 100 if n else 0.0

    verdict_total: dict[str, int] = defaultdict(int)
    verdict_match: dict[str, int] = defaultdict(int)
    for r in results:
        verdict_total[r["ground_truth"]] += 1
        if r["match"]:
            verdict_match[r["ground_truth"]] += 1

    n_genuine  = sum(1 for r in results if not r["fallback"] and not r["issue"])
    n_doi_gate = sum(1 for r in results if r.get("fallback_reason") == "doi_gate")
    n_null     = null_content_count
    n_schema   = schema_error_count
    n_api_err  = api_error_count

    # ── Report ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print(f"  MAVERICK BENCHMARK REPORT  ({MAVERICK_MODEL})")
    print("=" * 72)
    print(f"\n  Overall accuracy : {n_match}/{n}  ({overall:.1f}%)")

    print(f"\n  Response quality breakdown:")
    print(f"    Genuine LLM verdicts   : {n_genuine}/{n}")
    print(f"    DOI-gate fallbacks     : {n_doi_gate}/{n}   (INVALID/UNRESOLVABLE -> INSUFFICIENT_EVIDENCE)")
    print(f"    Null-content (OpenRouter) : {n_null}/{n}")
    print(f"    Malformed JSON / schema   : {n_schema}/{n}")
    print(f"    API errors                : {n_api_err}/{n}")

    print(f"\n  Per-verdict accuracy:")
    for v in sorted(verdict_total):
        t   = verdict_total[v]
        m   = verdict_match[v]
        pct = m / t * 100 if t else 0.0
        print(f"    {v:<28} {m}/{t}  ({pct:.0f}%)")

    print(f"\n  Match/Mismatch table:")
    print(f"  {'Case':<12} {'Type':<18} {'GT Verdict':<26} {'Predicted':<26} {'Conf':>5}  {'Result':<10}  {'Source'}")
    print("  " + "-" * 108)
    for r in results:
        status = "MATCH   " if r["match"] else "MISMATCH"
        source = r.get("fallback_reason") or r.get("issue") or "llm"
        gt_display = r["ground_truth"]
        if gt_display == "NEEDS_HUMAN_REVIEW":
            gt_display += " (->INSUFF)"
        print(f"  {r['case_id']:<12} {r['claim_type']:<18} {gt_display:<26} "
              f"{r['predicted']:<26} {r['confidence']:>5.2f}  {status:<10}  {source}")

    # ── Save JSON ─────────────────────────────────────────────────────────────
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": MAVERICK_MODEL,
        "provider": "OpenRouter",
        "n_active_cases": n,
        "skipped_cases": sorted(SKIP_CASES),
        "overall_accuracy_pct": round(overall, 1),
        "n_match": n_match,
        "n_genuine_llm": n_genuine,
        "n_doi_gate_fallback": n_doi_gate,
        "n_null_content": n_null,
        "n_schema_error": n_schema,
        "n_api_error": n_api_err,
        "per_verdict_accuracy": {
            v: {"match": verdict_match[v], "total": verdict_total[v]}
            for v in sorted(verdict_total)
        },
        "results": results,
    }
    RESULTS_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n  Results saved -> {RESULTS_PATH}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    run()
