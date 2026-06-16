"""
Unit tests for rag/api.py — the backend integration handoff layer.

These tests mock the pipeline functions that retrieve_evidence() and
verify_claim() wire together (clean_text, chunk_text, embed_chunks, search,
classify_citation_type, generate_verdict) at the points where rag.api
imports them, so each test exercises api.py's own orchestration logic
(branching, field mapping, fallback handling) rather than re-testing the
modules those functions belong to — those already have their own test
suites. validate_output() is left unmocked in the success path so the
full Door 2 chain (LLM string -> validated VerificationOutput -> response
model) is exercised end to end.
"""

from unittest.mock import patch

import pytest

from rag.api import (
    DoiStatus,
    RetrievalStatus,
    RetrieveEvidenceRequest,
    SourceMetadata,
    RetrievedEvidenceItem,
    VerifyClaimRequest,
    retrieve_evidence,
    verify_claim,
)
from rag.ingestion.models import (
    ChunkerOutput,
    ChunkMetadata,
    CleanerOutput,
    EvidenceAvailability,
    SourceEvidence,
)
from rag.prompts.classifier import CitationType
from rag.retrieval.models import EmbeddedChunk, EmbedderOutput, RetrievedChunk, VectorStoreOutput
from rag.verification.models import Verdict


# ── Fixtures and helpers ──────────────────────────────────────────────────────


def make_chunk(index: int, section: str = "results", text: str = "participants showed a 28% reduction...") -> ChunkMetadata:
    """Build a minimal ChunkMetadata for testing."""
    return ChunkMetadata(
        chunk_id=f"10_1234_example_2019_chunk_{index:03d}",
        section=section,
        priority=1.3,
        chunk_index=index,
        paper_doi="10.1234/example.2019.001",
        evidence_type="ABSTRACT",
        chunk_text=text,
        token_count=6,
    )


def fake_embed_chunks(input_data):
    """Stand-in for embed_chunks(): pairs every input chunk with a fixed vector."""
    embedded = [EmbeddedChunk(chunk=c, embedding=[0.1, 0.2]) for c in input_data.chunks]
    return EmbedderOutput(
        doi=input_data.doi,
        embedded_chunks=embedded,
        total_embedded=len(embedded),
        embedding_model="fake-model",
        embedding_dimensions=2,
    )


def make_door1_request(doi_status: DoiStatus = DoiStatus.VALID) -> RetrieveEvidenceRequest:
    """Build a Door 1 request matching the CLAUDE.md example payload."""
    return RetrieveEvidenceRequest(
        claim_id="claim_001",
        reference_id="ref_001",
        claim_text="Exercise reduces heart disease risk by 35%",
        citation_text="(Johnson et al., 2019)",
        doi="10.1234/example.2019.001",
        doi_status=doi_status,
        source_evidence=SourceEvidence(
            evidence_availability=EvidenceAvailability.ABSTRACT_AVAILABLE,
            text="Abstract text of the source paper...",
            source_url="https://doi.org/10.1234/example.2019.001",
        ),
    )


def make_door2_request(
    doi_status: DoiStatus = DoiStatus.VALID, overall_similarity_score: float = 0.82
) -> VerifyClaimRequest:
    """Build a Door 2 request matching the CLAUDE.md example payload."""
    return VerifyClaimRequest(
        claim_text="Exercise reduces heart disease risk by 35%",
        citation_text="(Johnson et al., 2019)",
        doi_status=doi_status,
        metadata=SourceMetadata(
            title="Cardiovascular effects of exercise",
            abstract="Abstract text...",
        ),
        retrieved_evidence=[
            RetrievedEvidenceItem(
                chunk_id="chunk_001",
                chunk_text="participants showed a 28% reduction...",
                similarity_score=0.84,
            )
        ],
        overall_similarity_score=overall_similarity_score,
    )


# ── Door 1: retrieve_evidence() ───────────────────────────────────────────────


def test_retrieve_evidence_success():
    """Full Door 1 flow with all pipeline steps mocked returns SUCCEEDED with ranked chunks."""
    chunk1, chunk2 = make_chunk(0), make_chunk(1)
    vector_output = VectorStoreOutput(
        doi="10.1234/example.2019.001",
        top_chunks=[
            RetrievedChunk(chunk=chunk1, raw_score=0.9, weighted_score=0.9, rank=1),
            RetrievedChunk(chunk=chunk2, raw_score=0.7, weighted_score=0.7, rank=2),
        ],
        total_indexed=2,
        retrieved_k=2,
        low_confidence=False,
    )

    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=fake_embed_chunks),
        patch("rag.api.search", return_value=vector_output),
    ):
        mock_clean.return_value = CleanerOutput(
            clean_text="cleaned text",
            doi="10.1234/example.2019.001",
            evidence_availability=EvidenceAvailability.ABSTRACT_AVAILABLE,
            original_length=20,
            cleaned_length=12,
        )
        mock_chunk.return_value = ChunkerOutput(
            doi="10.1234/example.2019.001",
            chunks=[chunk1, chunk2],
            total_chunks=2,
            sections_found=["results"],
            fallback_used=False,
        )

        response = retrieve_evidence(make_door1_request())

    assert response.claim_id == "claim_001"
    assert response.reference_id == "ref_001"
    assert response.retrieval_status == RetrievalStatus.SUCCEEDED
    assert len(response.top_chunks) == 2
    assert response.top_chunks[0].chunk_id == chunk1.chunk_id
    assert response.top_chunks[0].similarity_score == 0.9
    assert response.overall_similarity_score == 0.9
    assert response.retrieval_confidence == pytest.approx(0.8)


def test_retrieve_evidence_invalid_doi_skips_pipeline():
    """INVALID doi_status returns FAILED immediately without touching the pipeline."""
    with patch("rag.api.clean_text", side_effect=AssertionError("pipeline must not run")):
        response = retrieve_evidence(make_door1_request(doi_status=DoiStatus.INVALID))

    assert response.retrieval_status == RetrievalStatus.FAILED
    assert response.top_chunks == []


def test_retrieve_evidence_unresolvable_doi_skips_pipeline():
    """UNRESOLVABLE doi_status also returns FAILED immediately."""
    with patch("rag.api.clean_text", side_effect=AssertionError("pipeline must not run")):
        response = retrieve_evidence(make_door1_request(doi_status=DoiStatus.UNRESOLVABLE))

    assert response.retrieval_status == RetrievalStatus.FAILED


def test_retrieve_evidence_no_chunks_returns_failed():
    """Zero chunks from chunk_text() returns FAILED without calling embed_chunks/search."""
    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks") as mock_embed,
        patch("rag.api.search") as mock_search,
    ):
        mock_clean.return_value = CleanerOutput(
            clean_text="",
            doi="10.1234/example.2019.001",
            evidence_availability=EvidenceAvailability.ABSTRACT_AVAILABLE,
            original_length=0,
            cleaned_length=0,
        )
        mock_chunk.return_value = ChunkerOutput(
            doi="10.1234/example.2019.001",
            chunks=[],
            total_chunks=0,
            sections_found=[],
            fallback_used=True,
        )

        response = retrieve_evidence(make_door1_request())

        mock_embed.assert_not_called()
        mock_search.assert_not_called()

    assert response.retrieval_status == RetrievalStatus.FAILED


def test_retrieve_evidence_pipeline_exception_returns_failed():
    """An exception from embed_chunks() (e.g. missing API key) is caught and returns FAILED."""
    chunk1 = make_chunk(0)
    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=EnvironmentError("OPENROUTER_API_KEY is not set")),
        patch("rag.api.search") as mock_search,
    ):
        mock_clean.return_value = CleanerOutput(
            clean_text="cleaned text",
            doi="10.1234/example.2019.001",
            evidence_availability=EvidenceAvailability.ABSTRACT_AVAILABLE,
            original_length=20,
            cleaned_length=12,
        )
        mock_chunk.return_value = ChunkerOutput(
            doi="10.1234/example.2019.001",
            chunks=[chunk1],
            total_chunks=1,
            sections_found=["results"],
            fallback_used=False,
        )

        response = retrieve_evidence(make_door1_request())

        mock_search.assert_not_called()

    assert response.retrieval_status == RetrievalStatus.FAILED


def test_retrieve_evidence_empty_search_results_returns_failed():
    """search() returning zero top_chunks (e.g. empty index) returns FAILED."""
    chunk1 = make_chunk(0)
    empty_vector_output = VectorStoreOutput(
        doi="10.1234/example.2019.001", top_chunks=[], total_indexed=0, retrieved_k=0
    )

    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=fake_embed_chunks),
        patch("rag.api.search", return_value=empty_vector_output),
    ):
        mock_clean.return_value = CleanerOutput(
            clean_text="cleaned text",
            doi="10.1234/example.2019.001",
            evidence_availability=EvidenceAvailability.ABSTRACT_AVAILABLE,
            original_length=20,
            cleaned_length=12,
        )
        mock_chunk.return_value = ChunkerOutput(
            doi="10.1234/example.2019.001",
            chunks=[chunk1],
            total_chunks=1,
            sections_found=["results"],
            fallback_used=False,
        )

        response = retrieve_evidence(make_door1_request())

    assert response.retrieval_status == RetrievalStatus.FAILED


# ── Door 2: verify_claim() ────────────────────────────────────────────────────


def test_verify_claim_success():
    """Full Door 2 flow with classifier/LLM mocked, validate_output() run for real."""
    raw_json = (
        '{"verdict": "SUPPORTED", "confidence": 0.9, '
        '"explanation": "1. Claim says X. 2. Evidence says X. 3. They match. 4. Supported.", '
        '"evidence_used": ["chunk_001"], "limitations": null}'
    )

    with (
        patch("rag.api.classify_citation_type", return_value=CitationType.RESULT_COMPARISON),
        patch("rag.api.generate_verdict", return_value=raw_json) as mock_generate,
    ):
        response = verify_claim(make_door2_request(overall_similarity_score=0.82))

    mock_generate.assert_called_once()
    assert response.support_status == Verdict.SUPPORTED
    assert response.confidence == 0.9
    assert response.evidence_used == ["chunk_001"]
    assert response.human_review_required is False


def test_verify_claim_invalid_doi_skips_pipeline():
    """INVALID doi_status returns INSUFFICIENT_EVIDENCE immediately, no LLM calls."""
    with (
        patch("rag.api.classify_citation_type", side_effect=AssertionError("must not run")),
        patch("rag.api.generate_verdict", side_effect=AssertionError("must not run")),
    ):
        response = verify_claim(make_door2_request(doi_status=DoiStatus.INVALID))

    assert response.support_status == Verdict.INSUFFICIENT_EVIDENCE
    assert response.human_review_required is False


def test_verify_claim_unresolvable_doi_skips_pipeline():
    """UNRESOLVABLE doi_status also returns INSUFFICIENT_EVIDENCE immediately."""
    with (
        patch("rag.api.classify_citation_type", side_effect=AssertionError("must not run")),
        patch("rag.api.generate_verdict", side_effect=AssertionError("must not run")),
    ):
        response = verify_claim(make_door2_request(doi_status=DoiStatus.UNRESOLVABLE))

    assert response.support_status == Verdict.INSUFFICIENT_EVIDENCE


def test_verify_claim_llm_failure_falls_back_to_needs_human_review():
    """An exception from generate_verdict() is caught and converted to NEEDS_HUMAN_REVIEW."""
    with (
        patch("rag.api.classify_citation_type", return_value=CitationType.BACKGROUND),
        patch("rag.api.generate_verdict", side_effect=Exception("LLM call failed")),
    ):
        response = verify_claim(make_door2_request())

    assert response.support_status == Verdict.NEEDS_HUMAN_REVIEW
    assert response.confidence == 0.0
    assert response.human_review_required is True


def test_verify_claim_malformed_llm_response_falls_back_to_needs_human_review():
    """Malformed JSON from the LLM flows through validate_output()'s own fallback."""
    with (
        patch("rag.api.classify_citation_type", return_value=CitationType.BACKGROUND),
        patch("rag.api.generate_verdict", return_value="not valid json"),
    ):
        response = verify_claim(make_door2_request())

    assert response.support_status == Verdict.NEEDS_HUMAN_REVIEW
    assert response.human_review_required is True


def test_verify_claim_low_similarity_forces_human_review():
    """A high-confidence SUPPORTED verdict is still flagged when overall_similarity_score is low."""
    raw_json = (
        '{"verdict": "SUPPORTED", "confidence": 0.95, '
        '"explanation": "1. Claim. 2. Evidence. 3. Comparison. 4. Verdict.", '
        '"evidence_used": ["chunk_001"], "limitations": null}'
    )

    with (
        patch("rag.api.classify_citation_type", return_value=CitationType.RESULT_COMPARISON),
        patch("rag.api.generate_verdict", return_value=raw_json),
    ):
        response = verify_claim(make_door2_request(overall_similarity_score=0.1))

    assert response.support_status == Verdict.SUPPORTED
    assert response.human_review_required is True
