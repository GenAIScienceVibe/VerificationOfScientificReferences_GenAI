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
