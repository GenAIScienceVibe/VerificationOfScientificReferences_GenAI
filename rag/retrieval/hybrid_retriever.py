"""
Hybrid retrieval merger for the verifAi RAG pipeline (SCRUM-258).

Responsibility: take the dense FAISS results (vector_store.py) and the
keyword BM25 results (bm25_retriever.py) for the same claim, deduplicate
chunks that appear in both, and combine their rankings into a single
unified list using Reciprocal Rank Fusion (RRF).

Key design choices:
  - Rank-based fusion, not score-based: dense cosine similarity and BM25
    scores live on completely different scales (0-1 vs unbounded), so they
    cannot be summed directly. RRF instead combines each chunk's *rank
    position* in each list, which is scale-free.
  - RRF_K = 60: the standard smoothing constant from the original RRF paper
    (Cormack et al., 2009). It dampens the gap between rank 1 and rank 2 so
    that a chunk ranked highly by only one retriever doesn't automatically
    dominate a chunk ranked moderately well by both.
  - Chunks absent from one source contribute 0 from that source, not a
    penalty — being found by only one retriever is still meaningful signal.
  - In-memory only: like vector_store.py and bm25_retriever.py, this module
    holds no state between calls.
"""

import logging

from rag.ingestion.models import ChunkMetadata
from rag.retrieval.models import (
    HybridRetrievedChunk,
    HybridRetrieverInput,
    HybridRetrieverOutput,
)

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# Standard RRF smoothing constant (Cormack, Clarke & Buettcher, 2009).
RRF_K: int = 60


# ── Private helpers ────────────────────────────────────────────────────────────


def _rrf_score(rank: int) -> float:
    """Return the Reciprocal Rank Fusion contribution for a 1-based rank."""
    return 1.0 / (RRF_K + rank)


# ── Public API ─────────────────────────────────────────────────────────────────


def merge(input_data: HybridRetrieverInput) -> HybridRetrieverOutput:
    """Merge dense and BM25 results into a unified ranking via RRF.

    Pipeline:
      1. Walk the dense results, recording each chunk's dense rank and
         RRF contribution, keyed by chunk_id.
      2. Walk the BM25 results, adding each chunk's BM25 rank and RRF
         contribution to the same per-chunk_id record (creating a new
         record if the chunk wasn't in the dense results).
      3. Sort all unique chunks by combined rrf_score descending.
      4. Take the top-k and assign final 1-based ranks.

    Args:
        input_data: HybridRetrieverInput containing dense_results,
                    bm25_results, and the desired top_k.

    Returns:
        HybridRetrieverOutput with the unified ranked list.
    """
    top_k = input_data.top_k

    # chunk_id -> (chunk, accumulated rrf_score, dense_rank, bm25_rank)
    merged: dict[str, list] = {}

    for rc in input_data.dense_results.top_chunks:
        chunk: ChunkMetadata = rc.chunk
        merged[chunk.chunk_id] = [chunk, _rrf_score(rc.rank), rc.rank, None]

    for bc in input_data.bm25_results.top_chunks:
        chunk = bc.chunk
        if chunk.chunk_id in merged:
            merged[chunk.chunk_id][1] += _rrf_score(bc.rank)
            merged[chunk.chunk_id][3] = bc.rank
        else:
            merged[chunk.chunk_id] = [chunk, _rrf_score(bc.rank), None, bc.rank]

    total_unique = len(merged)

    if total_unique == 0:
        logger.warning("Hybrid merge called with no dense or BM25 results; returning empty.")
        return HybridRetrieverOutput(top_chunks=[], total_unique=0)

    ranked = sorted(merged.values(), key=lambda entry: entry[1], reverse=True)

    final_chunks = [
        HybridRetrievedChunk(
            chunk=chunk,
            rrf_score=round(rrf_score, 6),
            dense_rank=dense_rank,
            bm25_rank=bm25_rank,
            rank=rank_idx,
        )
        for rank_idx, (chunk, rrf_score, dense_rank, bm25_rank) in enumerate(
            ranked[:top_k], start=1
        )
    ]

    logger.info(
        "Hybrid merge — %d unique chunks; returning top %d.", total_unique, len(final_chunks)
    )

    return HybridRetrieverOutput(top_chunks=final_chunks, total_unique=total_unique)
