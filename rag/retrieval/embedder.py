"""
Embedding module for the verifAi RAG pipeline (SCRUM-180).

Responsibility: take a list of text chunks (with metadata) and return each
chunk paired with its dense vector representation. These vectors are later
loaded into a temporary FAISS index for similarity search.

Model used: text-embedding-3-small (OpenAI)
  - 1536 dimensions
  - Optimised for retrieval / semantic search tasks
  - Same tokeniser as the chunker (cl100k_base), so token-count estimates align

Key design choices:
  - Batching: we send chunks in groups of BATCH_SIZE (100) to avoid hitting
    the API's per-request token ceiling and to make retry logic simpler.
  - Exponential backoff: on a RateLimitError we wait 2 → 4 → 8 seconds before
    retrying. This is the standard pattern for any metered API.
  - Lazy client: the OpenAI client is built inside embed_chunks() from the
    OPENAI_API_KEY env var, not at module import time. This means tests can
    import this module without a real key present.
"""

import logging
import os
import time

from openai import OpenAI, RateLimitError, APIError

from rag.ingestion.models import ChunkMetadata
from rag.retrieval.models import EmbeddedChunk, EmbedderInput, EmbedderOutput

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# Number of chunks sent in a single API call. OpenAI allows up to 2048 inputs
# per request, but batching at 100 keeps individual payloads small and makes
# partial-failure handling straightforward.
BATCH_SIZE = 100

# Retry configuration for rate-limit errors (429 responses).
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2  # wait = BACKOFF_BASE_SECONDS ** attempt (2, 4, 8 s)


# ── Private helpers ───────────────────────────────────────────────────────────


def _embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """
    Call the OpenAI embeddings API for a single batch of texts.

    Retries up to MAX_RETRIES times on RateLimitError with exponential backoff.
    Raises immediately on other API errors so the caller knows what went wrong.

    Args:
        client: Authenticated OpenAI client.
        texts:  List of strings to embed (max BATCH_SIZE).

    Returns:
        List of embedding vectors, one per input text, in the same order.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.embeddings.create(
                input=texts,
                model=EMBEDDING_MODEL,
            )
            # The API returns objects sorted by index, so order is preserved.
            return [item.embedding for item in response.data]

        except RateLimitError:
            if attempt == MAX_RETRIES:
                logger.error("Rate limit hit after %d attempts — giving up.", MAX_RETRIES)
                raise
            wait = BACKOFF_BASE_SECONDS ** attempt
            logger.warning(
                "Rate limit hit (attempt %d/%d). Retrying in %ds …",
                attempt, MAX_RETRIES, wait,
            )
            time.sleep(wait)

        except APIError as exc:
            # Non-rate-limit API errors (auth failure, bad request, etc.)
            # are not retried — they require investigation.
            logger.error("OpenAI API error on attempt %d: %s", attempt, exc)
            raise


def _build_client() -> OpenAI:
    """
    Build and return an OpenAI-compatible client pointed at OpenRouter.

    Raises EnvironmentError if OPENROUTER_API_KEY is not set, with a clear
    message so developers know exactly what is missing.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file."
        )
    return OpenAI(api_key=api_key, base_url=base_url)


# ── Public API ────────────────────────────────────────────────────────────────


def embed_chunks(input_data: EmbedderInput) -> EmbedderOutput:
    """
    Embed all chunks for a single paper and return them paired with their vectors.

    The function:
      1. Builds an OpenAI client from the OPENAI_API_KEY env var.
      2. Groups chunks into batches of BATCH_SIZE.
      3. For each batch, calls the embeddings API with retry/backoff.
      4. Pairs each returned vector with its original ChunkMetadata.

    Args:
        input_data: EmbedderInput containing the list of chunks and the DOI.

    Returns:
        EmbedderOutput with every chunk paired with its embedding vector.

    Raises:
        EnvironmentError: if OPENAI_API_KEY is not set.
        RateLimitError:   if the rate limit is hit after MAX_RETRIES attempts.
        APIError:         on any other non-retryable OpenAI API error.
    """
    client = _build_client()
    chunks = input_data.chunks
    doi = input_data.doi

    if not chunks:
        logger.warning("DOI %s — embed_chunks called with empty chunk list.", doi)
        return EmbedderOutput(
            doi=doi,
            embedded_chunks=[],
            total_embedded=0,
            embedding_model=EMBEDDING_MODEL,
            embedding_dimensions=EMBEDDING_DIMENSIONS,
        )

    logger.info(
        "DOI %s — embedding %d chunks in batches of %d using %s.",
        doi, len(chunks), BATCH_SIZE, EMBEDDING_MODEL,
    )

    embedded: list[EmbeddedChunk] = []

    # Process in fixed-size batches.
    for batch_start in range(0, len(chunks), BATCH_SIZE):
        batch: list[ChunkMetadata] = chunks[batch_start : batch_start + BATCH_SIZE]
        texts = [c.chunk_text for c in batch]

        logger.debug(
            "DOI %s — embedding batch %d–%d (%d chunks).",
            doi, batch_start, batch_start + len(batch) - 1, len(batch),
        )

        vectors = _embed_batch(client, texts)

        for chunk, vector in zip(batch, vectors):
            embedded.append(EmbeddedChunk(chunk=chunk, embedding=vector))

    logger.info("DOI %s — successfully embedded %d/%d chunks.", doi, len(embedded), len(chunks))

    return EmbedderOutput(
        doi=doi,
        embedded_chunks=embedded,
        total_embedded=len(embedded),
        embedding_model=EMBEDDING_MODEL,
        embedding_dimensions=EMBEDDING_DIMENSIONS,
    )
