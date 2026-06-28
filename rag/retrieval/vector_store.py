"""
Vector store module for the verifAi RAG pipeline (SCRUM-186).

Responsibility: given an EmbedderOutput (embedded source-paper chunks), build a
temporary in-memory FAISS index, search it with a query embedding (the embedded
claim), apply section priority weights to the raw cosine scores, and return the
top-k most relevant chunks ranked by weighted score.

Key design choices:
  - In-memory only: the FAISS index is built per request inside search() and is
    garbage-collected when the function returns.  We own no persistent storage.
  - Cosine similarity via IndexFlatIP: we L2-normalise every vector before
    adding it to the index and before searching.  On unit vectors, inner
    product == cosine similarity, giving exact (not approximate) results.
  - Oversample then re-rank: we retrieve OVERSAMPLE_FACTOR × top_k candidates
    from FAISS by raw cosine first, then multiply each score by its section
    priority weight and re-sort.  This lets a high-priority section surface
    even when its raw cosine was not in the strict top-k.
  - Clean pipeline handoff: VectorStoreInput wraps EmbedderOutput directly, so
    the caller can pass embed_chunks() output straight into search() with no
    intermediate conversion.
"""

import logging

import faiss
import numpy as np

from rag.retrieval.models import (
    RetrievedChunk,
    VectorStoreInput,
    VectorStoreOutput,
)

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# Section priority weights: raw cosine score is multiplied by this factor.
# Higher weight means chunks from that section rise in the final ranking.
SECTION_WEIGHTS: dict[str, float] = {
    "results": 1.3,
    "methods": 1.3,
    "experiments": 1.3,
    "discussion": 1.1,
    "conclusion": 1.1,
    "introduction": 1.0,
    "abstract": 1.0,
    "related_work": 0.8,
    "future_work": 0.8,
    "unknown": 1.0,
}

# Fallback weight for any section name not in SECTION_WEIGHTS.
DEFAULT_WEIGHT: float = 1.0

# Retrieve this many candidates from FAISS before applying section weights.
# Oversampling gives the re-ranking step enough material to change the order.
OVERSAMPLE_FACTOR: int = 3

# Minimum weighted_score the best-ranked chunk must reach for the retrieval
# to be considered usable evidence. Below this, we flag low_confidence=True
# so the caller can short-circuit to INSUFFICIENT_EVIDENCE instead of sending
# weak evidence to the LLM.
SIMILARITY_THRESHOLD: float = 0.5

LOW_CONFIDENCE_WARNING: str = (
    "Best chunk similarity below threshold — evidence may be insufficient"
)


# ── Private helpers ────────────────────────────────────────────────────────────


def _to_float32(vectors: list[list[float]]) -> np.ndarray:
    """Convert a list of float vectors to a contiguous float32 numpy array.

    FAISS requires float32; using a contiguous array avoids an extra copy
    inside the FAISS C++ layer.
    """
    return np.array(vectors, dtype=np.float32)


def _normalise(matrix: np.ndarray) -> np.ndarray:
    """Return an L2-normalised copy of a 2-D float32 array.

    We work on a copy so the caller's data is never mutated.
    After normalisation, dot product == cosine similarity for any two rows.
    """
    matrix = matrix.copy()
    faiss.normalize_L2(matrix)
    return matrix


def _get_section_weight(section: str) -> float:
    """Return the priority weight for a section name, defaulting to DEFAULT_WEIGHT."""
    return SECTION_WEIGHTS.get(section, DEFAULT_WEIGHT)


def _build_index(normalised_embeddings: np.ndarray) -> faiss.IndexFlatIP:
    """Build and return a FAISS IndexFlatIP from already-normalised vectors.

    IndexFlatIP computes exact inner products — no approximation, no training.
    Because the vectors are L2-normalised, inner product equals cosine similarity.

    Args:
        normalised_embeddings: float32 array of shape (n, dim), already normalised.

    Returns:
        A populated FAISS index ready for search.
    """
    dim = normalised_embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(normalised_embeddings)
    return index


# ── Public API ─────────────────────────────────────────────────────────────────


def search(input_data: VectorStoreInput) -> VectorStoreOutput:
    """Build a temporary FAISS index and return the top-k most relevant chunks.

    Pipeline:
      1. Extract embeddings from EmbedderOutput and convert to float32.
      2. Validate that query dimension matches chunk dimension.
      3. L2-normalise all vectors (chunks + query).
      4. Build an in-memory IndexFlatIP and load chunk vectors.
      5. Search with an oversampled k (top_k × OVERSAMPLE_FACTOR).
      6. Multiply each raw cosine score by its section priority weight.
      7. Sort candidates by weighted score descending, take the final top-k.
      8. Check the best chunk's weighted_score against SIMILARITY_THRESHOLD;
         flag low_confidence=True if it falls short.
      9. Return VectorStoreOutput — the FAISS index is then discarded.

    Args:
        input_data: VectorStoreInput containing an EmbedderOutput, the query
                    embedding, and the desired top_k.

    Returns:
        VectorStoreOutput with ranked chunks, scores, and index statistics.

    Raises:
        ValueError: if the query embedding dimension does not match the chunks.
    """
    embedder_output = input_data.embedder_output
    embedded_chunks = embedder_output.embedded_chunks
    doi = embedder_output.doi
    top_k = input_data.top_k

    if not embedded_chunks:
        logger.warning("DOI %s — search called with no embedded chunks; returning empty.", doi)
        return VectorStoreOutput(doi=doi, top_chunks=[], total_indexed=0, retrieved_k=0)

    # ── 1. Prepare arrays ──────────────────────────────────────────────────────

    chunk_matrix = _to_float32([ec.embedding for ec in embedded_chunks])
    query_matrix = _to_float32([input_data.query_embedding])  # shape (1, dim)

    chunk_dim = chunk_matrix.shape[1]
    query_dim = query_matrix.shape[1]
    if query_dim != chunk_dim:
        raise ValueError(
            f"DOI {doi}: query embedding has {query_dim} dimensions but "
            f"chunk embeddings have {chunk_dim} dimensions."
        )

    # ── 2. Normalise and build index ───────────────────────────────────────────

    normalised_chunks = _normalise(chunk_matrix)
    normalised_query = _normalise(query_matrix)

    index = _build_index(normalised_chunks)
    total_indexed = index.ntotal

    # ── 3. Oversample search ───────────────────────────────────────────────────

    # Fetch more than top_k so priority weighting has room to reorder results.
    candidate_k = min(total_indexed, top_k * OVERSAMPLE_FACTOR)
    distances, indices = index.search(normalised_query, candidate_k)

    # distances / indices are shape (1, candidate_k); unwrap the batch dimension.
    raw_scores: list[float] = distances[0].tolist()
    hit_indices: list[int] = indices[0].tolist()

    # ── 4. Apply priority weights ──────────────────────────────────────────────

    # Accumulate (weighted_score, raw_score, chunk) tuples for sorting.
    candidates: list[tuple[float, float, object]] = []
    for idx, raw_score in zip(hit_indices, raw_scores):
        # FAISS fills unused slots with -1 when there are fewer results than k.
        if idx == -1:
            continue
        ec = embedded_chunks[idx]
        weight = _get_section_weight(ec.chunk.section)
        weighted = raw_score * weight
        candidates.append((weighted, float(raw_score), ec.chunk))

    # ── 5. Re-sort and build output ────────────────────────────────────────────

    candidates.sort(key=lambda t: t[0], reverse=True)

    final_chunks = [
        RetrievedChunk(
            chunk=chunk,
            raw_score=round(raw, 6),
            weighted_score=round(weighted, 6),
            rank=rank_idx,
        )
        for rank_idx, (weighted, raw, chunk) in enumerate(candidates[:top_k], start=1)
    ]

    logger.info(
        "DOI %s — indexed %d chunks; returning top %d (oversample pool=%d).",
        doi, total_indexed, len(final_chunks), candidate_k,
    )

    # ── 6. Similarity threshold check ──────────────────────────────────────────

    # If the best-ranked chunk doesn't clear SIMILARITY_THRESHOLD, the evidence
    # is too weak to be useful — flag it so the caller can skip LLM verification.
    low_confidence = False
    warning: str | None = None
    if final_chunks and final_chunks[0].weighted_score < SIMILARITY_THRESHOLD:
        low_confidence = True
        warning = LOW_CONFIDENCE_WARNING
        logger.warning(
            "DOI %s — best weighted_score %.4f below threshold %.2f. %s",
            doi, final_chunks[0].weighted_score, SIMILARITY_THRESHOLD, warning,
        )

    return VectorStoreOutput(
        doi=doi,
        top_chunks=final_chunks,
        total_indexed=total_indexed,
        retrieved_k=len(final_chunks),
        low_confidence=low_confidence,
        warning=warning,
    )
