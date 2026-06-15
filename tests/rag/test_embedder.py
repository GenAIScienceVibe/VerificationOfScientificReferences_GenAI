"""
Unit tests for rag/retrieval/embedder.py (SCRUM-180).

All tests use unittest.mock to replace the OpenAI client so that:
  - No real API calls are made (no cost, no key required).
  - We can simulate rate limits, API errors, and empty responses precisely.

Mocking strategy:
  - We patch 'rag.retrieval.embedder.OpenAI' so that _build_client() returns
    a mock object. We then configure mock_client.embeddings.create.return_value
    to look like a real API response.
"""

import os
from unittest.mock import MagicMock, patch, call

import pytest
from openai import RateLimitError, APIError

from rag.ingestion.models import ChunkMetadata, EvidenceAvailability
from rag.retrieval.embedder import (
    BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    MAX_RETRIES,
    _embed_batch,
    embed_chunks,
)
from rag.retrieval.models import EmbedderInput, EmbedderOutput, EmbeddedChunk


# ── Fixtures and helpers ──────────────────────────────────────────────────────


def make_chunk(index: int = 0, text: str = "Sample chunk text.") -> ChunkMetadata:
    """Build a minimal ChunkMetadata for testing."""
    return ChunkMetadata(
        chunk_id=f"10_0000_test_chunk_{index:03d}",
        section="results",
        priority=1.3,
        chunk_index=index,
        paper_doi="10.0000/test.2024",
        evidence_type="FULL_TEXT",
        chunk_text=text,
        token_count=4,
    )


def make_input(n_chunks: int = 3, doi: str = "10.0000/test.2024") -> EmbedderInput:
    """Build an EmbedderInput with n_chunks chunks."""
    return EmbedderInput(
        chunks=[make_chunk(i) for i in range(n_chunks)],
        doi=doi,
    )


def fake_embedding(dim: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Return a deterministic fake embedding vector of the correct dimension."""
    return [0.1] * dim


def make_api_response(n: int) -> MagicMock:
    """
    Build a mock that looks like an OpenAI embeddings API response.

    The real response has: response.data = [item, ...] where item.embedding
    is a list[float] and item.index is the position.
    """
    items = []
    for i in range(n):
        item = MagicMock()
        item.embedding = fake_embedding()
        item.index = i
        items.append(item)

    response = MagicMock()
    response.data = items
    return response


# ── _embed_batch ──────────────────────────────────────────────────────────────


class TestEmbedBatch:
    def test_returns_vectors_for_each_text(self):
        texts = ["text one", "text two", "text three"]
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = make_api_response(len(texts))

        vectors = _embed_batch(mock_client, texts)

        assert len(vectors) == len(texts)
        assert all(len(v) == EMBEDDING_DIMENSIONS for v in vectors)

    def test_calls_api_with_correct_model(self):
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = make_api_response(1)

        _embed_batch(mock_client, ["hello"])

        mock_client.embeddings.create.assert_called_once_with(
            input=["hello"],
            model=EMBEDDING_MODEL,
        )

    def test_retries_on_rate_limit_and_succeeds(self):
        """First call raises RateLimitError; second call succeeds."""
        mock_client = MagicMock()
        # Simulate a RateLimitError on first attempt
        rate_limit_exc = RateLimitError(
            message="rate limit exceeded",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"message": "rate limit exceeded"}},
        )
        mock_client.embeddings.create.side_effect = [
            rate_limit_exc,
            make_api_response(1),
        ]

        # Patch time.sleep to avoid actually waiting during tests.
        with patch("rag.retrieval.embedder.time.sleep") as mock_sleep:
            vectors = _embed_batch(mock_client, ["text"])

        assert len(vectors) == 1
        assert mock_client.embeddings.create.call_count == 2
        mock_sleep.assert_called_once()  # waited once between attempts

    def test_raises_after_max_retries_exceeded(self):
        """Rate limit on every attempt → raises after MAX_RETRIES."""
        mock_client = MagicMock()
        rate_limit_exc = RateLimitError(
            message="rate limit exceeded",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"message": "rate limit exceeded"}},
        )
        mock_client.embeddings.create.side_effect = rate_limit_exc

        with patch("rag.retrieval.embedder.time.sleep"):
            with pytest.raises(RateLimitError):
                _embed_batch(mock_client, ["text"])

        assert mock_client.embeddings.create.call_count == MAX_RETRIES

    def test_raises_immediately_on_api_error(self):
        """Non-rate-limit errors must not be retried."""
        mock_client = MagicMock()
        api_exc = APIError(
            message="invalid api key",
            request=MagicMock(),
            body={"error": {"message": "invalid api key"}},
        )
        mock_client.embeddings.create.side_effect = api_exc

        with pytest.raises(APIError):
            _embed_batch(mock_client, ["text"])

        # Must have been called exactly once — no retry on APIError
        assert mock_client.embeddings.create.call_count == 1


# ── embed_chunks ──────────────────────────────────────────────────────────────


class TestEmbedChunks:
    def test_returns_embedder_output_type(self):
        with patch("rag.retrieval.embedder.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.embeddings.create.return_value = make_api_response(3)
            os.environ["OPENROUTER_API_KEY"] = "test-key"

            result = embed_chunks(make_input(3))

        assert isinstance(result, EmbedderOutput)

    def test_total_embedded_matches_chunk_count(self):
        with patch("rag.retrieval.embedder.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.embeddings.create.return_value = make_api_response(5)
            os.environ["OPENROUTER_API_KEY"] = "test-key"

            result = embed_chunks(make_input(5))

        assert result.total_embedded == 5
        assert len(result.embedded_chunks) == 5

    def test_doi_passed_through(self):
        with patch("rag.retrieval.embedder.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.embeddings.create.return_value = make_api_response(1)
            os.environ["OPENROUTER_API_KEY"] = "test-key"

            result = embed_chunks(make_input(1, doi="10.9999/example"))

        assert result.doi == "10.9999/example"

    def test_embedding_model_field_correct(self):
        with patch("rag.retrieval.embedder.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.embeddings.create.return_value = make_api_response(1)
            os.environ["OPENROUTER_API_KEY"] = "test-key"

            result = embed_chunks(make_input(1))

        assert result.embedding_model == EMBEDDING_MODEL

    def test_embedding_dimensions_field_correct(self):
        with patch("rag.retrieval.embedder.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.embeddings.create.return_value = make_api_response(1)
            os.environ["OPENROUTER_API_KEY"] = "test-key"

            result = embed_chunks(make_input(1))

        assert result.embedding_dimensions == EMBEDDING_DIMENSIONS

    def test_each_embedded_chunk_has_correct_vector_length(self):
        with patch("rag.retrieval.embedder.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.embeddings.create.return_value = make_api_response(3)
            os.environ["OPENROUTER_API_KEY"] = "test-key"

            result = embed_chunks(make_input(3))

        for ec in result.embedded_chunks:
            assert isinstance(ec, EmbeddedChunk)
            assert len(ec.embedding) == EMBEDDING_DIMENSIONS

    def test_chunk_metadata_preserved_in_output(self):
        """The ChunkMetadata on each EmbeddedChunk must match the input chunk."""
        chunks = [make_chunk(i, text=f"text {i}") for i in range(3)]
        inp = EmbedderInput(chunks=chunks, doi="10.0000/test")

        with patch("rag.retrieval.embedder.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.embeddings.create.return_value = make_api_response(3)
            os.environ["OPENROUTER_API_KEY"] = "test-key"

            result = embed_chunks(inp)

        for i, ec in enumerate(result.embedded_chunks):
            assert ec.chunk.chunk_id == chunks[i].chunk_id
            assert ec.chunk.chunk_text == chunks[i].chunk_text

    def test_empty_chunk_list_returns_empty_output(self):
        with patch("rag.retrieval.embedder.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            os.environ["OPENROUTER_API_KEY"] = "test-key"

            result = embed_chunks(EmbedderInput(chunks=[], doi="10.0000/test"))

        assert result.total_embedded == 0
        assert result.embedded_chunks == []
        # API must not be called for an empty list
        mock_client.embeddings.create.assert_not_called()

    def test_batching_splits_large_input(self):
        """With 150 chunks and BATCH_SIZE=100, the API must be called twice."""
        n = BATCH_SIZE + 50  # 150

        with patch("rag.retrieval.embedder.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            # First batch: 100 chunks; second batch: 50 chunks
            mock_client.embeddings.create.side_effect = [
                make_api_response(BATCH_SIZE),
                make_api_response(50),
            ]
            os.environ["OPENROUTER_API_KEY"] = "test-key"

            result = embed_chunks(make_input(n))

        assert mock_client.embeddings.create.call_count == 2
        assert result.total_embedded == n

    def test_raises_environment_error_without_api_key(self):
        """embed_chunks must raise EnvironmentError if OPENROUTER_API_KEY is absent."""
        # Remove the key from the environment for this test.
        env_backup = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            with pytest.raises(EnvironmentError, match="OPENROUTER_API_KEY"):
                embed_chunks(make_input(1))
        finally:
            # Restore so other tests are not affected.
            if env_backup is not None:
                os.environ["OPENROUTER_API_KEY"] = env_backup

    def test_order_of_embedded_chunks_matches_input_order(self):
        """Embeddings must come back in the same order as the input chunks."""
        chunks = [make_chunk(i, text=f"unique text {i}") for i in range(4)]
        inp = EmbedderInput(chunks=chunks, doi="10.0000/test")

        # Give each position a distinct vector so we can verify order.
        items = []
        for i in range(4):
            item = MagicMock()
            item.embedding = [float(i)] * EMBEDDING_DIMENSIONS
            item.index = i
            items.append(item)
        mock_response = MagicMock()
        mock_response.data = items

        with patch("rag.retrieval.embedder.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.embeddings.create.return_value = mock_response
            os.environ["OPENROUTER_API_KEY"] = "test-key"

            result = embed_chunks(inp)

        for i, ec in enumerate(result.embedded_chunks):
            assert ec.embedding[0] == float(i), (
                f"Chunk at position {i} has wrong vector — order was not preserved"
            )
