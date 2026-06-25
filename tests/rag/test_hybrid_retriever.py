"""
Unit tests for rag/retrieval/hybrid_retriever.py (SCRUM-258 + SCRUM-259).

Testing strategy:
  - Pure local computation for RRF (no FAISS, no BM25, no API calls): we
    build VectorStoreOutput / Bm25RetrieverOutput fixtures by hand so the
    RRF math can be verified exactly.
  - FlashRank is mocked, never called for real: an autouse fixture patches
    _build_ranker() to raise, so by default every test exercises the
    fallback-to-RRF-only path with no model download (mirrors how
    test_classifier.py mocks the OpenAI client instead of calling it).
    Tests that specifically verify reranking behaviour patch
    rag.retrieval.hybrid_retriever.Ranker directly to control rerank output.
  - make_chunk / make_dense_output / make_bm25_output helpers build minimal
    but fully valid objects, mirroring test_vector_store.py's style.
"""

from unittest.mock import MagicMock, patch

import pytest

from rag.ingestion.models import ChunkMetadata
from rag.retrieval.hybrid_retriever import RRF_K, _rrf_score, merge
from rag.retrieval.models import (
    Bm25RetrievedChunk,
    Bm25RetrieverOutput,
    HybridRetrieverInput,
    HybridRetrieverOutput,
    RetrievedChunk,
    VectorStoreOutput,
)

TEST_DOI = "10.0000/test.2024"
TEST_CLAIM = "Exercise reduces heart disease risk."


@pytest.fixture(autouse=True)
def no_real_flashrank():
    """Prevent every test from downloading/calling the real FlashRank model.

    By default _build_ranker() raises, so merge()'s try/except falls back
    to RRF-only ordering — exactly what the pre-SCRUM-259 tests expect.
    Tests that want to exercise real reranking behaviour override this by
    patching rag.retrieval.hybrid_retriever.Ranker themselves.
    """
    with patch(
        "rag.retrieval.hybrid_retriever._build_ranker",
        side_effect=RuntimeError("FlashRank disabled in unit tests"),
    ):
        yield


def make_chunk(index: int, doi: str = TEST_DOI) -> ChunkMetadata:
    """Build a minimal ChunkMetadata for testing."""
    return ChunkMetadata(
        chunk_id=f"chunk_{index:03d}",
        section="results",
        priority=1.3,
        chunk_index=index,
        paper_doi=doi,
        evidence_type="FULL_TEXT",
        chunk_text=f"Test chunk {index}.",
        token_count=10,
    )


def make_dense_output(chunk_indices: list[int]) -> VectorStoreOutput:
    """Build a VectorStoreOutput where chunk_indices[i] is ranked i+1."""
    chunks = [
        RetrievedChunk(
            chunk=make_chunk(idx), raw_score=0.9, weighted_score=0.9, rank=rank
        )
        for rank, idx in enumerate(chunk_indices, start=1)
    ]
    return VectorStoreOutput(
        doi=TEST_DOI, top_chunks=chunks, total_indexed=len(chunks), retrieved_k=len(chunks)
    )


def make_bm25_output(chunk_indices: list[int]) -> Bm25RetrieverOutput:
    """Build a Bm25RetrieverOutput where chunk_indices[i] is ranked i+1."""
    chunks = [
        Bm25RetrievedChunk(
            chunk=make_chunk(idx), raw_score=5.0, weighted_score=5.0, rank=rank
        )
        for rank, idx in enumerate(chunk_indices, start=1)
    ]
    return Bm25RetrieverOutput(top_chunks=chunks, total_indexed=len(chunks), retrieved_k=len(chunks))


def make_input(dense, bm25, top_k=5, claim=TEST_CLAIM) -> HybridRetrieverInput:
    """Build a HybridRetrieverInput with a default claim string."""
    return HybridRetrieverInput(dense_results=dense, bm25_results=bm25, claim=claim, top_k=top_k)


# ── _rrf_score ─────────────────────────────────────────────────────────────────


def test_rrf_score_rank_1():
    assert _rrf_score(1) == 1.0 / (RRF_K + 1)


def test_rrf_score_decreases_with_rank():
    assert _rrf_score(1) > _rrf_score(2) > _rrf_score(10)


# ── merge — empty inputs ───────────────────────────────────────────────────────


def test_merge_both_empty_returns_empty_output():
    result = merge(make_input(make_dense_output([]), make_bm25_output([]), top_k=5))
    assert isinstance(result, HybridRetrieverOutput)
    assert result.top_chunks == []
    assert result.total_unique == 0


def test_merge_one_side_empty_returns_other_side():
    result = merge(make_input(make_dense_output([0, 1]), make_bm25_output([]), top_k=5))
    assert result.total_unique == 2
    assert {c.chunk.chunk_id for c in result.top_chunks} == {"chunk_000", "chunk_001"}
    assert all(c.bm25_rank is None for c in result.top_chunks)


# ── merge — deduplication and score combination ───────────────────────────────


def test_merge_chunk_in_both_sources_combines_rrf_contributions():
    # chunk_000 is rank 1 in dense and rank 2 in BM25.
    dense = make_dense_output([0])
    bm25 = make_bm25_output([1, 0])  # chunk_001 rank 1, chunk_000 rank 2

    result = merge(make_input(dense, bm25, top_k=5))

    assert result.total_unique == 2
    by_id = {c.chunk.chunk_id: c for c in result.top_chunks}

    expected_score_000 = _rrf_score(1) + _rrf_score(2)
    assert by_id["chunk_000"].rrf_score == round(expected_score_000, 6)
    assert by_id["chunk_000"].dense_rank == 1
    assert by_id["chunk_000"].bm25_rank == 2

    expected_score_001 = _rrf_score(1)
    assert by_id["chunk_001"].rrf_score == round(expected_score_001, 6)
    assert by_id["chunk_001"].dense_rank is None
    assert by_id["chunk_001"].bm25_rank == 1


def test_merge_chunk_found_by_both_ranks_above_chunk_found_by_one():
    # chunk_000: dense rank 1 + bm25 rank 1 -> highest combined score.
    # chunk_001: dense rank 2 only.
    # chunk_002: bm25 rank 2 only.
    dense = make_dense_output([0, 1])
    bm25 = make_bm25_output([0, 2])

    result = merge(make_input(dense, bm25, top_k=5))

    assert result.top_chunks[0].chunk.chunk_id == "chunk_000"
    assert result.top_chunks[0].rank == 1


def test_merge_does_not_duplicate_chunk_present_in_both_lists():
    dense = make_dense_output([0])
    bm25 = make_bm25_output([0])

    result = merge(make_input(dense, bm25, top_k=5))

    assert result.total_unique == 1
    assert len(result.top_chunks) == 1


# ── merge — ranking and top_k ─────────────────────────────────────────────────


def test_merge_assigns_sequential_1_based_ranks():
    dense = make_dense_output([0, 1, 2])
    bm25 = make_bm25_output([2, 1, 0])

    result = merge(make_input(dense, bm25, top_k=3))
    assert [c.rank for c in result.top_chunks] == [1, 2, 3]


def test_merge_limits_results_to_top_k():
    dense = make_dense_output([0, 1, 2, 3, 4])
    bm25 = make_bm25_output([])

    result = merge(make_input(dense, bm25, top_k=2))
    assert len(result.top_chunks) == 2
    assert result.total_unique == 5


def test_merge_top_k_larger_than_unique_chunks_returns_all():
    dense = make_dense_output([0])
    bm25 = make_bm25_output([1])

    result = merge(make_input(dense, bm25, top_k=10))
    assert len(result.top_chunks) == 2
    assert result.total_unique == 2


# ── merge — FlashRank reranking (SCRUM-259) ───────────────────────────────────


def fake_ranker(scores_by_id: dict[str, float]) -> MagicMock:
    """Build a mock Ranker whose .rerank() returns the given id -> score mapping."""
    ranker = MagicMock()

    def _rerank_side_effect(request):
        return [
            {"id": p["id"], "text": p["text"], "score": scores_by_id[p["id"]]}
            for p in request.passages
        ]

    ranker.rerank.side_effect = _rerank_side_effect
    return ranker


def test_merge_reranking_reorders_by_rerank_score():
    # RRF would rank chunk_000 first (rank 1 in both), but FlashRank scores
    # chunk_001 higher — the final order must follow FlashRank, not RRF.
    dense = make_dense_output([0, 1])
    bm25 = make_bm25_output([0, 1])

    with patch("rag.retrieval.hybrid_retriever._build_ranker") as mock_build:
        mock_build.return_value = fake_ranker({"chunk_000": 0.1, "chunk_001": 0.9})
        result = merge(make_input(dense, bm25, top_k=2))

    assert [c.chunk.chunk_id for c in result.top_chunks] == ["chunk_001", "chunk_000"]
    assert result.top_chunks[0].rerank_score == 0.9
    assert result.top_chunks[1].rerank_score == 0.1


def test_merge_reranking_only_covers_oversampled_pool():
    # With top_k=1 and RERANK_OVERSAMPLE_FACTOR=3, the pool is the top 3 RRF
    # chunks; a 4th chunk ranked last by RRF must never reach the reranker.
    dense = make_dense_output([0, 1, 2, 3])
    bm25 = make_bm25_output([])

    with patch("rag.retrieval.hybrid_retriever._build_ranker") as mock_build:
        ranker = fake_ranker({"chunk_000": 0.5, "chunk_001": 0.5, "chunk_002": 0.5})
        mock_build.return_value = ranker
        merge(make_input(dense, bm25, top_k=1))

    rerank_request = ranker.rerank.call_args[0][0]
    reranked_ids = {p["id"] for p in rerank_request.passages}
    assert reranked_ids == {"chunk_000", "chunk_001", "chunk_002"}
    assert "chunk_003" not in reranked_ids


def test_merge_falls_back_to_rrf_order_when_reranking_raises():
    dense = make_dense_output([0, 1])
    bm25 = make_bm25_output([0, 1])

    with patch("rag.retrieval.hybrid_retriever._build_ranker") as mock_build:
        mock_build.return_value.rerank.side_effect = RuntimeError("model unavailable")
        result = merge(make_input(dense, bm25, top_k=2))

    assert [c.chunk.chunk_id for c in result.top_chunks] == ["chunk_000", "chunk_001"]
    assert all(c.rerank_score is None for c in result.top_chunks)


def test_merge_rerank_score_is_none_when_flashrank_disabled():
    # The autouse fixture makes _build_ranker raise -> fallback path.
    dense = make_dense_output([0])
    bm25 = make_bm25_output([])

    result = merge(make_input(dense, bm25, top_k=1))
    assert result.top_chunks[0].rerank_score is None
