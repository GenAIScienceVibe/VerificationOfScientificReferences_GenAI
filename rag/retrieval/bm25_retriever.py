"""
BM25 keyword retrieval module for the verifAi RAG pipeline (SCRUM-257).

Responsibility: given the same chunks (list of ChunkMetadata) used by
vector_store.py, build a BM25 keyword index and score them against the claim
text. This is the keyword-search half of hybrid retrieval — it catches exact
term matches (numbers, names, acronyms) that dense embeddings can blur.

Key design choices:
  - In-memory only: like vector_store.py, the BM25Okapi index is built per
    request and discarded when search() returns. We own no persistent storage.
  - Same section priority weights as vector_store.py: SECTION_WEIGHTS is
    imported (not duplicated) so dense and keyword scores are biased the same
    way before they are merged downstream by hybrid_retriever.py.
  - Simple lowercase whitespace tokenisation: BM25 only needs token overlap,
    not semantic understanding, so a lightweight tokeniser is sufficient and
    keeps this module dependency-free beyond rank_bm25 itself.
  - Graceful empty-index fallback: an empty chunk list returns an empty
    Bm25RetrieverOutput instead of raising, mirroring vector_store.search().
"""

import logging
import re

from rank_bm25 import BM25Okapi

from rag.ingestion.models import ChunkMetadata
from rag.retrieval.models import Bm25RetrievedChunk, Bm25RetrieverInput, Bm25RetrieverOutput
from rag.retrieval.vector_store import DEFAULT_WEIGHT, SECTION_WEIGHTS

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# Matches runs of word characters; used to tokenise both chunk text and query.
_TOKEN_PATTERN = re.compile(r"\w+")


# ── Private helpers ────────────────────────────────────────────────────────────


def _tokenize(text: str) -> list[str]:
    """Lower-case and split text into word tokens for BM25 indexing/querying."""
    return _TOKEN_PATTERN.findall(text.lower())


def _get_section_weight(section: str) -> float:
    """Return the priority weight for a section name, defaulting to DEFAULT_WEIGHT.

    Reuses the same SECTION_WEIGHTS table as vector_store.py so dense and
    keyword scores are comparable when merged by hybrid_retriever.py.
    """
    return SECTION_WEIGHTS.get(section, DEFAULT_WEIGHT)


def _build_index(tokenized_corpus: list[list[str]]) -> BM25Okapi:
    """Build and return a BM25Okapi index from a tokenized chunk corpus."""
    return BM25Okapi(tokenized_corpus)


# ── Public API ─────────────────────────────────────────────────────────────────


def search(input_data: Bm25RetrieverInput) -> Bm25RetrieverOutput:
    """Build a temporary BM25 index and return the top-k most relevant chunks.

    Pipeline:
      1. Tokenize every chunk's text into a corpus.
      2. Build a BM25Okapi index from that corpus.
      3. Tokenize the claim query and score it against every chunk.
      4. Multiply each raw BM25 score by its section priority weight.
      5. Sort candidates by weighted score descending, take the top-k.
      6. Return Bm25RetrieverOutput — the BM25 index is then discarded.

    Args:
        input_data: Bm25RetrieverInput containing the chunks, claim query,
                    and desired top_k.

    Returns:
        Bm25RetrieverOutput with ranked chunks, scores, and index statistics.
    """
    chunks: list[ChunkMetadata] = input_data.chunks
    top_k = input_data.top_k

    if not chunks:
        logger.warning("BM25 search called with no chunks; returning empty.")
        return Bm25RetrieverOutput(top_chunks=[], total_indexed=0, retrieved_k=0)

    # ── 1. Tokenize and build index ─────────────────────────────────────────────

    tokenized_corpus = [_tokenize(chunk.chunk_text) for chunk in chunks]
    index = _build_index(tokenized_corpus)
    total_indexed = len(chunks)

    # ── 2. Score query against every chunk ──────────────────────────────────────

    tokenized_query = _tokenize(input_data.query)
    raw_scores = index.get_scores(tokenized_query)

    # ── 3. Apply priority weights ────────────────────────────────────────────────

    candidates: list[tuple[float, float, ChunkMetadata]] = []
    for chunk, raw_score in zip(chunks, raw_scores):
        weight = _get_section_weight(chunk.section)
        weighted = float(raw_score) * weight
        candidates.append((weighted, float(raw_score), chunk))

    # ── 4. Re-sort and build output ──────────────────────────────────────────────

    candidates.sort(key=lambda t: t[0], reverse=True)

    final_chunks = [
        Bm25RetrievedChunk(
            chunk=chunk,
            raw_score=round(raw, 6),
            weighted_score=round(weighted, 6),
            rank=rank_idx,
        )
        for rank_idx, (weighted, raw, chunk) in enumerate(candidates[:top_k], start=1)
    ]

    logger.info(
        "BM25 — indexed %d chunks; returning top %d.", total_indexed, len(final_chunks)
    )

    return Bm25RetrieverOutput(
        top_chunks=final_chunks,
        total_indexed=total_indexed,
        retrieved_k=len(final_chunks),
    )
