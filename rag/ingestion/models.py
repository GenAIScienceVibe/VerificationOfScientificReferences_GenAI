"""
Pydantic models for the RAG ingestion pipeline.

These models define the data shapes that flow into and out of the
text cleaning and chunking steps. Using Pydantic ensures the backend
contract is enforced at runtime with clear error messages.
"""

from enum import Enum
from pydantic import BaseModel, Field


class EvidenceAvailability(str, Enum):
    """How much source text the backend was able to retrieve."""

    FULL_TEXT_AVAILABLE = "FULL_TEXT_AVAILABLE"
    ABSTRACT_AVAILABLE = "ABSTRACT_AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class SourceEvidence(BaseModel):
    """Source evidence payload sent by the backend (part of Door 1 input)."""

    evidence_availability: EvidenceAvailability
    text: str = Field(..., description="Raw plain text extracted from the source paper")
    source_url: str = Field(..., description="URL or DOI link for the source")


class CleanerInput(BaseModel):
    """Input to the text cleaning step."""

    raw_text: str = Field(..., description="Raw plain text as received from the backend")
    evidence_availability: EvidenceAvailability = Field(
        ..., description="Indicates whether text is full paper or abstract only"
    )
    doi: str = Field(..., description="DOI of the source paper, used for logging")


class CleanerOutput(BaseModel):
    """Output from the text cleaning step, passed directly to the chunker."""

    clean_text: str = Field(..., description="Cleaned plain text ready for chunking")
    doi: str = Field(..., description="DOI passed through for downstream metadata")
    evidence_availability: EvidenceAvailability = Field(
        ..., description="Passed through so the chunker can tag evidence_type"
    )
    original_length: int = Field(..., description="Character count of the raw input")
    cleaned_length: int = Field(..., description="Character count after cleaning")


# ── Chunker models ────────────────────────────────────────────────────────────


class ChunkMetadata(BaseModel):
    """A single text chunk with all metadata required by downstream steps."""

    chunk_id: str = Field(..., description="Unique ID: {doi_slug}_chunk_{index:03d}")
    section: str = Field(..., description="Normalised section name, e.g. 'results'")
    priority: float = Field(..., description="Section weight used during retrieval scoring")
    chunk_index: int = Field(..., description="Zero-based position of this chunk in the paper")
    paper_doi: str = Field(..., description="DOI of the source paper")
    evidence_type: str = Field(..., description="'FULL_TEXT' or 'ABSTRACT'")
    chunk_text: str = Field(..., description="The actual text content of this chunk")
    token_count: int = Field(..., description="Number of tokens in chunk_text (cl100k_base)")


class ChunkerInput(BaseModel):
    """Input to the chunking step — mirrors the relevant fields of CleanerOutput."""

    clean_text: str = Field(..., description="Cleaned plain text from the cleaner")
    doi: str = Field(..., description="DOI of the source paper")
    evidence_availability: EvidenceAvailability = Field(
        ..., description="Determines the evidence_type label on each chunk"
    )


class ChunkerOutput(BaseModel):
    """Output from the chunking step, ready for embedding."""

    doi: str = Field(..., description="DOI of the source paper")
    chunks: list[ChunkMetadata] = Field(..., description="Ordered list of all chunks")
    total_chunks: int = Field(..., description="Total number of chunks produced")
    sections_found: list[str] = Field(..., description="Unique section names detected")
    fallback_used: bool = Field(
        ..., description="True when no headings were detected and blind chunking was applied"
    )
