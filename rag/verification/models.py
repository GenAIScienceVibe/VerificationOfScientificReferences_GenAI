"""
Pydantic models for the LLM verification step (Door 2).

These models define the exact input the verifier consumes and the exact
output schema the backend expects back. The verdict labels and field names
must match the backend contract exactly — see CLAUDE.md, VERDICT LABELS.
"""

from enum import Enum

from pydantic import BaseModel, Field

from rag.ingestion.models import ChunkMetadata


class Verdict(str, Enum):
    """The five verdict labels the backend schema accepts. Must match exactly."""

    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class VerificationInput(BaseModel):
    """Input to the LLM verification step."""

    claim_text: str = Field(..., description="Clean factual claim text, author names stripped")
    citation_type: str = Field(
        ..., description="RESULT_COMPARISON / METHOD / BACKGROUND / MOTIVATION / EXTENSION / FUTURE_WORK"
    )
    chunks: list[ChunkMetadata] = Field(
        ..., description="Top retrieved chunks with section labels, used as evidence"
    )
    doi: str = Field(..., description="DOI of the source paper being checked")


class VerificationOutput(BaseModel):
    """Output from the LLM verification step, validated before returning to the backend."""

    verdict: Verdict = Field(..., description="One of the five verdict labels")
    confidence: float = Field(..., ge=0.0, le=1.0, description="LLM's confidence in the verdict")
    explanation: str = Field(..., description="Reasoning behind the verdict, including chain-of-thought")
    evidence_used: list[str] = Field(
        default_factory=list, description="chunk_id values the LLM relied on for the verdict"
    )
    limitations: str | None = Field(
        default=None, description="Caveats, e.g. 'Only abstract-level evidence was available.'"
    )
    human_review_required: bool = Field(
        ..., description="True when confidence < 0.5 OR verdict == PARTIALLY_SUPPORTED"
    )
