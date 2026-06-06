from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    CacheSource,
    ClaimType,
    DocumentStatus,
    DoiStatus,
    EvidenceAvailability,
    MappingStatus,
    MetadataStatus,
    PipelineStatus,
    PipelineStepStatus,
    SafetyRiskLevel,
    SupportStatus,
    UploadType,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def prefixed_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Document(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("doc"))
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    upload_type: Mapped[str] = mapped_column(String(32), nullable=False, default=UploadType.TEXT.value)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default=DocumentStatus.UPLOADED.value, index=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleaned_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    pages_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    references_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claims_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_pipeline_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    sections: Mapped[list[DocumentSection]] = relationship(back_populates="document", cascade="all, delete-orphan")
    references: Mapped[list[Reference]] = relationship(back_populates="document", cascade="all, delete-orphan")
    claims: Mapped[list[Claim]] = relationship(back_populates="document", cascade="all, delete-orphan")
    citations: Mapped[list[Citation]] = relationship(back_populates="document", cascade="all, delete-orphan")
    claim_reference_links: Mapped[list[ClaimReferenceLink]] = relationship(back_populates="document", cascade="all, delete-orphan")
    evidence_packages: Mapped[list[EvidencePackage]] = relationship(back_populates="document", cascade="all, delete-orphan")
    retrieval_results: Mapped[list[RagRetrievalResult]] = relationship(back_populates="document", cascade="all, delete-orphan")
    verification_results: Mapped[list[VerificationResult]] = relationship(back_populates="document", cascade="all, delete-orphan")
    reports: Mapped[list[Report]] = relationship(back_populates="document", cascade="all, delete-orphan")
    feedback_entries: Mapped[list[UserFeedback]] = relationship(back_populates="document", cascade="all, delete-orphan")
    uat_surveys: Mapped[list[UatSurvey]] = relationship(back_populates="document", cascade="all, delete-orphan")
    pipeline_runs: Mapped[list[PipelineRun]] = relationship(
        back_populates="document", cascade="all, delete-orphan", foreign_keys="PipelineRun.document_id"
    )
    prompt_runs: Mapped[list[PromptRun]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentSection(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "document_sections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("sec"))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_preview: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    document: Mapped[Document] = relationship(back_populates="sections")


class Reference(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "references"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("ref"))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), nullable=False, index=True)
    reference_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_reference: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    extracted_authors: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_doi: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    doi_status: Mapped[str] = mapped_column(String(64), nullable=False, default=DoiStatus.MISSING.value, index=True)
    metadata_status: Mapped[str] = mapped_column(String(64), nullable=False, default=MetadataStatus.NOT_LOOKED_UP.value)
    metadata_match_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    document: Mapped[Document] = relationship(back_populates="references")
    metadata_records: Mapped[list[SourceMetadata]] = relationship(back_populates="reference", cascade="all, delete-orphan")
    citations: Mapped[list[Citation]] = relationship(back_populates="mapped_reference")
    claim_links: Mapped[list[ClaimReferenceLink]] = relationship(back_populates="reference")
    evidence_packages: Mapped[list[EvidencePackage]] = relationship(back_populates="reference")
    retrieval_results: Mapped[list[RagRetrievalResult]] = relationship(back_populates="reference")
    verification_results: Mapped[list[VerificationResult]] = relationship(back_populates="reference")
    cache_entries: Mapped[list[ClaimCacheIndex]] = relationship(back_populates="reference")


class SourceMetadata(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "source_metadata"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("meta"))
    reference_id: Mapped[str] = mapped_column(String(64), ForeignKey("references.id"), nullable=False)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    authors: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(512), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(512), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    lookup_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lookup_status: Mapped[str] = mapped_column(String(64), nullable=False, default=MetadataStatus.NOT_LOOKED_UP.value)
    raw_metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    title_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    author_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    year_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    metadata_match_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    reference: Mapped[Reference] = relationship(back_populates="metadata_records")


class Claim(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("claim"))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), nullable=False, index=True)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(64), nullable=False, default=ClaimType.UNKNOWN.value)
    section_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_paragraph: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sentence_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    document: Mapped[Document] = relationship(back_populates="claims")
    citations: Mapped[list[Citation]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    reference_links: Mapped[list[ClaimReferenceLink]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    evidence_packages: Mapped[list[EvidencePackage]] = relationship(back_populates="claim")
    retrieval_results: Mapped[list[RagRetrievalResult]] = relationship(back_populates="claim")
    verification_results: Mapped[list[VerificationResult]] = relationship(back_populates="claim")
    prompt_runs: Mapped[list[PromptRun]] = relationship(back_populates="claim")


class Citation(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("cit"))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), nullable=False, index=True)
    claim_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("claims.id"), nullable=True)
    raw_citation: Mapped[str] = mapped_column(String(1000), nullable=False)
    citation_style: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sentence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mapped_reference_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("references.id"), nullable=True)
    mapping_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    document: Mapped[Document] = relationship(back_populates="citations")
    claim: Mapped[Claim | None] = relationship(back_populates="citations")
    mapped_reference: Mapped[Reference | None] = relationship(back_populates="citations")
    claim_links: Mapped[list[ClaimReferenceLink]] = relationship(back_populates="citation")


class ClaimReferenceLink(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "claim_reference_links"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("link"))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), nullable=False)
    claim_id: Mapped[str] = mapped_column(String(64), ForeignKey("claims.id"), nullable=False, index=True)
    citation_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("citations.id"), nullable=True)
    reference_id: Mapped[str] = mapped_column(String(64), ForeignKey("references.id"), nullable=False, index=True)
    mapping_status: Mapped[str] = mapped_column(String(64), nullable=False, default=MappingStatus.UNCERTAIN.value)
    mapping_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    mapping_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped[Document] = relationship(back_populates="claim_reference_links")
    claim: Mapped[Claim] = relationship(back_populates="reference_links")
    citation: Mapped[Citation | None] = relationship(back_populates="claim_links")
    reference: Mapped[Reference] = relationship(back_populates="claim_links")


class EvidencePackage(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "evidence_packages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("evidence"))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), nullable=False)
    claim_id: Mapped[str] = mapped_column(String(64), ForeignKey("claims.id"), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(64), ForeignKey("references.id"), nullable=False)
    citation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doi_status: Mapped[str] = mapped_column(String(64), nullable=False, default=DoiStatus.MISSING.value)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    evidence_availability: Mapped[str] = mapped_column(String(64), nullable=False, default=EvidenceAvailability.SOURCE_UNAVAILABLE.value)
    embedding_model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_policy_version: Mapped[str | None] = mapped_column(String(128), nullable=True)

    document: Mapped[Document] = relationship(back_populates="evidence_packages")
    claim: Mapped[Claim] = relationship(back_populates="evidence_packages")
    reference: Mapped[Reference] = relationship(back_populates="evidence_packages")
    retrieval_results: Mapped[list[RagRetrievalResult]] = relationship(back_populates="evidence_package")


class RagRetrievalResult(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "rag_retrieval_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("retrieval"))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), nullable=False)
    claim_id: Mapped[str] = mapped_column(String(64), ForeignKey("claims.id"), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(64), ForeignKey("references.id"), nullable=False)
    evidence_package_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("evidence_packages.id"), nullable=True)
    retrieval_status: Mapped[str] = mapped_column(String(64), nullable=False, default="NOT_STARTED")
    top_chunks_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    overall_similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieval_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped[Document] = relationship(back_populates="retrieval_results")
    claim: Mapped[Claim] = relationship(back_populates="retrieval_results")
    reference: Mapped[Reference] = relationship(back_populates="retrieval_results")
    evidence_package: Mapped[EvidencePackage | None] = relationship(back_populates="retrieval_results")


class VerificationResult(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "verification_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("result"))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), nullable=False, index=True)
    claim_id: Mapped[str] = mapped_column(String(64), ForeignKey("claims.id"), nullable=False, index=True)
    reference_id: Mapped[str] = mapped_column(String(64), ForeignKey("references.id"), nullable=False)
    support_status: Mapped[str] = mapped_column(String(64), nullable=False, default=SupportStatus.NEEDS_HUMAN_REVIEW.value, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    evidence_used_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    evidence_availability: Mapped[str] = mapped_column(String(64), nullable=False, default=EvidenceAvailability.SOURCE_UNAVAILABLE.value)
    evidence_used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    verification_method: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cache_source: Mapped[str] = mapped_column(String(64), nullable=False, default=CacheSource.NEW_VERIFICATION.value)
    source_result_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("verification_results.id"), nullable=True)

    document: Mapped[Document] = relationship(back_populates="verification_results")
    claim: Mapped[Claim] = relationship(back_populates="verification_results")
    reference: Mapped[Reference] = relationship(back_populates="verification_results")
    source_result: Mapped[VerificationResult | None] = relationship(remote_side="VerificationResult.id")
    safety_checks: Mapped[list[SafetyCheck]] = relationship(back_populates="verification_result", cascade="all, delete-orphan")
    feedback_entries: Mapped[list[UserFeedback]] = relationship(back_populates="verification_result")
    cache_entries: Mapped[list[ClaimCacheIndex]] = relationship(
        back_populates="verification_result", foreign_keys="ClaimCacheIndex.verification_result_id"
    )


class SafetyCheck(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "safety_checks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("safety"))
    verification_result_id: Mapped[str] = mapped_column(String(64), ForeignKey("verification_results.id"), nullable=False)
    safety_status: Mapped[str] = mapped_column(String(64), nullable=False, default="PENDING")
    risk_level: Mapped[str] = mapped_column(String(64), nullable=False, default=SafetyRiskLevel.UNKNOWN.value)
    issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    backend_rule_triggered: Mapped[str | None] = mapped_column(String(255), nullable=True)

    verification_result: Mapped[VerificationResult] = relationship(back_populates="safety_checks")


class Report(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("report"))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), nullable=False)
    format: Mapped[str] = mapped_column(String(64), nullable=False, default="HTML")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="NOT_STARTED")
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    html_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    report_storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    document: Mapped[Document] = relationship(back_populates="reports")


class UserFeedback(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "user_feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("feedback"))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), nullable=False)
    result_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("verification_results.id"), nullable=True)
    link_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("claim_reference_links.id"), nullable=True)
    feedback_type: Mapped[str] = mapped_column(String(128), nullable=False)
    user_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    suggested_reference_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("references.id"), nullable=True)
    user_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_role: Mapped[str | None] = mapped_column(String(128), nullable=True)

    document: Mapped[Document] = relationship(back_populates="feedback_entries")
    verification_result: Mapped[VerificationResult | None] = relationship(back_populates="feedback_entries")
    claim_reference_link: Mapped[ClaimReferenceLink | None] = relationship()
    suggested_reference: Mapped[Reference | None] = relationship()


class UatSurvey(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "uat_surveys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("survey"))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), nullable=False)
    participant_role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ease_of_use_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_clarity_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trust_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usefulness_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped[Document] = relationship(back_populates="uat_surveys")


class PipelineRun(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("run"))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(64), nullable=False, default="STANDARD")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default=PipelineStatus.QUEUED.value, index=True)
    progress_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_step: Mapped[str | None] = mapped_column(String(255), nullable=True)
    use_cache: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    use_rag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    use_genai_safety_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    generate_report: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warnings_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped[Document] = relationship(back_populates="pipeline_runs", foreign_keys=[document_id])
    steps: Mapped[list[PipelineStep]] = relationship(back_populates="pipeline_run", cascade="all, delete-orphan")
    prompt_runs: Mapped[list[PromptRun]] = relationship(back_populates="pipeline_run")


class PipelineStep(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "pipeline_steps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("step"))
    pipeline_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("pipeline_runs.id"), nullable=False)
    step_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default=PipelineStepStatus.PENDING.value)
    progress_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="steps")


class PromptRun(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "prompt_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("prompt"))
    document_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("documents.id"), nullable=True)
    claim_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("claims.id"), nullable=True)
    pipeline_run_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("pipeline_runs.id"), nullable=True)
    prompt_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    model_provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_usage_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    document: Mapped[Document | None] = relationship(back_populates="prompt_runs")
    claim: Mapped[Claim | None] = relationship(back_populates="prompt_runs")
    pipeline_run: Mapped[PipelineRun | None] = relationship(back_populates="prompt_runs")


class ClaimCacheIndex(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "claim_cache_index"
    __table_args__ = (
        UniqueConstraint(
            "normalized_claim_hash",
            "doi",
            "reference_id",
            "evidence_version",
            "embedding_model_version",
            "prompt_version",
            "verification_policy_version",
            name="uq_claim_cache_exact_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: prefixed_id("cache"))
    normalized_claim_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_embedding_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doi: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reference_id: Mapped[str] = mapped_column(String(64), ForeignKey("references.id"), nullable=False)
    verification_result_id: Mapped[str] = mapped_column(String(64), ForeignKey("verification_results.id"), nullable=False)
    support_status: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_version: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    verification_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    cache_source: Mapped[str] = mapped_column(String(64), nullable=False, default=CacheSource.NEW_VERIFICATION.value)

    reference: Mapped[Reference] = relationship(back_populates="cache_entries")
    verification_result: Mapped[VerificationResult] = relationship(
        back_populates="cache_entries", foreign_keys=[verification_result_id]
    )


# Explicit index names make the BE-2 database contract easy to inspect.
Index("ix_claim_reference_links_document_id", ClaimReferenceLink.document_id)
Index("ix_verification_results_document_claim", VerificationResult.document_id, VerificationResult.claim_id)
Index("ix_pipeline_steps_run_status", PipelineStep.pipeline_run_id, PipelineStep.status)
Index("ix_claim_cache_doi_hash", ClaimCacheIndex.doi, ClaimCacheIndex.normalized_claim_hash)
