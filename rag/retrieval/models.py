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
