"""
Unit tests for rag/api.py — the backend integration handoff layer.

These tests mock the pipeline functions that retrieve_evidence() and
verify_claim() wire together (clean_text, chunk_text, embed_chunks, search,
bm25_search, merge, classify_citation_type, generate_verdict) at the points
where rag.api imports them, so each test exercises api.py's own
orchestration logic (branching, field mapping, fallback handling) rather
than re-testing the modules those functions belong to — those already have
their own test suites. validate_output() is left unmocked in the success
path so the full Door 2 chain (LLM string -> validated VerificationOutput
-> response model) is exercised end to end.
"""

from unittest.mock import patch

import pytest

import rag.api as rag_api
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
from rag.retrieval.models import (
    Bm25RetrievedChunk,
    Bm25RetrieverOutput,
    EmbeddedChunk,
    EmbedderOutput,
    HybridRetrievedChunk,
    HybridRetrieverOutput,
    RetrievedChunk,
    VectorStoreOutput,
)
from rag.verification.models import Verdict


# ── Fixtures and helpers ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_embedding_cache():
    """SCRUM-264's per-DOI cache is module-level state — clear it before and
    after every test so tests reusing the same DOI string don't leak cached
    EmbedderOutputs (and the mocks that produced them) into each other."""
    rag_api._embedding_cache.clear()
    yield
    rag_api._embedding_cache.clear()


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


def count_source_embedding_calls(requests: list[RetrieveEvidenceRequest]) -> int:
    """Run mocked Door 1 requests and count source-chunk embedding calls."""
    chunk = make_chunk(0)
    vector_output = VectorStoreOutput(
        doi="irrelevant",
        top_chunks=[RetrievedChunk(chunk=chunk, raw_score=0.9, weighted_score=0.9, rank=1)],
        total_indexed=1,
        retrieved_k=1,
    )
    bm25_output = Bm25RetrieverOutput(top_chunks=[], total_indexed=1, retrieved_k=0)
    hybrid_output = HybridRetrieverOutput(
        top_chunks=[
            HybridRetrievedChunk(
                chunk=chunk,
                rrf_score=0.02,
                dense_rank=1,
                bm25_rank=None,
                rerank_score=0.9,
                rank=1,
            ),
        ],
        total_unique=1,
    )

    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=fake_embed_chunks) as mock_embed,
        patch("rag.api.search", return_value=vector_output),
        patch("rag.api.bm25_search", return_value=bm25_output),
        patch("rag.api.merge", return_value=hybrid_output),
    ):
        mock_clean.return_value = CleanerOutput(
            clean_text="cleaned text",
            doi="irrelevant",
            evidence_availability=EvidenceAvailability.ABSTRACT_AVAILABLE,
            original_length=20,
            cleaned_length=12,
        )
        mock_chunk.return_value = ChunkerOutput(
            doi="irrelevant",
            chunks=[chunk],
            total_chunks=1,
            sections_found=["results"],
            fallback_used=False,
        )
        responses = [retrieve_evidence(request) for request in requests]

    assert all(response.retrieval_status == RetrievalStatus.SUCCEEDED for response in responses)
    source_calls = [
        call
        for call in mock_embed.call_args_list
        if any(item.chunk_id == chunk.chunk_id for item in call.args[0].chunks)
    ]
    return len(source_calls)


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
    bm25_output = Bm25RetrieverOutput(top_chunks=[], total_indexed=2, retrieved_k=0)
    hybrid_output = HybridRetrieverOutput(
        top_chunks=[
            HybridRetrievedChunk(
                chunk=chunk1, rrf_score=0.02, dense_rank=1, bm25_rank=None, rerank_score=0.9, rank=1
            ),
            HybridRetrievedChunk(
                chunk=chunk2, rrf_score=0.01, dense_rank=2, bm25_rank=None, rerank_score=0.7, rank=2
            ),
        ],
        total_unique=2,
    )

    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=fake_embed_chunks),
        patch("rag.api.search", return_value=vector_output),
        patch("rag.api.bm25_search", return_value=bm25_output),
        patch("rag.api.merge", return_value=hybrid_output),
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
    assert response.semantic_cache_match == {
        "matched": False,
        "cached_result_id": None,
        "similarity": None,
    }
    assert response.error_message is None


@pytest.mark.parametrize(
    ("requested_top_k", "expected_top_k"),
    [
        pytest.param(1, 1, id="top-k-one"),
        pytest.param(3, 3, id="top-k-three"),
        pytest.param(None, 5, id="top-k-default"),
    ],
)
def test_retrieve_evidence_respects_requested_top_k(
    requested_top_k: int | None,
    expected_top_k: int,
) -> None:
    chunks = [make_chunk(index) for index in range(6)]
    vector_output = VectorStoreOutput(
        doi="10.1234/example.2019.001",
        top_chunks=[
            RetrievedChunk(
                chunk=chunk,
                raw_score=0.9 - index * 0.05,
                weighted_score=0.9 - index * 0.05,
                rank=index + 1,
            )
            for index, chunk in enumerate(chunks)
        ],
        total_indexed=len(chunks),
        retrieved_k=len(chunks),
    )
    hybrid_output = HybridRetrieverOutput(
        top_chunks=[
            HybridRetrievedChunk(
                chunk=chunk,
                rrf_score=0.02 - index * 0.001,
                dense_rank=index + 1,
                bm25_rank=None,
                rerank_score=0.9 - index * 0.05,
                rank=index + 1,
            )
            for index, chunk in enumerate(chunks)
        ],
        total_unique=len(chunks),
    )
    request = make_door1_request()
    if requested_top_k is not None:
        request = request.model_copy(update={"top_k": requested_top_k})

    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=fake_embed_chunks),
        patch("rag.api.search", return_value=vector_output) as mock_search,
        patch(
            "rag.api.bm25_search",
            return_value=Bm25RetrieverOutput(
                top_chunks=[],
                total_indexed=len(chunks),
                retrieved_k=0,
            ),
        ) as mock_bm25,
        patch("rag.api.merge", return_value=hybrid_output) as mock_merge,
    ):
        mock_clean.return_value = CleanerOutput(
            clean_text="cleaned text",
            doi=request.doi,
            evidence_availability=EvidenceAvailability.ABSTRACT_AVAILABLE,
            original_length=20,
            cleaned_length=12,
        )
        mock_chunk.return_value = ChunkerOutput(
            doi=request.doi,
            chunks=chunks,
            total_chunks=len(chunks),
            sections_found=["results"],
            fallback_used=False,
        )

        response = retrieve_evidence(request)

    assert len(response.top_chunks) == expected_top_k
    assert mock_search.call_args.args[0].top_k == expected_top_k * 3
    assert mock_bm25.call_args.args[0].top_k == expected_top_k * 3
    assert mock_merge.call_args.args[0].top_k == expected_top_k


def test_retrieve_evidence_success_falls_back_to_dense_score_when_rerank_missing():
    """When FlashRank reranking failed (rerank_score is None), similarity_score
    falls back to the chunk's dense weighted_score instead of going unscored."""
    chunk1 = make_chunk(0)
    vector_output = VectorStoreOutput(
        doi="10.1234/example.2019.001",
        top_chunks=[RetrievedChunk(chunk=chunk1, raw_score=0.65, weighted_score=0.65, rank=1)],
        total_indexed=1,
        retrieved_k=1,
    )
    bm25_output = Bm25RetrieverOutput(top_chunks=[], total_indexed=1, retrieved_k=0)
    hybrid_output = HybridRetrieverOutput(
        top_chunks=[
            HybridRetrievedChunk(
                chunk=chunk1, rrf_score=0.016, dense_rank=1, bm25_rank=None, rerank_score=None, rank=1
            ),
        ],
        total_unique=1,
    )

    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=fake_embed_chunks),
        patch("rag.api.search", return_value=vector_output),
        patch("rag.api.bm25_search", return_value=bm25_output),
        patch("rag.api.merge", return_value=hybrid_output),
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

    assert response.top_chunks[0].similarity_score == pytest.approx(0.5)
    assert response.overall_similarity_score == pytest.approx(0.5)


def test_retrieve_evidence_normalizes_dense_fallback_scores_above_one():
    """SCRUM-262: a section-weighted dense score above 1.0 (e.g. 1.3 for a
    perfect cosine match in a Results section) is normalized to 0-1 by
    MAX_SECTION_WEIGHT, and ranking order against a lower dense score is
    preserved."""
    chunk1, chunk2 = make_chunk(0), make_chunk(1)
    vector_output = VectorStoreOutput(
        doi="10.1234/example.2019.001",
        top_chunks=[
            RetrievedChunk(chunk=chunk1, raw_score=1.0, weighted_score=1.3, rank=1),
            RetrievedChunk(chunk=chunk2, raw_score=0.5, weighted_score=0.65, rank=2),
        ],
        total_indexed=2,
        retrieved_k=2,
    )
    bm25_output = Bm25RetrieverOutput(top_chunks=[], total_indexed=2, retrieved_k=0)
    hybrid_output = HybridRetrieverOutput(
        top_chunks=[
            HybridRetrievedChunk(
                chunk=chunk1, rrf_score=0.02, dense_rank=1, bm25_rank=None, rerank_score=None, rank=1
            ),
            HybridRetrievedChunk(
                chunk=chunk2, rrf_score=0.01, dense_rank=2, bm25_rank=None, rerank_score=None, rank=2
            ),
        ],
        total_unique=2,
    )

    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=fake_embed_chunks),
        patch("rag.api.search", return_value=vector_output),
        patch("rag.api.bm25_search", return_value=bm25_output),
        patch("rag.api.merge", return_value=hybrid_output),
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

    assert response.top_chunks[0].chunk_id == chunk1.chunk_id
    assert response.top_chunks[0].similarity_score == pytest.approx(1.0)
    assert response.top_chunks[1].similarity_score == pytest.approx(0.5)
    assert all(c.similarity_score <= 1.0 for c in response.top_chunks)
    assert response.overall_similarity_score == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("rerank_score", "expected_score"),
    [
        pytest.param(1.7, 1.0, id="above-one"),
        pytest.param(-0.4, 0.0, id="negative"),
    ],
)
def test_retrieve_evidence_normalizes_rerank_scores_to_backend_range(
    rerank_score: float,
    expected_score: float,
) -> None:
    chunk = make_chunk(0)
    vector_output = VectorStoreOutput(
        doi="10.1234/example.2019.001",
        top_chunks=[RetrievedChunk(chunk=chunk, raw_score=0.8, weighted_score=0.8, rank=1)],
        total_indexed=1,
        retrieved_k=1,
    )
    hybrid_output = HybridRetrieverOutput(
        top_chunks=[
            HybridRetrievedChunk(
                chunk=chunk,
                rrf_score=0.02,
                dense_rank=1,
                bm25_rank=None,
                rerank_score=rerank_score,
                rank=1,
            )
        ],
        total_unique=1,
    )

    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=fake_embed_chunks),
        patch("rag.api.search", return_value=vector_output),
        patch(
            "rag.api.bm25_search",
            return_value=Bm25RetrieverOutput(top_chunks=[], total_indexed=1, retrieved_k=0),
        ),
        patch("rag.api.merge", return_value=hybrid_output),
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
            chunks=[chunk],
            total_chunks=1,
            sections_found=["results"],
            fallback_used=False,
        )

        response = retrieve_evidence(make_door1_request())

    assert response.top_chunks[0].similarity_score == expected_score
    assert response.overall_similarity_score == expected_score
    assert response.retrieval_confidence == expected_score


def test_retrieve_evidence_reuses_cached_embeddings_for_same_doi():
    """SCRUM-264: a second claim against the same DOI reuses the cached
    EmbedderOutput instead of re-embedding the source chunks. embed_chunks()
    is also used internally to embed the claim query text itself (see
    _embed_single_text()), so it is still called once per request for that —
    only the source-chunk embedding call is skipped on a cache hit."""
    chunk1 = make_chunk(0)
    vector_output = VectorStoreOutput(
        doi="10.1234/example.2019.001",
        top_chunks=[RetrievedChunk(chunk=chunk1, raw_score=0.9, weighted_score=0.9, rank=1)],
        total_indexed=1,
        retrieved_k=1,
    )
    bm25_output = Bm25RetrieverOutput(top_chunks=[], total_indexed=1, retrieved_k=0)
    hybrid_output = HybridRetrieverOutput(
        top_chunks=[
            HybridRetrievedChunk(
                chunk=chunk1, rrf_score=0.02, dense_rank=1, bm25_rank=None, rerank_score=0.9, rank=1
            ),
        ],
        total_unique=1,
    )

    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=fake_embed_chunks) as mock_embed,
        patch("rag.api.search", return_value=vector_output),
        patch("rag.api.bm25_search", return_value=bm25_output),
        patch("rag.api.merge", return_value=hybrid_output),
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

        first = retrieve_evidence(make_door1_request())
        second = retrieve_evidence(make_door1_request())

    # Each call always embeds the claim query text itself (_embed_single_text
    # always calls embed_chunks once), but the source-chunk embedding call
    # should only happen on the first request — the second is a cache hit.
    source_chunk_embed_calls = [
        call for call in mock_embed.call_args_list
        if any(c.chunk_id == chunk1.chunk_id for c in call.args[0].chunks)
    ]
    assert len(source_chunk_embed_calls) == 1
    assert first.retrieval_status == RetrievalStatus.SUCCEEDED
    assert second.retrieval_status == RetrievalStatus.SUCCEEDED


def test_retrieve_evidence_does_not_reuse_cache_across_different_dois():
    """A different DOI with the same reference_id must not hit cached embeddings."""
    chunk1 = make_chunk(0)
    vector_output = VectorStoreOutput(
        doi="irrelevant",
        top_chunks=[RetrievedChunk(chunk=chunk1, raw_score=0.9, weighted_score=0.9, rank=1)],
        total_indexed=1,
        retrieved_k=1,
    )
    bm25_output = Bm25RetrieverOutput(top_chunks=[], total_indexed=1, retrieved_k=0)
    hybrid_output = HybridRetrieverOutput(
        top_chunks=[
            HybridRetrievedChunk(
                chunk=chunk1, rrf_score=0.02, dense_rank=1, bm25_rank=None, rerank_score=0.9, rank=1
            ),
        ],
        total_unique=1,
    )

    def make_request_for_doi(doi: str) -> RetrieveEvidenceRequest:
        request = make_door1_request()
        return request.model_copy(update={"doi": doi})

    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=fake_embed_chunks) as mock_embed,
        patch("rag.api.search", return_value=vector_output),
        patch("rag.api.bm25_search", return_value=bm25_output),
        patch("rag.api.merge", return_value=hybrid_output),
    ):
        mock_clean.return_value = CleanerOutput(
            clean_text="cleaned text",
            doi="irrelevant",
            evidence_availability=EvidenceAvailability.ABSTRACT_AVAILABLE,
            original_length=20,
            cleaned_length=12,
        )
        mock_chunk.return_value = ChunkerOutput(
            doi="irrelevant",
            chunks=[chunk1],
            total_chunks=1,
            sections_found=["results"],
            fallback_used=False,
        )

        retrieve_evidence(make_request_for_doi("10.1111/aaa"))
        retrieve_evidence(make_request_for_doi("10.2222/bbb"))

    # Both requests must embed their source chunks — neither DOI should hit
    # the other's cache entry.
    source_chunk_embed_calls = [
        call for call in mock_embed.call_args_list
        if any(c.chunk_id == chunk1.chunk_id for c in call.args[0].chunks)
    ]
    assert len(source_chunk_embed_calls) == 2


@pytest.mark.parametrize(
    (
        "second_doi",
        "second_text",
        "second_source_url",
        "second_availability",
        "expected_source_embedding_calls",
    ),
    [
        pytest.param(
            "10.1234/example.2019.001",
            "A changed source text payload.",
            "https://doi.org/10.1234/example.2019.001",
            EvidenceAvailability.ABSTRACT_AVAILABLE,
            2,
            id="same-doi-different-source-text",
        ),
        pytest.param(
            "10.2222/different",
            "A different paper's source text.",
            "https://doi.org/10.2222/different",
            EvidenceAvailability.ABSTRACT_AVAILABLE,
            2,
            id="different-doi-different-source-text",
        ),
        pytest.param(
            " DOI:HTTPS://DOI.ORG/10.1234/EXAMPLE.2019.001 ",
            "Abstract text of the source paper...",
            "https://doi.org/10.1234/example.2019.001",
            EvidenceAvailability.ABSTRACT_AVAILABLE,
            1,
            id="doi-case-and-prefix-normalize-to-same-key",
        ),
        pytest.param(
            "10.1234/example.2019.001",
            "Abstract text of the source paper...",
            "https://repository.example/source.pdf",
            EvidenceAvailability.ABSTRACT_AVAILABLE,
            2,
            id="same-doi-different-source-identity",
        ),
        pytest.param(
            "10.1234/example.2019.001",
            "Abstract text of the source paper...",
            "https://doi.org/10.1234/example.2019.001",
            EvidenceAvailability.FULL_TEXT_AVAILABLE,
            2,
            id="same-doi-different-evidence-availability",
        ),
    ],
)
def test_retrieve_evidence_cache_key_scopes_source_embeddings(
    second_doi: str,
    second_text: str,
    second_source_url: str,
    second_availability: EvidenceAvailability,
    expected_source_embedding_calls: int,
) -> None:
    """Cache reuse requires the same normalized DOI and exact evidence identity."""
    first = make_door1_request()
    second = first.model_copy(
        update={
            "doi": second_doi,
            "source_evidence": SourceEvidence(
                evidence_availability=second_availability,
                text=second_text,
                source_url=second_source_url,
            ),
        }
    )

    assert count_source_embedding_calls([first, second]) == expected_source_embedding_calls


def test_retrieve_evidence_invalid_doi_skips_pipeline():
    """INVALID doi_status returns FAILED immediately without touching the pipeline."""
    with patch("rag.api.clean_text", side_effect=AssertionError("pipeline must not run")):
        response = retrieve_evidence(make_door1_request(doi_status=DoiStatus.INVALID))

    assert response.retrieval_status == RetrievalStatus.FAILED
    assert response.top_chunks == []
    assert "DOI is invalid or unresolved" in response.error_message
    assert response.semantic_cache_match["matched"] is False


def test_retrieve_evidence_unresolvable_doi_skips_pipeline():
    """UNRESOLVABLE doi_status also returns FAILED immediately."""
    with patch("rag.api.clean_text", side_effect=AssertionError("pipeline must not run")):
        response = retrieve_evidence(make_door1_request(doi_status=DoiStatus.UNRESOLVABLE))

    assert response.retrieval_status == RetrievalStatus.FAILED
    assert "DOI is invalid or unresolved" in response.error_message


def test_retrieve_evidence_empty_source_returns_safe_failure_without_pipeline_calls():
    request = make_door1_request().model_copy(
        update={
            "source_evidence": SourceEvidence(
                evidence_availability=EvidenceAvailability.ABSTRACT_AVAILABLE,
                text="   ",
                source_url="file:///private/source.pdf",
            )
        }
    )
    with patch("rag.api.clean_text") as mock_clean:
        response = retrieve_evidence(request)

    mock_clean.assert_not_called()
    assert response.retrieval_status == RetrievalStatus.FAILED
    assert response.error_message == "Source evidence is unavailable or empty."
    assert response.semantic_cache_match == {
        "matched": False,
        "cached_result_id": None,
        "similarity": None,
    }


def test_retrieve_evidence_no_chunks_returns_failed():
    """Zero chunks from chunk_text() returns FAILED without calling embed_chunks/search/bm25/merge."""
    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks") as mock_embed,
        patch("rag.api.search") as mock_search,
        patch("rag.api.bm25_search") as mock_bm25,
        patch("rag.api.merge") as mock_merge,
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
        mock_bm25.assert_not_called()
        mock_merge.assert_not_called()

    assert response.retrieval_status == RetrievalStatus.FAILED
    assert response.error_message == "Source evidence produced no retrievable chunks."


def test_retrieve_evidence_pipeline_exception_returns_failed():
    """An exception from embed_chunks() (e.g. missing API key) is caught and returns FAILED."""
    chunk1 = make_chunk(0)
    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch(
            "rag.api.embed_chunks",
            side_effect=EnvironmentError("OPENROUTER_API_KEY=sk-secret-value"),
        ),
        patch("rag.api.search") as mock_search,
        patch("rag.api.bm25_search") as mock_bm25,
        patch("rag.api.merge") as mock_merge,
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
        mock_bm25.assert_not_called()
        mock_merge.assert_not_called()

    assert response.retrieval_status == RetrievalStatus.FAILED
    assert response.error_message == "Embedding service failed while preparing retrieval vectors."
    assert "secret" not in response.error_message.casefold()


def test_retrieve_evidence_internal_exception_returns_safe_failure_detail():
    chunk = make_chunk(0)
    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=fake_embed_chunks),
        patch("rag.api.search", side_effect=RuntimeError("token=private-token")),
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
            chunks=[chunk],
            total_chunks=1,
            sections_found=["results"],
            fallback_used=False,
        )

        response = retrieve_evidence(make_door1_request())

    assert response.retrieval_status == RetrievalStatus.FAILED
    assert response.error_message == "RAG retrieval failed due to an internal error."
    assert "token" not in response.error_message.casefold()


def test_retrieve_evidence_empty_hybrid_results_returns_failed():
    """merge() returning zero top_chunks (e.g. both retrievers empty) returns FAILED."""
    chunk1 = make_chunk(0)
    vector_output = VectorStoreOutput(
        doi="10.1234/example.2019.001", top_chunks=[], total_indexed=0, retrieved_k=0
    )
    bm25_output = Bm25RetrieverOutput(top_chunks=[], total_indexed=0, retrieved_k=0)
    empty_hybrid_output = HybridRetrieverOutput(top_chunks=[], total_unique=0)

    with (
        patch("rag.api.clean_text") as mock_clean,
        patch("rag.api.chunk_text") as mock_chunk,
        patch("rag.api.embed_chunks", side_effect=fake_embed_chunks),
        patch("rag.api.search", return_value=vector_output),
        patch("rag.api.bm25_search", return_value=bm25_output),
        patch("rag.api.merge", return_value=empty_hybrid_output),
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
    assert response.error_message == "No relevant evidence chunks were found."


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
    assert response.human_review_required is True


def test_verify_claim_unresolvable_doi_skips_pipeline():
    """UNRESOLVABLE doi_status also returns INSUFFICIENT_EVIDENCE immediately."""
    with (
        patch("rag.api.classify_citation_type", side_effect=AssertionError("must not run")),
        patch("rag.api.generate_verdict", side_effect=AssertionError("must not run")),
    ):
        response = verify_claim(make_door2_request(doi_status=DoiStatus.UNRESOLVABLE))

    assert response.support_status == Verdict.INSUFFICIENT_EVIDENCE
    assert response.human_review_required is True


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
