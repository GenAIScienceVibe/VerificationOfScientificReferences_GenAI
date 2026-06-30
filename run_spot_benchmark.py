"""
Spot benchmark: run Door 1 + Door 2 for a specific subset of cases.

Usage:
    python run_spot_benchmark.py case_012 case_013
"""

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
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

DATASET_PATH = Path("data/evaluation/benchmark_dataset.json")

NEEDS_HUMAN_REVIEW_GTS = {"NEEDS_HUMAN_REVIEW"}


def verdicts_match(predicted: str, ground_truth: str) -> bool:
    if ground_truth in NEEDS_HUMAN_REVIEW_GTS:
        return predicted == "INSUFFICIENT_EVIDENCE"
    return predicted == ground_truth


def run(target_ids: set[str]) -> None:
    with open(DATASET_PATH, encoding="utf-8") as f:
        dataset = json.load(f)

    cases = [c for c in dataset["cases"] if c["case_id"] in target_ids]
    if not cases:
        print(f"No cases found for: {target_ids}")
        return

    print(f"\nSpot benchmark: {', '.join(sorted(target_ids))}")
    print("-" * 72)

    for case in cases:
        case_id = case["case_id"]
        claim_text = case["claim_text"]
        doi_status_raw = case["doi_status"]
        source_ev_raw = case["source_evidence"]
        metadata_raw = case.get("metadata", {})
        ground_truth = case["ground_truth_verdict"]
        claim_type = case["claim_type"]

        print(f"\n{case_id}  ({claim_type})")
        print(f"  Claim : {claim_text[:100]}{'...' if len(claim_text) > 100 else ''}")
        print(f"  GT    : {ground_truth}")

        # Door 1
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
        d1_req = RetrieveEvidenceRequest(
            claim_id=case["claim_id"],
            reference_id=case["reference_id"],
            claim_text=claim_text,
            citation_text=case.get("citation_text", ""),
            doi=case["doi"],
            doi_status=DoiStatus(doi_status_raw),
            source_evidence=source_evidence,
        )
        d1: RetrieveEvidenceResponse = retrieve_evidence(d1_req)
        print(f"  Door1 : {d1.retrieval_status.value}  chunks={len(d1.top_chunks)}  sim={d1.overall_similarity_score:.3f}")

        # Door 2
        d2_req = VerifyClaimRequest(
            claim_text=claim_text,
            citation_text=case.get("citation_text", ""),
            doi_status=DoiStatus(doi_status_raw),
            metadata=SourceMetadata(
                title=metadata_raw.get("title", ""),
                abstract=metadata_raw.get("abstract", ""),
            ),
            retrieved_evidence=[
                RetrievedEvidenceItem(
                    chunk_id=ch.chunk_id,
                    chunk_text=ch.chunk_text,
                    similarity_score=ch.similarity_score,
                )
                for ch in d1.top_chunks
            ],
            overall_similarity_score=d1.overall_similarity_score,
        )
        d2: VerifyClaimResponse = verify_claim(d2_req)

        matched = verdicts_match(d2.support_status.value, ground_truth)
        print(f"  Door2 : predicted={d2.support_status.value}  conf={d2.confidence:.2f}  "
              f"{'MATCH' if matched else 'MISMATCH'}")
        print(f"  evidence_used ({len(d2.evidence_used)} items): {d2.evidence_used}")
        # Check types
        all_strings = all(isinstance(e, str) for e in d2.evidence_used)
        print(f"  All string IDs: {all_strings}")
        if d2.limitations:
            print(f"  Limitations: {d2.limitations}")
        print(f"  Explanation: {d2.explanation[:200]}")

    print("\n" + "-" * 72)


if __name__ == "__main__":
    targets = set(sys.argv[1:]) if len(sys.argv) > 1 else {"case_012", "case_013"}
    run(targets)
