"""
Hybrid retrieval merger and neural reranker for the verifAi RAG pipeline
(SCRUM-258 + SCRUM-259).

Responsibility: take the dense FAISS results (vector_store.py) and the
keyword BM25 results (bm25_retriever.py) for the same claim, deduplicate
chunks that appear in both, combine their rankings into a single unified
list using Reciprocal Rank Fusion (RRF), then reorder the top candidates
by true semantic relevance using FlashRank neural reranking.

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
  - Rerank only the RRF top candidate pool, not everything: FlashRank is a
    real (if small) neural model call, so reranking the full unique-chunk
    set would be wasteful when RRF has already pushed clearly irrelevant
    chunks to the bottom. We oversample RERANK_OVERSAMPLE_FACTOR × top_k
    candidates from the RRF ranking and only rerank those.
  - Lazy ranker: the FlashRank Ranker is built inside _build_ranker(), not
    at module import time, mirroring the lazy-client pattern in
    embedder.py/classifier.py so importing this module never triggers a
    model download.
  - Reranking never fails the pipeline: if FlashRank raises for any reason,
    we log a warning and fall back to the RRF-only ordering.
  - In-memory only: like vector_store.py and bm25_retriever.py, this module
    holds no state between calls.
"""

import logging

from flashrank import Ranker, RerankRequest

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

# Small, fast default FlashRank model — sufficient for reranking short
# claim/chunk pairs without the latency cost of a larger cross-encoder.
RERANK_MODEL: str = "ms-marco-TinyBERT-L-2-v2"

# Rerank this many × top_k candidates from the RRF ranking. Oversampling
# gives the neural reranker enough material to promote a chunk that RRF
# under-ranked, without paying the model cost over the entire result set.
RERANK_OVERSAMPLE_FACTOR: int = 3


# ── Private helpers ────────────────────────────────────────────────────────────


def _rrf_score(rank: int) -> float:
    """Return the Reciprocal Rank Fusion contribution for a 1-based rank."""
    return 1.0 / (RRF_K + rank)


def _build_ranker() -> Ranker:
    """Build a FlashRank Ranker using the small default reranking model.

    Built lazily inside rerank steps, not at import time, so importing this
    module never triggers a model download.
    """
    return Ranker(model_name=RERANK_MODEL)


def _rerank(
    claim: str, candidates: list[tuple[ChunkMetadata, float, int | None, int | None]]
) -> dict[str, float]:
    """Rerank candidate chunks against the claim and return chunk_id -> rerank_score.

    Args:
        claim: The claim text used as the rerank query.
        candidates: (chunk, rrf_score, dense_rank, bm25_rank) tuples to rerank.

    Returns:
        Mapping from chunk_id to FlashRank relevance score.

    Raises:
        Exception: propagates any FlashRank failure; the caller decides the
                    fallback behaviour.
    """
    ranker = _build_ranker()
    passages = [
        {"id": chunk.chunk_id, "text": chunk.chunk_text} for chunk, _, _, _ in candidates
    ]
    request = RerankRequest(query=claim, passages=passages)
    results = ranker.rerank(request)
    return {result["id"]: float(result["score"]) for result in results}


# ── Public API ─────────────────────────────────────────────────────────────────


def merge(input_data: HybridRetrieverInput) -> HybridRetrieverOutput:
    """Merge dense and BM25 results via RRF, then rerank the top pool with FlashRank.

    Pipeline:
      1. Walk the dense results, recording each chunk's dense rank and
         RRF contribution, keyed by chunk_id.
      2. Walk the BM25 results, adding each chunk's BM25 rank and RRF
         contribution to the same per-chunk_id record (creating a new
         record if the chunk wasn't in the dense results).
      3. Sort all unique chunks by combined rrf_score descending.
      4. Take an oversampled candidate pool (top_k × RERANK_OVERSAMPLE_FACTOR)
         and rerank it against the claim with FlashRank. On any reranking
         failure, log a warning and keep the RRF-only order instead.
      5. Take the final top-k and assign 1-based ranks.

    Args:
        input_data: HybridRetrieverInput containing dense_results,
                    bm25_results, the claim text, and the desired top_k.

    Returns:
        HybridRetrieverOutput with the unified, reranked list.
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

    # ── Rerank the RRF top pool with FlashRank ──────────────────────────────────

    pool_size = min(total_unique, top_k * RERANK_OVERSAMPLE_FACTOR)
    candidate_pool = ranked[:pool_size]

    rerank_scores: dict[str, float] = {}
    try:
        rerank_scores = _rerank(input_data.claim, candidate_pool)
    except Exception:
        logger.warning(
            "FlashRank reranking failed; falling back to RRF-only ordering.", exc_info=True
        )

    if rerank_scores:
        candidate_pool.sort(key=lambda entry: rerank_scores.get(entry[0].chunk_id, 0.0), reverse=True)

    final_chunks = [
        HybridRetrievedChunk(
            chunk=chunk,
            rrf_score=round(rrf_score, 6),
            dense_rank=dense_rank,
            bm25_rank=bm25_rank,
            rerank_score=rerank_scores.get(chunk.chunk_id),
            rank=rank_idx,
        )
        for rank_idx, (chunk, rrf_score, dense_rank, bm25_rank) in enumerate(
            candidate_pool[:top_k], start=1
        )
    ]

    logger.info(
        "Hybrid merge — %d unique chunks; reranked pool of %d; returning top %d.",
        total_unique, len(candidate_pool), len(final_chunks),
    )

    return HybridRetrieverOutput(top_chunks=final_chunks, total_unique=total_unique)
