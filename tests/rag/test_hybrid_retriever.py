"""
Unit tests for rag/retrieval/hybrid_retriever.py (SCRUM-258).

Testing strategy:
  - Pure local computation (no FAISS, no BM25, no API calls): we build
    VectorStoreOutput / Bm25RetrieverOutput fixtures by hand so the RRF math
    can be verified exactly.
  - make_chunk / make_retrieved_chunk / make_bm25_chunk helpers build minimal
    but fully valid objects, mirroring test_vector_store.py's style.
"""

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


# ── _rrf_score ─────────────────────────────────────────────────────────────────


def test_rrf_score_rank_1():
    assert _rrf_score(1) == 1.0 / (RRF_K + 1)


def test_rrf_score_decreases_with_rank():
    assert _rrf_score(1) > _rrf_score(2) > _rrf_score(10)


# ── merge — empty inputs ───────────────────────────────────────────────────────


def test_merge_both_empty_returns_empty_output():
    result = merge(
        HybridRetrieverInput(
            dense_results=make_dense_output([]), bm25_results=make_bm25_output([]), top_k=5
        )
    )
    assert isinstance(result, HybridRetrieverOutput)
    assert result.top_chunks == []
    assert result.total_unique == 0


def test_merge_one_side_empty_returns_other_side():
    result = merge(
        HybridRetrieverInput(
            dense_results=make_dense_output([0, 1]), bm25_results=make_bm25_output([]), top_k=5
        )
    )
    assert result.total_unique == 2
    assert {c.chunk.chunk_id for c in result.top_chunks} == {"chunk_000", "chunk_001"}
    assert all(c.bm25_rank is None for c in result.top_chunks)


# ── merge — deduplication and score combination ───────────────────────────────


def test_merge_chunk_in_both_sources_combines_rrf_contributions():
    # chunk_000 is rank 1 in dense and rank 2 in BM25.
    dense = make_dense_output([0])
    bm25 = make_bm25_output([1, 0])  # chunk_001 rank 1, chunk_000 rank 2

    result = merge(HybridRetrieverInput(dense_results=dense, bm25_results=bm25, top_k=5))

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

    result = merge(HybridRetrieverInput(dense_results=dense, bm25_results=bm25, top_k=5))

    assert result.top_chunks[0].chunk.chunk_id == "chunk_000"
    assert result.top_chunks[0].rank == 1


def test_merge_does_not_duplicate_chunk_present_in_both_lists():
    dense = make_dense_output([0])
    bm25 = make_bm25_output([0])

    result = merge(HybridRetrieverInput(dense_results=dense, bm25_results=bm25, top_k=5))

    assert result.total_unique == 1
    assert len(result.top_chunks) == 1


# ── merge — ranking and top_k ─────────────────────────────────────────────────


def test_merge_assigns_sequential_1_based_ranks():
    dense = make_dense_output([0, 1, 2])
    bm25 = make_bm25_output([2, 1, 0])

    result = merge(HybridRetrieverInput(dense_results=dense, bm25_results=bm25, top_k=3))
    assert [c.rank for c in result.top_chunks] == [1, 2, 3]


def test_merge_limits_results_to_top_k():
    dense = make_dense_output([0, 1, 2, 3, 4])
    bm25 = make_bm25_output([])

    result = merge(HybridRetrieverInput(dense_results=dense, bm25_results=bm25, top_k=2))
    assert len(result.top_chunks) == 2
    assert result.total_unique == 5


def test_merge_top_k_larger_than_unique_chunks_returns_all():
    dense = make_dense_output([0])
    bm25 = make_bm25_output([1])

    result = merge(HybridRetrieverInput(dense_results=dense, bm25_results=bm25, top_k=10))
    assert len(result.top_chunks) == 2
    assert result.total_unique == 2
