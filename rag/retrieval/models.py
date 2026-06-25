"""
Pydantic models for the RAG retrieval pipeline.

These models define the data shapes flowing between the embedder,
vector store, BM25 retriever, and hybrid retriever steps.
"""

from pydantic import BaseModel, Field

from rag.ingestion.models import ChunkMetadata


# ── Embedder models ───────────────────────────────────────────────────────────


class EmbeddedChunk(BaseModel):
    """A chunk paired with its embedding vector, ready for FAISS indexing."""

    chunk: ChunkMetadata = Field(..., description="Original chunk with all metadata")
    embedding: list[float] = Field(
        ..., description="Dense vector from text-embedding-3-small (1536 dims)"
    )


class EmbedderInput(BaseModel):
    """Input to the embedding step."""

    chunks: list[ChunkMetadata] = Field(
        ..., description="Chunks produced by the chunker"
    )
    doi: str = Field(..., description="DOI of the source paper, used for logging")


class EmbedderOutput(BaseModel):
    """Output from the embedding step, passed directly to the vector store."""

    doi: str = Field(..., description="DOI of the source paper")
    embedded_chunks: list[EmbeddedChunk] = Field(
        ..., description="Each chunk paired with its embedding vector"
    )
    total_embedded: int = Field(..., description="Number of chunks successfully embedded")
    embedding_model: str = Field(
        ..., description="Model used to generate the embeddings"
    )
    embedding_dimensions: int = Field(
        ..., description="Dimensionality of each embedding vector"
    )


# ── Vector store models ───────────────────────────────────────────────────────


class VectorStoreInput(BaseModel):
    """Input to the vector store search step.

    Accepts EmbedderOutput directly so the two modules connect without
    any intermediate conversion: embed_chunks() → search().
    """

    embedder_output: EmbedderOutput = Field(
        ...,
        description="Direct output from embed_chunks(); carries embedded chunks and DOI",
    )
    query_embedding: list[float] = Field(
        ..., description="Embedding vector of the claim text to search against"
    )
    top_k: int = Field(
        default=5, ge=1, description="Number of top chunks to return"
    )


class RetrievedChunk(BaseModel):
    """A single chunk returned from the vector store, with both raw and weighted scores."""

    chunk: ChunkMetadata = Field(..., description="Original chunk with all metadata")
    raw_score: float = Field(
        ..., description="Cosine similarity between chunk and query (0–1)"
    )
    weighted_score: float = Field(
        ..., description="raw_score × section priority weight; used for final ranking"
    )
    rank: int = Field(..., description="1-based position in the final ranked results")


class VectorStoreOutput(BaseModel):
    """Output from the vector store search step."""

    doi: str = Field(..., description="DOI of the source paper")
    top_chunks: list[RetrievedChunk] = Field(
        ..., description="Top-k chunks ordered by weighted_score descending"
    )
    total_indexed: int = Field(
        ..., description="Total number of chunks that were loaded into the FAISS index"
    )
    retrieved_k: int = Field(
        ..., description="Number of chunks actually returned (may be < top_k if index is small)"
    )
    low_confidence: bool = Field(
        default=False,
        description="True when the best chunk's weighted_score is below SIMILARITY_THRESHOLD",
    )
    warning: str | None = Field(
        default=None,
        description="Human-readable warning explaining why low_confidence is True",
    )


# ── BM25 retriever models ─────────────────────────────────────────────────────


class Bm25RetrieverInput(BaseModel):
    """Input to the BM25 keyword search step."""

    chunks: list[ChunkMetadata] = Field(
        ..., description="Chunks to index, same format as vector_store.py"
    )
    query: str = Field(..., description="Claim text used as the BM25 query")
    top_k: int = Field(default=5, ge=1, description="Number of top chunks to return")


class Bm25RetrievedChunk(BaseModel):
    """A single chunk returned from the BM25 retriever, with raw and weighted scores."""

    chunk: ChunkMetadata = Field(..., description="Original chunk with all metadata")
    raw_score: float = Field(..., description="Raw BM25 score (Okapi BM25, unbounded)")
    weighted_score: float = Field(
        ..., description="raw_score × section priority weight; used for final ranking"
    )
    rank: int = Field(..., description="1-based position in the final ranked results")


class Bm25RetrieverOutput(BaseModel):
    """Output from the BM25 keyword search step."""

    top_chunks: list[Bm25RetrievedChunk] = Field(
        ..., description="Top-k chunks ordered by weighted_score descending"
    )
    total_indexed: int = Field(
        ..., description="Total number of chunks that were loaded into the BM25 index"
    )
    retrieved_k: int = Field(
        ..., description="Number of chunks actually returned (may be < top_k if index is small)"
    )


# ── Hybrid retriever models ───────────────────────────────────────────────────


class HybridRetrieverInput(BaseModel):
    """Input to the hybrid retrieval merge step."""

    dense_results: VectorStoreOutput = Field(
        ..., description="Output from vector_store.search() (dense FAISS results)"
    )
    bm25_results: Bm25RetrieverOutput = Field(
        ..., description="Output from bm25_retriever.search() (keyword results)"
    )
    claim: str = Field(
        ..., description="The original claim text, used as the FlashRank rerank query"
    )
    top_k: int = Field(default=5, ge=1, description="Number of top chunks to return")


class HybridRetrievedChunk(BaseModel):
    """A single chunk in the merged hybrid ranking, with per-source rank info."""

    chunk: ChunkMetadata = Field(..., description="Original chunk with all metadata")
    rrf_score: float = Field(
        ..., description="Combined Reciprocal Rank Fusion score across both sources"
    )
    dense_rank: int | None = Field(
        default=None, description="1-based rank in the dense results, or None if absent"
    )
    bm25_rank: int | None = Field(
        default=None, description="1-based rank in the BM25 results, or None if absent"
    )
    rerank_score: float | None = Field(
        default=None,
        description="FlashRank neural relevance score; None if reranking was skipped or failed",
    )
    rank: int = Field(..., description="1-based position in the final merged ranking")


class HybridRetrieverOutput(BaseModel):
    """Output from the hybrid retrieval merge step, ready for reranking."""

    top_chunks: list[HybridRetrievedChunk] = Field(
        ..., description="Top-k chunks ordered by rrf_score descending"
    )
    total_unique: int = Field(
        ..., description="Total number of unique chunks across both input sources"
    )
