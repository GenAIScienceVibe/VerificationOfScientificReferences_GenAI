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
