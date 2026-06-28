"""
Unit tests for rag/retrieval/bm25_retriever.py (SCRUM-257).

Testing strategy:
  - No mocking of rank_bm25: it is a local computation library with no
    external dependencies, so we test it for real.
  - make_chunk helper builds minimal but fully valid ChunkMetadata so each
    test reads as a clear scenario, mirroring test_vector_store.py's style.
"""

from rag.ingestion.models import ChunkMetadata
from rag.retrieval.bm25_retriever import _build_index, _get_section_weight, _tokenize, search
from rag.retrieval.models import Bm25RetrieverInput, Bm25RetrieverOutput
from rag.retrieval.vector_store import DEFAULT_WEIGHT, SECTION_WEIGHTS

TEST_DOI = "10.0000/test.2024"


def make_chunk(
    index: int = 0,
    section: str = "results",
    chunk_text: str = "Test chunk.",
    doi: str = TEST_DOI,
) -> ChunkMetadata:
    """Build a minimal ChunkMetadata for testing."""
    priority = SECTION_WEIGHTS.get(section, DEFAULT_WEIGHT)
    return ChunkMetadata(
        chunk_id=f"10_0000_test_chunk_{index:03d}",
        section=section,
        priority=priority,
        chunk_index=index,
        paper_doi=doi,
        evidence_type="FULL_TEXT",
        chunk_text=chunk_text,
        token_count=10,
    )


# ── _tokenize ──────────────────────────────────────────────────────────────────


def test_tokenize_lowercases_and_splits_on_words():
    assert _tokenize("The Model Achieved 95% Accuracy.") == [
        "the", "model", "achieved", "95", "accuracy",
    ]


def test_tokenize_empty_string_returns_empty_list():
    assert _tokenize("") == []


# ── _get_section_weight ───────────────────────────────────────────────────────


def test_get_section_weight_known_section():
    assert _get_section_weight("results") == SECTION_WEIGHTS["results"]


def test_get_section_weight_unknown_section_defaults():
    assert _get_section_weight("totally_unknown_section") == DEFAULT_WEIGHT


# ── _build_index ──────────────────────────────────────────────────────────────


def test_build_index_returns_object_with_get_scores():
    index = _build_index([["alpha", "beta"], ["gamma", "delta"]])
    scores = index.get_scores(["alpha"])
    assert len(scores) == 2


# ── search — empty input ──────────────────────────────────────────────────────


def test_search_empty_chunks_returns_empty_output():
    result = search(Bm25RetrieverInput(chunks=[], query="anything", top_k=5))
    assert isinstance(result, Bm25RetrieverOutput)
    assert result.top_chunks == []
    assert result.total_indexed == 0
    assert result.retrieved_k == 0


# ── search — ranking order ────────────────────────────────────────────────────


def test_search_ranks_exact_keyword_match_first():
    chunks = [
        make_chunk(0, section="results", chunk_text="The transformer model used attention."),
        make_chunk(1, section="results", chunk_text="Photosynthesis converts sunlight to energy."),
        make_chunk(2, section="results", chunk_text="Attention mechanisms improve transformer accuracy."),
    ]
    result = search(Bm25RetrieverInput(chunks=chunks, query="transformer attention", top_k=3))

    assert result.total_indexed == 3
    assert result.retrieved_k == 3
    # Chunks containing both query terms should outrank the unrelated chunk.
    top_chunk_ids = [c.chunk.chunk_id for c in result.top_chunks[:2]]
    assert chunks[1].chunk_id not in top_chunk_ids


def test_search_assigns_sequential_1_based_ranks():
    chunks = [make_chunk(i, chunk_text=f"keyword number {i}") for i in range(4)]
    result = search(Bm25RetrieverInput(chunks=chunks, query="keyword", top_k=4))
    assert [c.rank for c in result.top_chunks] == [1, 2, 3, 4]


# ── search — section weighting ────────────────────────────────────────────────


def test_search_section_weight_breaks_ties_in_favor_of_higher_priority():
    # Identical text -> identical raw BM25 score; weighted_score must differ
    # according to SECTION_WEIGHTS, and the higher-weighted section must rank first.
    # A third unrelated filler chunk keeps the shared term's IDF positive
    # (BM25 IDF goes negative when a term appears in every document of a tiny
    # corpus, which would invert the expected ordering).
    low_priority_chunk = make_chunk(0, section="related_work", chunk_text="shared keyword text")
    high_priority_chunk = make_chunk(1, section="results", chunk_text="shared keyword text")
    filler_chunk = make_chunk(2, section="unknown", chunk_text="completely unrelated filler content")

    result = search(
        Bm25RetrieverInput(
            chunks=[low_priority_chunk, high_priority_chunk, filler_chunk],
            query="shared keyword",
            top_k=3,
        )
    )

    assert result.top_chunks[0].chunk.section == "results"
    assert result.top_chunks[0].raw_score == result.top_chunks[1].raw_score
    assert result.top_chunks[0].weighted_score > result.top_chunks[1].weighted_score


def test_search_weighted_score_equals_raw_score_times_section_weight():
    chunk = make_chunk(0, section="methods", chunk_text="distinctive keyword phrase")
    result = search(Bm25RetrieverInput(chunks=[chunk], query="distinctive keyword", top_k=1))

    top = result.top_chunks[0]
    expected_weighted = round(top.raw_score * SECTION_WEIGHTS["methods"], 6)
    assert top.weighted_score == expected_weighted


# ── search — top_k limiting ───────────────────────────────────────────────────


def test_search_limits_results_to_top_k():
    chunks = [make_chunk(i, chunk_text=f"keyword {i}") for i in range(10)]
    result = search(Bm25RetrieverInput(chunks=chunks, query="keyword", top_k=3))
    assert result.retrieved_k == 3
    assert len(result.top_chunks) == 3
    assert result.total_indexed == 10


def test_search_top_k_larger_than_corpus_returns_all_chunks():
    chunks = [make_chunk(i, chunk_text=f"keyword {i}") for i in range(2)]
    result = search(Bm25RetrieverInput(chunks=chunks, query="keyword", top_k=10))
    assert result.retrieved_k == 2
    assert len(result.top_chunks) == 2
