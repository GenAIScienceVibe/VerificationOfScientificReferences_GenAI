from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ────────────────────────────────────────────────────────────────────

class UploadType(str, Enum):
    PDF = "PDF"
    TEXT = "TEXT"


class DocumentProcessingStatus(str, Enum):
    UPLOADED = "UPLOADED"
    TEXT_EXTRACTING = "TEXT_EXTRACTING"
    TEXT_EXTRACTED = "TEXT_EXTRACTED"
    REFERENCES_EXTRACTING = "REFERENCES_EXTRACTING"
    REFERENCES_EXTRACTED = "REFERENCES_EXTRACTED"
    DOI_VERIFYING = "DOI_VERIFYING"
    DOI_VERIFIED = "DOI_VERIFIED"
    CLAIMS_EXTRACTING = "CLAIMS_EXTRACTING"
    CLAIMS_EXTRACTED = "CLAIMS_EXTRACTED"
    EVIDENCE_PREPARING = "EVIDENCE_PREPARING"
    EVIDENCE_READY = "EVIDENCE_READY"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    REPORT_GENERATED = "REPORT_GENERATED"
    FAILED = "FAILED"
    PARTIAL_FAILED = "PARTIAL_FAILED"


class SectionType(str, Enum):
    title = "title"
    abstract = "abstract"
    introduction = "introduction"
    body = "body"
    references = "references"
    unknown = "unknown"


class DoiStatus(str, Enum):
    FOUND = "FOUND"
    MISSING = "MISSING"
    MALFORMED = "MALFORMED"
    VALID = "VALID"
    INVALID = "INVALID"
    LOOKUP_FAILED = "LOOKUP_FAILED"


class MetadataStatus(str, Enum):
    NOT_LOOKED_UP = "NOT_LOOKED_UP"
    LOOKUP_SUCCEEDED = "LOOKUP_SUCCEEDED"
    LOOKUP_FAILED = "LOOKUP_FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceLevel(str, Enum):
    METADATA_ONLY = "METADATA_ONLY"
    ABSTRACT_AVAILABLE = "ABSTRACT_AVAILABLE"
    FULL_TEXT_AVAILABLE = "FULL_TEXT_AVAILABLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class CacheStatus(str, Enum):
    NEW_VERIFICATION = "NEW_VERIFICATION"
    EXACT_CACHE = "EXACT_CACHE"
    SEMANTIC_CACHE = "SEMANTIC_CACHE"
    NO_HIT = "NO_HIT"
    HUMAN_CORRECTED = "HUMAN_CORRECTED"


class CacheSource(str, Enum):
    NEW_VERIFICATION = "NEW_VERIFICATION"
    EXACT_CACHE = "EXACT_CACHE"
    SEMANTIC_CACHE = "SEMANTIC_CACHE"
    HUMAN_CORRECTED = "HUMAN_CORRECTED"


class SupportStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class RetrievalStatus(str, Enum):
    QUEUED = "QUEUED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class VerificationMethod(str, Enum):
    RAG_GENAI = "RAG_GENAI"
    DIRECT_LOOKUP = "DIRECT_LOOKUP"
    CACHE_REUSE = "CACHE_REUSE"


class FeedbackType(str, Enum):
    VERIFICATION_RESULT = "VERIFICATION_RESULT"
    MAPPING = "MAPPING"
    SURVEY = "SURVEY"


class PipelineRunStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PipelineRunMode(str, Enum):
    full = "full"
    references_only = "references_only"
    claims_only = "claims_only"


class PipelineStepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ReportFormat(str, Enum):
    JSON = "JSON"
    HTML = "HTML"
    PDF = "PDF"


# ── Models ───────────────────────────────────────────────────────────────────

class Document(Base):
    __tablename__ = "documents"

    document_id = Column(String(64), primary_key=True)
    title = Column(String(256), nullable=True)
    filename = Column(String(256), nullable=True)
    upload_type = Column(SQLEnum(UploadType), nullable=False)
    status = Column(SQLEnum(DocumentProcessingStatus), nullable=False, default=DocumentProcessingStatus.UPLOADED)
    file_size_bytes = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=True)
    references_count = Column(Integer, nullable=True)
    claims_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    sections = relationship("DocumentSection", back_populates="document", cascade="all, delete-orphan")
    references = relationship("Reference", back_populates="document", cascade="all, delete-orphan")
    claims = relationship("Claim", back_populates="document", cascade="all, delete-orphan")
    pipeline_runs = relationship("PipelineRun", back_populates="document", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="document", cascade="all, delete-orphan")
    uat_surveys = relationship("UatSurvey", back_populates="document", cascade="all, delete-orphan")


class DocumentSection(Base):
    __tablename__ = "document_sections"
    __table_args__ = (UniqueConstraint("document_id", "section_id", name="uq_document_section"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(64), ForeignKey("documents.document_id"), nullable=False, index=True)
    section_id = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    type = Column(SQLEnum(SectionType), nullable=False, default=SectionType.unknown)
    order_index = Column(Integer, nullable=False, default=0)
    text_preview = Column(Text, nullable=True)
    full_text = Column(Text, nullable=True)
    start_char = Column(Integer, nullable=True)
    end_char = Column(Integer, nullable=True)

    document = relationship("Document", back_populates="sections")


class Reference(Base):
    __tablename__ = "references"

    reference_id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey("documents.document_id"), nullable=False, index=True)
    raw_reference = Column(Text, nullable=False)
    extracted_title = Column(String(512), nullable=True)
    extracted_authors = Column(JSON, nullable=True)
    extracted_year = Column(Integer, nullable=True)
    extracted_doi = Column(String(128), nullable=True)
    doi_normalized = Column(String(128), nullable=True)
    doi_status = Column(SQLEnum(DoiStatus), nullable=False, default=DoiStatus.MISSING)
    metadata_status = Column(SQLEnum(MetadataStatus), nullable=False, default=MetadataStatus.NOT_LOOKED_UP)
    metadata_match_score = Column(Float, nullable=True)
    position = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    document = relationship("Document", back_populates="references")
    source_metadata = relationship("SourceMetadata", back_populates="reference", uselist=False, cascade="all, delete-orphan")
    citations = relationship("Citation", back_populates="reference")
    claim_reference_links = relationship("ClaimReferenceLink", back_populates="reference")


class SourceMetadata(Base):
    __tablename__ = "source_metadata"

    metadata_id = Column(Integer, primary_key=True, autoincrement=True)
    reference_id = Column(String(64), ForeignKey("references.reference_id"), nullable=False, unique=True)
    metadata_status = Column(SQLEnum(MetadataStatus), nullable=False, default=MetadataStatus.NOT_LOOKED_UP)
    doi = Column(String(128), nullable=True)
    title = Column(String(512), nullable=True)
    authors = Column(JSON, nullable=True)
    year = Column(Integer, nullable=True)
    journal = Column(String(256), nullable=True)
    publisher = Column(String(256), nullable=True)
    url = Column(String(1024), nullable=True)
    abstract = Column(Text, nullable=True)
    fetched_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    reference = relationship("Reference", back_populates="source_metadata")


class Claim(Base):
    __tablename__ = "claims"

    claim_id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey("documents.document_id"), nullable=False, index=True)
    claim_text = Column(Text, nullable=False)
    claim_type = Column(String(64), nullable=True)
    section_name = Column(String(128), nullable=True)
    source_paragraph = Column(Text, nullable=True)
    citation_text = Column(String(512), nullable=True)
    page_number = Column(Integer, nullable=True)
    paragraph_index = Column(Integer, nullable=True)
    sentence_index = Column(Integer, nullable=True)
    extraction_confidence = Column(Float, nullable=True)
    mapping_status = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    document = relationship("Document", back_populates="claims")
    citations = relationship("Citation", back_populates="claim", cascade="all, delete-orphan")
    claim_reference_links = relationship("ClaimReferenceLink", back_populates="claim", cascade="all, delete-orphan")
    evidence_package = relationship("EvidencePackage", back_populates="claim", uselist=False, cascade="all, delete-orphan")
    retrieval_result = relationship("RetrievalResult", back_populates="claim", uselist=False, cascade="all, delete-orphan")
    verification_results = relationship("VerificationResult", back_populates="claim", cascade="all, delete-orphan")
    cache_entries = relationship("CacheIndex", back_populates="claim", cascade="all, delete-orphan")


class Citation(Base):
    __tablename__ = "citations"

    citation_id = Column(String(64), primary_key=True)
    claim_id = Column(String(64), ForeignKey("claims.claim_id"), nullable=False, index=True)
    citation_text = Column(String(512), nullable=False)
    citation_style = Column(String(128), nullable=True)
    raw_marker = Column(String(64), nullable=True)
    mapped_reference_id = Column(String(64), ForeignKey("references.reference_id"), nullable=True)
    mapping_confidence = Column(Float, nullable=True)
    mapping_uncertain = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    claim = relationship("Claim", back_populates="citations")
    reference = relationship("Reference", back_populates="citations")
    claim_reference_links = relationship("ClaimReferenceLink", back_populates="citation")


class ClaimReferenceLink(Base):
    __tablename__ = "claim_reference_links"

    link_id = Column(String(64), primary_key=True)
    claim_id = Column(String(64), ForeignKey("claims.claim_id"), nullable=False, index=True)
    citation_id = Column(String(64), ForeignKey("citations.citation_id"), nullable=True, index=True)
    reference_id = Column(String(64), ForeignKey("references.reference_id"), nullable=True, index=True)
    mapping_status = Column(String(64), nullable=True)
    mapping_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    claim = relationship("Claim", back_populates="claim_reference_links")
    citation = relationship("Citation", back_populates="claim_reference_links")
    reference = relationship("Reference", back_populates="claim_reference_links")
    feedback = relationship("UserFeedback", back_populates="claim_reference_link", uselist=False)
    verification_results = relationship("VerificationResult", back_populates="claim_reference_link")


class EvidencePackage(Base):
    __tablename__ = "evidence_packages"

    package_id = Column(String(64), primary_key=True)
    claim_id = Column(String(64), ForeignKey("claims.claim_id"), nullable=False, index=True)
    reference_id = Column(String(64), ForeignKey("references.reference_id"), nullable=False, index=True)
    evidence_level = Column(SQLEnum(EvidenceLevel), nullable=False)
    source_evidence_text = Column(Text, nullable=True)
    source_evidence_url = Column(String(1024), nullable=True)
    embedding_model_version = Column(String(128), nullable=True)
    prompt_version = Column(String(128), nullable=True)
    verification_policy_version = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    claim = relationship("Claim", back_populates="evidence_package")
    reference = relationship("Reference")


class RetrievalResult(Base):
    __tablename__ = "retrieval_results"

    retrieval_result_id = Column(String(64), primary_key=True)
    claim_id = Column(String(64), ForeignKey("claims.claim_id"), nullable=False, index=True)
    retrieval_status = Column(SQLEnum(RetrievalStatus), nullable=False, default=RetrievalStatus.QUEUED)
    overall_similarity_score = Column(Float, nullable=True)
    retrieval_confidence = Column(Float, nullable=True)
    top_k = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    claim = relationship("Claim", back_populates="retrieval_result")
    chunks = relationship("RetrievalChunk", back_populates="retrieval_result", cascade="all, delete-orphan")


class RetrievalChunk(Base):
    __tablename__ = "retrieval_chunks"

    chunk_id = Column(String(64), primary_key=True)
    retrieval_result_id = Column(String(64), ForeignKey("retrieval_results.retrieval_result_id"), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)
    similarity_score = Column(Float, nullable=False)
    evidence_type = Column(String(128), nullable=True)
    source = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    retrieval_result = relationship("RetrievalResult", back_populates="chunks")


class VerificationResult(Base):
    __tablename__ = "verification_results"

    result_id = Column(String(64), primary_key=True)
    claim_id = Column(String(64), ForeignKey("claims.claim_id"), nullable=False, index=True)
    citation_id = Column(String(64), ForeignKey("citations.citation_id"), nullable=True, index=True)
    reference_id = Column(String(64), ForeignKey("references.reference_id"), nullable=True, index=True)
    claim_reference_link_id = Column(String(64), ForeignKey("claim_reference_links.link_id"), nullable=True, index=True)
    support_status = Column(SQLEnum(SupportStatus), nullable=False)
    confidence = Column(Float, nullable=True)
    human_review_required = Column(Boolean, nullable=False, default=False)
    cache_source = Column(SQLEnum(CacheSource), nullable=True)
    evidence_availability = Column(SQLEnum(EvidenceLevel), nullable=True)
    evidence_used_count = Column(Integer, nullable=True)
    overall_similarity_score = Column(Float, nullable=True)
    verification_method = Column(SQLEnum(VerificationMethod), nullable=True)
    explanation = Column(Text, nullable=True)
    safety_risk_level = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    claim = relationship("Claim", back_populates="verification_results")
    citation = relationship("Citation")
    reference = relationship("Reference")
    claim_reference_link = relationship("ClaimReferenceLink", back_populates="verification_results")
    safety_checks = relationship("SafetyCheck", back_populates="verification_result", cascade="all, delete-orphan")
    feedback = relationship("UserFeedback", back_populates="verification_result", uselist=False)


class SafetyCheck(Base):
    __tablename__ = "safety_checks"

    check_id = Column(String(64), primary_key=True)
    verification_result_id = Column(String(64), ForeignKey("verification_results.result_id"), nullable=False, index=True)
    rule_id = Column(String(128), nullable=False)
    triggered = Column(Boolean, nullable=False, default=False)
    details = Column(JSON, nullable=True)
    overridden_to = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    verification_result = relationship("VerificationResult", back_populates="safety_checks")


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    feedback_id = Column(String(64), primary_key=True)
    verification_result_id = Column(String(64), ForeignKey("verification_results.result_id"), nullable=True, index=True)
    claim_reference_link_id = Column(String(64), ForeignKey("claim_reference_links.link_id"), nullable=True, index=True)
    feedback_type = Column(SQLEnum(FeedbackType), nullable=False)
    user_label = Column(String(128), nullable=False)
    user_comment = Column(Text, nullable=True)
    user_role = Column(String(128), nullable=True)
    suggested_reference_id = Column(String(64), ForeignKey("references.reference_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    verification_result = relationship("VerificationResult", back_populates="feedback")
    claim_reference_link = relationship("ClaimReferenceLink", back_populates="feedback")


class CacheIndex(Base):
    __tablename__ = "cache_index"

    cache_id = Column(String(64), primary_key=True)
    claim_id = Column(String(64), ForeignKey("claims.claim_id"), nullable=False, index=True)
    cache_status = Column(SQLEnum(CacheStatus), nullable=False)
    cache_source = Column(SQLEnum(CacheSource), nullable=False)
    matched_result_id = Column(String(64), ForeignKey("verification_results.result_id"), nullable=True)
    semantic_similarity = Column(Float, nullable=True)
    reuse_allowed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    claim = relationship("Claim", back_populates="cache_entries")
    matched_result = relationship("VerificationResult")


# ── New models ───────────────────────────────────────────────────────────────

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    pipeline_run_id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey("documents.document_id"), nullable=False, index=True)
    status = Column(SQLEnum(PipelineRunStatus), nullable=False, default=PipelineRunStatus.QUEUED)
    mode = Column(SQLEnum(PipelineRunMode), nullable=False, default=PipelineRunMode.full)
    progress_percentage = Column(Integer, nullable=True, default=0)
    current_step = Column(String(128), nullable=True)
    error_detail = Column(Text, nullable=True)
    use_cache = Column(Boolean, nullable=False, default=True)
    use_rag = Column(Boolean, nullable=False, default=True)
    use_genai_safety_review = Column(Boolean, nullable=False, default=True)
    generate_report = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="pipeline_runs")
    steps = relationship("PipelineRunStep", back_populates="pipeline_run", cascade="all, delete-orphan")


class PipelineRunStep(Base):
    __tablename__ = "pipeline_run_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id = Column(String(64), ForeignKey("pipeline_runs.pipeline_run_id"), nullable=False, index=True)
    step = Column(String(128), nullable=False)
    status = Column(SQLEnum(PipelineStepStatus), nullable=False, default=PipelineStepStatus.PENDING)
    error_detail = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    pipeline_run = relationship("PipelineRun", back_populates="steps")


class Report(Base):
    __tablename__ = "reports"

    report_id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey("documents.document_id"), nullable=False, index=True)
    title = Column(String(256), nullable=True)
    format = Column(SQLEnum(ReportFormat), nullable=False, default=ReportFormat.JSON)
    total_claims = Column(Integer, nullable=True)
    total_references = Column(Integer, nullable=True)
    supported = Column(Integer, nullable=True)
    partially_supported = Column(Integer, nullable=True)
    not_supported = Column(Integer, nullable=True)
    insufficient_evidence = Column(Integer, nullable=True)
    needs_human_review = Column(Integer, nullable=True)
    valid_dois = Column(Integer, nullable=True)
    missing_dois = Column(Integer, nullable=True)
    invalid_dois = Column(Integer, nullable=True)
    overall_risk_level = Column(String(32), nullable=True)
    high_risk_claim_ids = Column(JSON, nullable=True)
    safety_rules_triggered = Column(JSON, nullable=True)
    human_review_recommendations = Column(JSON, nullable=True)
    limitations = Column(Text, nullable=True)
    html_content = Column(Text, nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    document = relationship("Document", back_populates="reports")


class UatSurvey(Base):
    __tablename__ = "uat_surveys"

    survey_id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey("documents.document_id"), nullable=False, index=True)
    user_id = Column(String(128), nullable=True)
    responses = Column(JSON, nullable=False)
    overall_rating = Column(Integer, nullable=True)
    free_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    document = relationship("Document", back_populates="uat_surveys")
