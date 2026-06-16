"""
Unit tests for rag/retrieval/vector_store.py (SCRUM-186).

Testing strategy:
  - No mocking of FAISS: it is a local computation library with no external
    dependencies, so we test it for real.  This gives us confidence that the
    normalisation, indexing, and scoring math is actually correct.
  - 8-dimensional unit vectors: small enough that expected cosine similarities
    can be verified by hand, large enough that FAISS behaves normally.
  - Helpers (make_embedded_chunk, make_embedder_output, make_search_input)
    build minimal but fully valid objects so each test reads as a clear scenario.
"""

import math

import numpy as np
import pytest

from rag.ingestion.models import ChunkMetadata, EvidenceAvailability
from rag.retrieval.embedder import EMBEDDING_DIMENSIONS
from rag.retrieval.models import (
    EmbeddedChunk,
    EmbedderOutput,
    RetrievedChunk,
    VectorStoreInput,
    VectorStoreOutput,
)
from rag.retrieval.vector_store import (
    DEFAULT_WEIGHT,
    LOW_CONFIDENCE_WARNING,
    OVERSAMPLE_FACTOR,
    SECTION_WEIGHTS,
    SIMILARITY_THRESHOLD,
    _build_index,
    _get_section_weight,
    _normalise,
    _to_float32,
    search,
)

# ── Test constants ─────────────────────────────────────────────────────────────

TEST_DIM = 8          # small dimension keeps tests fast; FAISS is dimension-agnostic
TEST_DOI = "10.0000/test.2024"


# ── Fixtures / helpers ─────────────────────────────────────────────────────────


def unit_vec(dominant: int, dim: int = TEST_DIM) -> list[float]:
    """Return a unit vector with 1.0 at position `dominant` and 0.0 elsewhere."""
    v = [0.0] * dim
    v[dominant] = 1.0
    return v


def make_embedded_chunk(
    index: int = 0,
    section: str = "results",
    embedding: list[float] | None = None,
    doi: str = TEST_DOI,
) -> EmbeddedChunk:
    """Build a minimal EmbeddedChunk for testing."""
    if embedding is None:
        embedding = unit_vec(0)
    priority = SECTION_WEIGHTS.get(section, DEFAULT_WEIGHT)
    chunk = ChunkMetadata(
        chunk_id=f"10_0000_test_chunk_{index:03d}",
        section=section,
        priority=priority,
        chunk_index=index,
        paper_doi=doi,
        evidence_type="FULL_TEXT",
        chunk_text=f"Test chunk {index} from section {section}.",
        token_count=10,
    )
    return EmbeddedChunk(chunk=chunk, embedding=embedding)


def make_embedder_output(
    chunks: list[EmbeddedChunk],
    doi: str = TEST_DOI,
) -> EmbedderOutput:
    """Wrap a list of EmbeddedChunk objects in an EmbedderOutput."""
    return EmbedderOutput(
        doi=doi,
        embedded_chunks=chunks,
        total_embedded=len(chunks),
        embedding_model="openai/text-embedding-3-small",
        embedding_dimensions=TEST_DIM,
    )


def make_search_input(
    chunks: list[EmbeddedChunk],
    query: list[float] | None = None,
    top_k: int = 3,
    doi: str = TEST_DOI,
) -> VectorStoreInput:
    """Build a VectorStoreInput from a chunk list and optional query vector."""
    if query is None:
        query = unit_vec(0)
    return VectorStoreInput(
        embedder_output=make_embedder_output(chunks, doi=doi),
        query_embedding=query,
        top_k=top_k,
    )


# ── _to_float32 ───────────────────────────────────────────────────────────────


class TestToFloat32:
    def test_output_dtype_is_float32(self):
        result = _to_float32([[1.0, 0.0], [0.0, 1.0]])
        assert result.dtype == np.float32

    def test_shape_matches_input(self):
        vecs = [[float(i)] * TEST_DIM for i in range(5)]
        result = _to_float32(vecs)
        assert result.shape == (5, TEST_DIM)


# ── _normalise ────────────────────────────────────────────────────────────────


class TestNormalise:
    def test_each_row_has_unit_l2_norm(self):
        raw = _to_float32([[3.0, 4.0], [1.0, 0.0], [0.0, 5.0]])
        normed = _normalise(raw)
        for row in normed:
            norm = math.sqrt(sum(float(x) ** 2 for x in row))
            assert abs(norm - 1.0) < 1e-5

    def test_does_not_mutate_input(self):
        raw = _to_float32([[3.0, 4.0]])
        original_value = float(raw[0, 0])
        _normalise(raw)
        assert float(raw[0, 0]) == original_value

    def test_normalised_identical_vectors_have_dot_product_one(self):
        """Inner product of a unit vector with itself must equal 1.0."""
        raw = _to_float32([[3.0, 4.0]])
        normed = _normalise(raw)
        dot = float(np.dot(normed[0], normed[0]))
        assert abs(dot - 1.0) < 1e-5


# ── _get_section_weight ───────────────────────────────────────────────────────


class TestGetSectionWeight:
    def test_results_section_returns_1_3(self):
        assert _get_section_weight("results") == 1.3

    def test_related_work_returns_0_8(self):
        assert _get_section_weight("related_work") == 0.8

    def test_unknown_section_returns_default(self):
        assert _get_section_weight("completely_made_up") == DEFAULT_WEIGHT

    def test_all_defined_sections_return_correct_weights(self):
        for section, expected in SECTION_WEIGHTS.items():
            assert _get_section_weight(section) == expected


# ── _build_index ──────────────────────────────────────────────────────────────


class TestBuildIndex:
    def test_ntotal_equals_number_of_vectors(self):
        vecs = _normalise(_to_float32([unit_vec(i) for i in range(5)]))
        index = _build_index(vecs)
        assert index.ntotal == 5

    def test_index_dimension_matches_input(self):
        vecs = _normalise(_to_float32([unit_vec(0)]))
        index = _build_index(vecs)
        assert index.d == TEST_DIM

    def test_exact_match_query_returns_score_near_one(self):
        """A query identical to an indexed vector must return cosine ≈ 1.0."""
        vec = _to_float32([unit_vec(0)])
        normed = _normalise(vec)
        index = _build_index(normed)
        distances, _ = index.search(normed, 1)
        assert abs(float(distances[0, 0]) - 1.0) < 1e-5


# ── search ─────────────────────────────────────────────────────────────────────


class TestSearch:
    def test_returns_vector_store_output_type(self):
        chunks = [make_embedded_chunk(0)]
        result = search(make_search_input(chunks))
        assert isinstance(result, VectorStoreOutput)

    def test_empty_chunks_returns_empty_output(self):
        result = search(make_search_input([]))
        assert result.top_chunks == []
        assert result.total_indexed == 0
        assert result.retrieved_k == 0

    def test_doi_passed_through_from_embedder_output(self):
        chunks = [make_embedded_chunk(0)]
        result = search(make_search_input(chunks, doi="10.9999/paper"))
        assert result.doi == "10.9999/paper"

    def test_returns_at_most_top_k_results(self):
        chunks = [make_embedded_chunk(i) for i in range(10)]
        result = search(make_search_input(chunks, top_k=3))
        assert len(result.top_chunks) == 3

    def test_when_fewer_chunks_than_top_k_returns_all(self):
        """With only 2 chunks and top_k=10, we should get 2 results back."""
        chunks = [make_embedded_chunk(i) for i in range(2)]
        result = search(make_search_input(chunks, top_k=10))
        assert len(result.top_chunks) == 2
        assert result.retrieved_k == 2

    def test_results_sorted_by_weighted_score_descending(self):
        chunks = [make_embedded_chunk(i) for i in range(5)]
        result = search(make_search_input(chunks, top_k=5))
        scores = [c.weighted_score for c in result.top_chunks]
        assert scores == sorted(scores, reverse=True)

    def test_rank_is_1_based_and_sequential(self):
        chunks = [make_embedded_chunk(i) for i in range(4)]
        result = search(make_search_input(chunks, top_k=4))
        ranks = [c.rank for c in result.top_chunks]
        assert ranks == list(range(1, len(result.top_chunks) + 1))

    def test_total_indexed_matches_chunk_count(self):
        chunks = [make_embedded_chunk(i) for i in range(7)]
        result = search(make_search_input(chunks, top_k=3))
        assert result.total_indexed == 7

    def test_retrieved_k_matches_len_of_top_chunks(self):
        chunks = [make_embedded_chunk(i) for i in range(5)]
        result = search(make_search_input(chunks, top_k=3))
        assert result.retrieved_k == len(result.top_chunks)

    def test_most_similar_chunk_ranks_first(self):
        """The chunk whose embedding most closely aligns with the query must be rank 1.

        Chunk 0: embedding = [1, 0, 0, ...]  — cosine 1.0 with query [1, 0, ...]
        Chunk 1: embedding = [0, 1, 0, ...]  — cosine 0.0 with query [1, 0, ...]
        Both in the same section ("results") so section weight doesn't interfere.
        """
        chunk_0 = make_embedded_chunk(0, section="results", embedding=unit_vec(0))
        chunk_1 = make_embedded_chunk(1, section="results", embedding=unit_vec(1))
        query = unit_vec(0)

        result = search(make_search_input([chunk_0, chunk_1], query=query, top_k=2))

        assert result.top_chunks[0].chunk.chunk_id == chunk_0.chunk.chunk_id
        assert result.top_chunks[0].rank == 1

    def test_section_weights_applied_to_equal_cosine_scores(self):
        """Two chunks with the same embedding must be ranked by section weight.

        Both chunks are identical to the query, so raw cosine = 1.0 for each.
        Chunk A is in 'results' (weight 1.3); chunk B in 'related_work' (0.8).
        After weighting, A must rank above B.
        """
        chunk_a = make_embedded_chunk(0, section="results",      embedding=unit_vec(0))
        chunk_b = make_embedded_chunk(1, section="related_work", embedding=unit_vec(0))
        query = unit_vec(0)

        result = search(make_search_input([chunk_a, chunk_b], query=query, top_k=2))

        assert result.top_chunks[0].chunk.section == "results"
        assert result.top_chunks[1].chunk.section == "related_work"
        assert result.top_chunks[0].weighted_score > result.top_chunks[1].weighted_score

    def test_weighted_score_equals_raw_times_weight(self):
        """weighted_score must equal raw_score × SECTION_WEIGHTS[section]."""
        chunk = make_embedded_chunk(0, section="results", embedding=unit_vec(0))
        query = unit_vec(0)

        result = search(make_search_input([chunk], query=query, top_k=1))

        rc = result.top_chunks[0]
        expected = round(rc.raw_score * SECTION_WEIGHTS["results"], 6)
        assert abs(rc.weighted_score - expected) < 1e-5

    def test_raw_score_is_cosine_similarity(self):
        """For an exact-match query, raw_score must be very close to 1.0."""
        chunk = make_embedded_chunk(0, section="results", embedding=unit_vec(0))
        query = unit_vec(0)

        result = search(make_search_input([chunk], query=query, top_k=1))

        assert abs(result.top_chunks[0].raw_score - 1.0) < 1e-5

    def test_orthogonal_chunk_has_low_raw_score(self):
        """A chunk orthogonal to the query (cosine = 0) must score near 0."""
        chunk = make_embedded_chunk(0, section="results", embedding=unit_vec(1))
        query = unit_vec(0)

        result = search(make_search_input([chunk], query=query, top_k=1))

        assert abs(result.top_chunks[0].raw_score) < 1e-5

    def test_chunk_metadata_preserved_in_output(self):
        """Every field of ChunkMetadata must survive the round-trip intact."""
        chunk = make_embedded_chunk(0, section="methods", embedding=unit_vec(0))
        result = search(make_search_input([chunk], top_k=1))

        out_chunk = result.top_chunks[0].chunk
        assert out_chunk.chunk_id    == chunk.chunk.chunk_id
        assert out_chunk.section     == chunk.chunk.section
        assert out_chunk.priority    == chunk.chunk.priority
        assert out_chunk.paper_doi   == chunk.chunk.paper_doi
        assert out_chunk.chunk_text  == chunk.chunk.chunk_text

    def test_dimension_mismatch_raises_value_error(self):
        """Query embedding with wrong dimension must raise ValueError."""
        chunk = make_embedded_chunk(0, embedding=unit_vec(0))          # dim=TEST_DIM
        wrong_query = [1.0] * (TEST_DIM + 4)                          # wrong dim

        with pytest.raises(ValueError, match="dimensions"):
            search(make_search_input([chunk], query=wrong_query))

    def test_priority_weighting_can_promote_lower_cosine_chunk(self):
        """A chunk from 'results' with slightly lower cosine can beat a 'related_work'
        chunk with a higher cosine once section weights are applied.

        Chunk A (results, weight 1.3):  embedding at 45° to query → cosine ≈ 0.707
        Chunk B (related_work, 0.8):    embedding identical to query → cosine = 1.0

        Weighted scores:
          A = 0.707 × 1.3 ≈ 0.919
          B = 1.0   × 0.8 = 0.800

        So A should rank above B despite lower raw cosine.
        """
        # 45-degree vector in first two dimensions: [1/√2, 1/√2, 0, ...]
        half = 1.0 / math.sqrt(2)
        diagonal = [half, half] + [0.0] * (TEST_DIM - 2)

        chunk_a = make_embedded_chunk(0, section="results",      embedding=diagonal)
        chunk_b = make_embedded_chunk(1, section="related_work", embedding=unit_vec(0))
        query = unit_vec(0)

        result = search(make_search_input([chunk_a, chunk_b], query=query, top_k=2))

        assert result.top_chunks[0].chunk.section == "results"
        assert result.top_chunks[1].chunk.section == "related_work"


# ── Similarity threshold check ──────────────────────────────────────────────────


class TestSimilarityThreshold:
    def test_threshold_constant_value(self):
        assert SIMILARITY_THRESHOLD == 0.5

    def test_high_similarity_sets_low_confidence_false(self):
        """An exact-match chunk (cosine 1.0, weight 1.0) clears the threshold easily."""
        chunk = make_embedded_chunk(0, section="abstract", embedding=unit_vec(0))
        query = unit_vec(0)

        result = search(make_search_input([chunk], query=query, top_k=1))

        assert result.top_chunks[0].weighted_score >= SIMILARITY_THRESHOLD
        assert result.low_confidence is False
        assert result.warning is None

    def test_low_similarity_sets_low_confidence_true(self):
        """An orthogonal chunk (cosine ≈ 0) falls far below the threshold.

        Chunk embedding is orthogonal to the query, so raw cosine ≈ 0 and
        weighted_score ≈ 0, well under SIMILARITY_THRESHOLD (0.5).
        """
        chunk = make_embedded_chunk(0, section="abstract", embedding=unit_vec(1))
        query = unit_vec(0)

        result = search(make_search_input([chunk], query=query, top_k=1))

        assert result.top_chunks[0].weighted_score < SIMILARITY_THRESHOLD
        assert result.low_confidence is True
        assert result.warning == LOW_CONFIDENCE_WARNING

    def test_low_confidence_warning_message_text(self):
        chunk = make_embedded_chunk(0, section="abstract", embedding=unit_vec(1))
        query = unit_vec(0)

        result = search(make_search_input([chunk], query=query, top_k=1))

        assert result.warning == (
            "Best chunk similarity below threshold — evidence may be insufficient"
        )

    def test_borderline_score_just_above_threshold_is_not_flagged(self):
        """A 45° angle gives cosine ≈ 0.707; with weight 1.0 this clears 0.5."""
        half = 1.0 / math.sqrt(2)
        diagonal = [half, half] + [0.0] * (TEST_DIM - 2)

        chunk = make_embedded_chunk(0, section="abstract", embedding=diagonal)
        query = unit_vec(0)

        result = search(make_search_input([chunk], query=query, top_k=1))

        assert result.top_chunks[0].weighted_score > SIMILARITY_THRESHOLD
        assert result.low_confidence is False
        assert result.warning is None

    def test_only_best_chunk_score_determines_flag(self):
        """Even if lower-ranked chunks are weak, a strong top chunk keeps low_confidence False."""
        strong_chunk = make_embedded_chunk(0, section="abstract", embedding=unit_vec(0))
        weak_chunk = make_embedded_chunk(1, section="abstract", embedding=unit_vec(1))
        query = unit_vec(0)

        result = search(make_search_input([strong_chunk, weak_chunk], query=query, top_k=2))

        assert result.top_chunks[0].chunk.chunk_id == strong_chunk.chunk.chunk_id
        assert result.low_confidence is False
        assert result.warning is None

    def test_empty_chunks_does_not_set_low_confidence(self):
        """No chunks to score means low_confidence stays False (no evidence claim made here)."""
        result = search(make_search_input([]))
        assert result.low_confidence is False
        assert result.warning is None

    def test_low_confidence_field_defaults_false_on_model(self):
        """VectorStoreOutput constructed without low_confidence defaults to False/None."""
        output = VectorStoreOutput(
            doi=TEST_DOI,
            top_chunks=[],
            total_indexed=0,
            retrieved_k=0,
        )
        assert output.low_confidence is False
        assert output.warning is None
