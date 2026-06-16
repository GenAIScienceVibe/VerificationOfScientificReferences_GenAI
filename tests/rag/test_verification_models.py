"""
Unit tests for rag/verification/models.py (SCRUM-194).

Checks that the Pydantic schema matches the backend Door 2 contract exactly:
the five verdict labels, required fields, and validation bounds.
"""

import pytest
from pydantic import ValidationError

from rag.ingestion.models import ChunkMetadata
from rag.verification.models import Verdict, VerificationInput, VerificationOutput


# ── Fixtures and helpers ──────────────────────────────────────────────────────


def make_chunk(index: int = 0) -> ChunkMetadata:
    """Build a minimal ChunkMetadata for testing."""
    return ChunkMetadata(
        chunk_id=f"10_0000_test_chunk_{index:03d}",
        section="results",
        priority=1.3,
        chunk_index=index,
        paper_doi="10.0000/test.2024",
        evidence_type="FULL_TEXT",
        chunk_text="participants showed a 28% reduction...",
        token_count=6,
    )


# ── Verdict enum ───────────────────────────────────────────────────────────────


def test_verdict_has_exactly_five_labels():
    assert {v.value for v in Verdict} == {
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "NOT_SUPPORTED",
        "INSUFFICIENT_EVIDENCE",
        "NEEDS_HUMAN_REVIEW",
    }


def test_verdict_values_match_backend_strings_exactly():
    assert Verdict.SUPPORTED.value == "SUPPORTED"
    assert Verdict.PARTIALLY_SUPPORTED.value == "PARTIALLY_SUPPORTED"
    assert Verdict.NOT_SUPPORTED.value == "NOT_SUPPORTED"
    assert Verdict.INSUFFICIENT_EVIDENCE.value == "INSUFFICIENT_EVIDENCE"
    assert Verdict.NEEDS_HUMAN_REVIEW.value == "NEEDS_HUMAN_REVIEW"


def test_verdict_rejects_unknown_label():
    with pytest.raises(ValueError):
        Verdict("MADE_UP_LABEL")


# ── VerificationInput ────────────────────────────────────────────────────────


def test_verification_input_accepts_valid_payload():
    vi = VerificationInput(
        claim_text="Exercise reduces heart disease risk",
        citation_type="RESULT_COMPARISON",
        chunks=[make_chunk(0), make_chunk(1)],
        doi="10.1234/example.2019.001",
    )
    assert vi.claim_text == "Exercise reduces heart disease risk"
    assert vi.citation_type == "RESULT_COMPARISON"
    assert len(vi.chunks) == 2
    assert vi.doi == "10.1234/example.2019.001"


def test_verification_input_accepts_empty_chunks_list():
    vi = VerificationInput(
        claim_text="Some claim",
        citation_type="BACKGROUND",
        chunks=[],
        doi="10.1234/example.2019.001",
    )
    assert vi.chunks == []


@pytest.mark.parametrize("missing_field", ["claim_text", "citation_type", "chunks", "doi"])
def test_verification_input_requires_all_fields(missing_field):
    payload = {
        "claim_text": "Some claim",
        "citation_type": "METHOD",
        "chunks": [make_chunk(0)],
        "doi": "10.1234/example.2019.001",
    }
    del payload[missing_field]
    with pytest.raises(ValidationError):
        VerificationInput(**payload)


# ── VerificationOutput ───────────────────────────────────────────────────────


def test_verification_output_accepts_valid_payload():
    out = VerificationOutput(
        verdict=Verdict.PARTIALLY_SUPPORTED,
        confidence=0.72,
        explanation="The source reports 28% reduction, not 35% as claimed.",
        evidence_used=["10_0000_test_chunk_000"],
        limitations="Only abstract-level evidence was available.",
        human_review_required=True,
    )
    assert out.verdict == Verdict.PARTIALLY_SUPPORTED
    assert out.confidence == 0.72
    assert out.human_review_required is True


def test_verification_output_accepts_string_verdict():
    """Pydantic should coerce a plain string into the Verdict enum."""
    out = VerificationOutput(
        verdict="SUPPORTED",
        confidence=0.9,
        explanation="Matches.",
        human_review_required=False,
    )
    assert out.verdict == Verdict.SUPPORTED


def test_verification_output_defaults_evidence_used_and_limitations():
    out = VerificationOutput(
        verdict=Verdict.INSUFFICIENT_EVIDENCE,
        confidence=0.0,
        explanation="No evidence retrieved.",
        human_review_required=False,
    )
    assert out.evidence_used == []
    assert out.limitations is None


@pytest.mark.parametrize("bad_confidence", [-0.01, 1.01, -1.0, 2.0])
def test_verification_output_rejects_confidence_out_of_bounds(bad_confidence):
    with pytest.raises(ValidationError):
        VerificationOutput(
            verdict=Verdict.SUPPORTED,
            confidence=bad_confidence,
            explanation="x",
            human_review_required=False,
        )


@pytest.mark.parametrize("boundary_confidence", [0.0, 1.0])
def test_verification_output_accepts_confidence_boundaries(boundary_confidence):
    out = VerificationOutput(
        verdict=Verdict.SUPPORTED,
        confidence=boundary_confidence,
        explanation="x",
        human_review_required=False,
    )
    assert out.confidence == boundary_confidence


def test_verification_output_rejects_invalid_verdict_string():
    with pytest.raises(ValidationError):
        VerificationOutput(
            verdict="MAYBE_SUPPORTED",
            confidence=0.5,
            explanation="x",
            human_review_required=False,
        )


@pytest.mark.parametrize("missing_field", ["verdict", "confidence", "explanation", "human_review_required"])
def test_verification_output_requires_all_mandatory_fields(missing_field):
    payload = {
        "verdict": Verdict.SUPPORTED,
        "confidence": 0.8,
        "explanation": "x",
        "human_review_required": False,
    }
    del payload[missing_field]
    with pytest.raises(ValidationError):
        VerificationOutput(**payload)
