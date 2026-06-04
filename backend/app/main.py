from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Path, Query, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, init_db
from app.db.models import (
    CacheIndex,
    CacheSource,
    CacheStatus,
    Claim,
    ClaimReferenceLink,
    Citation,
    Document,
    DocumentProcessingStatus,
    DocumentSection,
    EvidencePackage,
    FeedbackType,
    PipelineRun,
    PipelineRunMode,
    PipelineRunStatus,
    PipelineRunStep,
    PipelineStepStatus,
    Reference,
    Report,
    ReportFormat,
    RetrievalResult,
    SafetyCheck,
    SectionType,
    SourceMetadata,
    SupportStatus,
    UatSurvey,
    UploadType,
    UserFeedback,
    VerificationResult,
)
from app.logger import logger
from app.services.text_service import process_document_text, process_text_document
from app.services.reference_service import process_references
from app.services.doi_lookup_service import lookup_all_references, lookup_single_reference
from app.db.repositories import (
    CacheIndexRepository,
    CitationRepository,
    ClaimReferenceLinkRepository,
    ClaimRepository,
    DocumentRepository,
    DocumentSectionRepository,
    EvidencePackageRepository,
    PipelineRunRepository,
    ReferenceRepository,
    ReportRepository,
    RetrievalRepository,
    SafetyCheckRepository,
    SourceMetadataRepository,
    UatSurveyRepository,
    UserFeedbackRepository,
    VerificationResultRepository,
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Scientific Reference Verification API",
    version="1.0.0",
    description="Backend API for uploading scientific documents and running the "
                "complete reference, citation, claim, evidence, and verification workflow.",
)


@app.on_event("startup")
def on_startup():
    logger.info(f"refcheck-backend v{VERSION} starting up")


@app.on_event("shutdown")
def on_shutdown():
    logger.info("refcheck-backend shutting down")

VERSION = "1.0.0"
SERVICE = "refcheck-backend"
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
MAX_TEXT_LENGTH = 500_000
ALLOWED_CONTENT_TYPES = {"application/pdf"}
ALLOWED_EXTENSIONS = {".pdf"}

ALL_PIPELINE_STEPS = [
    "TEXT_EXTRACTION", "SECTION_DETECTION", "REFERENCE_EXTRACTION",
    "DOI_LOOKUP", "CLAIM_EXTRACTION", "CITATION_MAPPING",
    "EVIDENCE_PREPARATION", "CACHE_CHECK", "RAG_RETRIEVAL",
    "GENAI_VERIFICATION", "SAFETY_CHECK", "REPORT_GENERATION",
]


def NOW() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# DB session dependency
# ---------------------------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class TextDocumentRequest(BaseModel):
    title: str
    text: str

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("text must be at least 10 characters.")
        if len(v) > MAX_TEXT_LENGTH:
            raise ValueError("text must be at most 500 000 characters.")
        return v


class FeedbackRequest(BaseModel):
    user_label: str
    user_comment: Optional[str] = None
    user_role: Optional[str] = None

    @field_validator("user_label")
    @classmethod
    def valid_label(cls, v: str) -> str:
        allowed = {s.value for s in SupportStatus}
        if v not in allowed:
            raise ValueError(f"user_label must be one of: {', '.join(sorted(allowed))}")
        return v


class MappingFeedbackRequest(BaseModel):
    feedback_type: str
    suggested_reference_id: Optional[str] = None
    comment: Optional[str] = None

    @field_validator("feedback_type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        allowed = {"CORRECT", "INCORRECT", "UNCERTAIN"}
        if v not in allowed:
            raise ValueError(f"feedback_type must be one of: {', '.join(sorted(allowed))}")
        return v


class ResetRequest(BaseModel):
    reason: str
    force: bool = False


class PipelineRunRequest(BaseModel):
    mode: str = "full"
    use_cache: bool = True
    use_rag: bool = True
    use_genai_safety_review: bool = True
    generate_report: bool = True


class CacheCheckRequest(BaseModel):
    include_semantic: bool = True
    threshold: float = 0.92


class RetrieveEvidenceRequest(BaseModel):
    force: bool = False
    top_k: int = 5


class DebugStepRequest(BaseModel):
    force: bool = False
    options: Optional[dict] = None


class UatSurveyRequest(BaseModel):
    document_id: str
    user_id: Optional[str] = None
    responses: List[dict]
    overall_rating: Optional[int] = None
    free_text: Optional[str] = None


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def ok(data, message: str = "Success"):
    return {
        "success": True,
        "data": data,
        "message": message,
        "errors": [],
        "request_id": f"req_{uuid.uuid4().hex[:8]}",
    }


def err(code: str, detail: str, field: Optional[str] = None):
    return {
        "success": False,
        "data": None,
        "message": detail,
        "errors": [{"code": code, "field": field, "detail": detail}],
        "request_id": f"req_{uuid.uuid4().hex[:8]}",
    }


def raise_404(resource: str, resource_id: str):
    logger.warning(f"[404] {resource} '{resource_id}' not found")
    raise HTTPException(
        status_code=404,
        detail=err("NOT_FOUND", f"{resource} '{resource_id}' was not found."),
    )


def raise_409(code: str, message: str):
    logger.warning(f"[409] {code} — {message}")
    raise HTTPException(status_code=409, detail=err(code, message))


def raise_413(max_mb: float, received_mb: float):
    raise HTTPException(
        status_code=413,
        detail=err("PAYLOAD_TOO_LARGE",
                   f"Payload {received_mb:.2f} MB exceeds the {max_mb} MB limit."),
    )


def raise_415(received: str):
    raise HTTPException(
        status_code=415,
        detail=err("UNSUPPORTED_MEDIA_TYPE",
                   f"File type '{received}' is not supported. Only application/pdf is accepted."),
    )


def raise_502(service: str):
    logger.error(f"[502] Bad gateway — service: {service}")
    raise HTTPException(
        status_code=502,
        detail=err("BAD_GATEWAY",
                   f"Upstream service '{service}' returned an unexpected response."),
    )


def raise_503(service: str):
    logger.error(f"[503] Service unavailable — service: {service}")
    raise HTTPException(
        status_code=503,
        detail=err("SERVICE_UNAVAILABLE",
                   f"The '{service}' service is currently unavailable."),
    )


def raise_504(service: str, timeout_seconds: int = 30):
    raise HTTPException(
        status_code=504,
        detail=err("GATEWAY_TIMEOUT",
                   f"The '{service}' service did not respond within {timeout_seconds}s."),
    )


# ---------------------------------------------------------------------------
# Serialisers — Model → dict
# ---------------------------------------------------------------------------

def _doc_to_dict(doc: Document) -> dict:
    return {
        "document_id": doc.document_id,
        "filename": doc.filename,
        "title": doc.title,
        "upload_type": doc.upload_type.value if doc.upload_type else None,
        "status": doc.status.value if doc.status else None,
        "file_size_bytes": doc.file_size_bytes,
        "page_count": doc.page_count,
        "references_count": doc.references_count,
        "claims_count": doc.claims_count,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


def _ref_to_dict(ref: Reference) -> dict:
    return {
        "reference_id": ref.reference_id,
        "document_id": ref.document_id,
        "raw_reference": ref.raw_reference,
        "extracted_title": ref.extracted_title,
        "extracted_authors": ref.extracted_authors,
        "extracted_year": ref.extracted_year,
        "extracted_doi": ref.extracted_doi,
        "doi_normalized": ref.doi_normalized,
        "doi_status": ref.doi_status.value if ref.doi_status else None,
        "metadata_status": ref.metadata_status.value if ref.metadata_status else None,
        "metadata_match_score": ref.metadata_match_score,
        "position": ref.position,
    }


def _claim_to_dict(claim: Claim) -> dict:
    return {
        "claim_id": claim.claim_id,
        "document_id": claim.document_id,
        "claim_text": claim.claim_text,
        "claim_type": claim.claim_type,
        "section_name": claim.section_name,
        "source_paragraph": claim.source_paragraph,
        "citation_text": claim.citation_text,
        "page_number": claim.page_number,
        "paragraph_index": claim.paragraph_index,
        "sentence_index": claim.sentence_index,
        "extraction_confidence": claim.extraction_confidence,
        "mapping_status": claim.mapping_status,
        "citations": [_citation_to_dict(c) for c in claim.citations],
    }


def _citation_to_dict(cit: Citation) -> dict:
    return {
        "citation_id": cit.citation_id,
        "citation_text": cit.citation_text,
        "citation_style": cit.citation_style,
        "mapped_reference_id": cit.mapped_reference_id,
        "mapping_confidence": cit.mapping_confidence,
        "mapping_uncertain": cit.mapping_uncertain,
    }


def _link_to_dict(link: ClaimReferenceLink) -> dict:
    return {
        "link_id": link.link_id,
        "claim_id": link.claim_id,
        "claim_text": link.claim.claim_text if link.claim else None,
        "citation_text": link.citation.citation_text if link.citation else None,
        "citation_style": link.citation.citation_style if link.citation else None,
        "reference_id": link.reference_id,
        "reference_title": link.reference.extracted_title if link.reference else None,
        "doi": link.reference.doi_normalized if link.reference else None,
        "mapping_status": link.mapping_status,
        "mapping_confidence": link.mapping_confidence,
        "mapping_uncertain": (link.mapping_confidence or 1.0) < 0.7,
    }


def _vr_to_dict(vr: VerificationResult) -> dict:
    return {
        "result_id": vr.result_id,
        "claim_id": vr.claim_id,
        "claim_text": vr.claim.claim_text if vr.claim else None,
        "citation_text": vr.citation.citation_text if vr.citation else None,
        "reference_id": vr.reference_id,
        "reference_title": vr.reference.extracted_title if vr.reference else None,
        "doi": vr.reference.doi_normalized if vr.reference else None,
        "support_status": vr.support_status.value if vr.support_status else None,
        "confidence_score": vr.confidence,
        "human_review_required": vr.human_review_required,
        "explanation": vr.explanation,
        "evidence_availability": vr.evidence_availability.value if vr.evidence_availability else None,
        "evidence_used_count": vr.evidence_used_count,
        "overall_similarity_score": vr.overall_similarity_score,
        "verification_method": vr.verification_method.value if vr.verification_method else None,
        "safety_risk_level": vr.safety_risk_level,
        "any_safety_triggered": any(c.triggered for c in vr.safety_checks),
        "cache_source": vr.cache_source.value if vr.cache_source else None,
        "ml_rag_conflict": False,
        "created_at": vr.created_at.isoformat() if vr.created_at else None,
        "updated_at": vr.updated_at.isoformat() if vr.updated_at else None,
    }


def _safety_to_dict(s: SafetyCheck) -> dict:
    return {
        "rule": s.rule_id,
        "triggered": s.triggered,
        "reason": (s.details or {}).get("message") if s.triggered else None,
        "override_status": s.overridden_to,
    }


def _pipeline_run_to_dict(run: PipelineRun) -> dict:
    return {
        "pipeline_run_id": run.pipeline_run_id,
        "document_id": run.document_id,
        "status": run.status.value if run.status else None,
        "mode": run.mode.value if run.mode else None,
        "progress_percentage": run.progress_percentage,
        "current_step": run.current_step,
        "error_detail": run.error_detail,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _step_to_dict(s: PipelineRunStep) -> dict:
    return {
        "step": s.step,
        "status": s.status.value if s.status else None,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        "error_detail": s.error_detail,
    }


def _report_to_dict(r: Report) -> dict:
    return {
        "report_id": r.report_id,
        "document_id": r.document_id,
        "title": r.title,
        "format": r.format.value if r.format else None,
        "summary": {
            "document_id": r.document_id,
            "total_claims": r.total_claims,
            "total_references": r.total_references,
            "supported": r.supported,
            "partially_supported": r.partially_supported,
            "not_supported": r.not_supported,
            "insufficient_evidence": r.insufficient_evidence,
            "needs_human_review": r.needs_human_review,
            "valid_dois": r.valid_dois,
            "missing_dois": r.missing_dois,
            "invalid_dois": r.invalid_dois,
            "overall_risk_level": r.overall_risk_level,
            "high_risk_claim_ids": r.high_risk_claim_ids or [],
            "safety_rules_triggered": r.safety_rules_triggered or [],
            "limitations": r.limitations,
        },
        "human_review_recommendations": r.human_review_recommendations or [],
        "html_content": r.html_content,
        "generated_at": r.generated_at.isoformat() if r.generated_at else None,
    }


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

def _run_text_extraction(document_id: str, pdf_bytes: bytes) -> None:
    """Background task: extract text from PDF, then trigger reference extraction."""
    with SessionLocal() as db:
        result = process_document_text(document_id, pdf_bytes, db)
        if result.success:
            logger.info(
                f"[bg] {document_id} — text extraction complete: "
                f"{result.page_count} pages, {len(result.sections)} sections"
            )
            # Chain: trigger reference extraction
            _run_reference_extraction(document_id)
        else:
            logger.error(f"[bg] {document_id} — text extraction failed: {result.error}")


def _run_text_processing(document_id: str, text: str) -> None:
    """Background task: process plain text, then trigger reference extraction."""
    with SessionLocal() as db:
        result = process_text_document(document_id, text, db)
        if result.success:
            logger.info(
                f"[bg] {document_id} — text processing complete: "
                f"{len(result.sections)} sections"
            )
            # Chain: trigger reference extraction
            _run_reference_extraction(document_id)
        else:
            logger.error(f"[bg] {document_id} — text processing failed: {result.error}")


def _run_reference_extraction(document_id: str) -> None:
    """Background task: extract references, then trigger DOI lookup."""
    with SessionLocal() as db:
        result = process_references(document_id, db)
        if result.success:
            logger.info(
                f"[bg] {document_id} — reference extraction complete: "
                f"{result.total} refs, {result.found_doi} DOIs found"
            )
            # Chain: trigger DOI lookup
            _run_doi_lookup(document_id)
        else:
            logger.error(f"[bg] {document_id} — reference extraction failed: {result.error}")


def _run_doi_lookup(document_id: str) -> None:
    """Background task: lookup DOI metadata for all references."""
    with SessionLocal() as db:
        result = lookup_all_references(document_id, db)
        if result.success:
            logger.info(
                f"[bg] {document_id} — DOI lookup complete: "
                f"{result.succeeded} succeeded, {result.failed} failed, "
                f"{result.cached} cached"
            )
        else:
            logger.error(f"[bg] {document_id} — DOI lookup failed: {result.error}")


def _run_text_extraction_from_db(document_id: str) -> None:
    """Background task: re-trigger text extraction using stored file bytes."""
    from app.db.repositories import DocumentRepository as DR
    with SessionLocal() as db:
        doc = DR(db).get(document_id)
        if not doc or not doc.file_path:
            logger.error(f"[bg] {document_id} — no file path stored, cannot re-extract")
            return
        try:
            with open(doc.file_path, "rb") as f:
                pdf_bytes = f.read()
            result = process_document_text(document_id, pdf_bytes, db)
            if result.success:
                logger.info(f"[bg] {document_id} — re-extraction complete: {result.page_count} pages")
                _run_reference_extraction(document_id)
        except Exception as e:
            logger.error(f"[bg] {document_id} — re-extraction failed: {e}")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/v1/health", tags=["Health"])
def get_health():
    return ok(
        {"status": "OK", "service": SERVICE, "version": VERSION, "timestamp": NOW()},
        message="Backend is healthy",
    )


@app.get("/api/v1/health/readiness", tags=["Health"])
def get_readiness(db: Session = Depends(get_db)):
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception:
        raise_503("database")
    return ok(
        {"status": "OK", "service": SERVICE, "version": VERSION, "timestamp": NOW()},
        message="Backend is ready",
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@app.get("/api/v1/documents", tags=["Documents"])
def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    repo = DocumentRepository(db)
    offset = (page - 1) * page_size
    docs = repo.list(offset=offset, limit=page_size, status=status)
    total = repo.count(status=status)
    return ok({
        "documents": [_doc_to_dict(d) for d in docs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    })


@app.post("/api/v1/documents/upload", tags=["Documents"])
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_title: Optional[str] = None,
    uploaded_by: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise_415(file.content_type)
    ext = ("." + file.filename.rsplit(".", 1)[-1].lower()) if file.filename and "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise_415(ext or "unknown")
    contents = await file.read()
    size_bytes = len(contents)
    if size_bytes > MAX_FILE_SIZE_BYTES:
        raise_413(MAX_FILE_SIZE_BYTES / 1024 / 1024, size_bytes / 1024 / 1024)

    doc = Document(
        document_id=new_id("doc_"),
        title=document_title,
        filename=file.filename,
        upload_type=UploadType.PDF,
        status=DocumentProcessingStatus.UPLOADED,
        file_size_bytes=size_bytes,
    )
    DocumentRepository(db).create(doc)
    db.commit()
    logger.info(f"[document] {doc.document_id} uploaded — {size_bytes} bytes — {file.filename}")

    # Trigger text extraction in background
    background_tasks.add_task(
        _run_text_extraction,
        document_id=doc.document_id,
        pdf_bytes=contents,
    )

    return ok(_doc_to_dict(doc), message="Document uploaded. Text extraction started.")


@app.post("/api/v1/documents/text", tags=["Documents"])
def upload_text_document(
    background_tasks: BackgroundTasks,
    body: TextDocumentRequest,
    db: Session = Depends(get_db),
):
    doc = Document(
        document_id=new_id("doc_"),
        title=body.title,
        filename=f"{body.title}.txt",
        upload_type=UploadType.TEXT,
        status=DocumentProcessingStatus.UPLOADED,
        file_size_bytes=len(body.text.encode("utf-8")),
    )
    DocumentRepository(db).create(doc)
    db.commit()
    logger.info(f"[document] {doc.document_id} created (text) — {doc.file_size_bytes} bytes — {doc.title}")

    # Trigger text processing in background
    background_tasks.add_task(
        _run_text_processing,
        document_id=doc.document_id,
        text=body.text,
    )

    return ok(_doc_to_dict(doc), message="Text document created. Processing started.")


@app.get("/api/v1/documents/{document_id}", tags=["Documents"])
def get_document(document_id: str = Path(...), db: Session = Depends(get_db)):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    return ok(_doc_to_dict(doc))


@app.delete("/api/v1/documents/{document_id}", tags=["Documents"])
def delete_document(document_id: str = Path(...), db: Session = Depends(get_db)):
    repo = DocumentRepository(db)
    doc = repo.get(document_id)
    if not doc:
        raise_404("Document", document_id)
    active_statuses = {
        DocumentProcessingStatus.TEXT_EXTRACTING,
        DocumentProcessingStatus.CLAIMS_EXTRACTING,
        DocumentProcessingStatus.VERIFYING,
    }
    if doc.status in active_statuses:
        raise_409("WORKFLOW_CONFLICT",
                  f"Cannot delete document '{document_id}' while it is being processed.")
    repo.delete(document_id)
    db.commit()
    logger.info(f"[document] {document_id} deleted")
    return ok({"document_id": document_id, "deleted": True}, message="Document deleted.")


@app.get("/api/v1/documents/{document_id}/status", tags=["Documents"])
def get_document_status(document_id: str = Path(...), db: Session = Depends(get_db)):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)

    status_map = {
        DocumentProcessingStatus.UPLOADED:            ("idle",       0,   None),
        DocumentProcessingStatus.TEXT_EXTRACTING:     ("processing", 15,  "TEXT_EXTRACTION"),
        DocumentProcessingStatus.TEXT_EXTRACTED:      ("processing", 25,  "SECTION_DETECTION"),
        DocumentProcessingStatus.REFERENCES_EXTRACTING: ("processing", 35, "REFERENCE_EXTRACTION"),
        DocumentProcessingStatus.REFERENCES_EXTRACTED: ("processing", 45, "DOI_LOOKUP"),
        DocumentProcessingStatus.DOI_VERIFYING:       ("processing", 50,  "DOI_LOOKUP"),
        DocumentProcessingStatus.DOI_VERIFIED:        ("processing", 55,  "CLAIM_EXTRACTION"),
        DocumentProcessingStatus.CLAIMS_EXTRACTING:   ("processing", 60,  "CLAIM_EXTRACTION"),
        DocumentProcessingStatus.CLAIMS_EXTRACTED:    ("processing", 70,  "CITATION_MAPPING"),
        DocumentProcessingStatus.EVIDENCE_PREPARING:  ("processing", 75,  "EVIDENCE_PREPARATION"),
        DocumentProcessingStatus.EVIDENCE_READY:      ("processing", 80,  "CACHE_CHECK"),
        DocumentProcessingStatus.VERIFYING:           ("processing", 90,  "GENAI_VERIFICATION"),
        DocumentProcessingStatus.VERIFIED:            ("completed",  100, None),
        DocumentProcessingStatus.REPORT_GENERATED:    ("completed",  100, None),
        DocumentProcessingStatus.FAILED:              ("failed",     0,   None),
        DocumentProcessingStatus.PARTIAL_FAILED:      ("failed",     0,   None),
    }
    frontend_status, progress, current_step = status_map.get(doc.status, ("idle", 0, None))

    latest_run = PipelineRunRepository(db).list_by_document(document_id)
    latest_run_id = latest_run[0].pipeline_run_id if latest_run else None

    return ok({
        "document_id": document_id,
        "status": doc.status.value,
        "frontend_status": frontend_status,
        "current_step": current_step,
        "progress_percentage": progress,
        "latest_pipeline_run_id": latest_run_id,
        "message": None,
        "error_detail": None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    })


@app.post("/api/v1/documents/{document_id}/reset", tags=["Documents"])
def reset_document(
    document_id: str = Path(...),
    body: ResetRequest = ...,
    db: Session = Depends(get_db),
):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    active = {DocumentProcessingStatus.TEXT_EXTRACTING,
              DocumentProcessingStatus.CLAIMS_EXTRACTING,
              DocumentProcessingStatus.VERIFYING}
    if doc.status in active:
        raise_409("WORKFLOW_CONFLICT",
                  f"Cannot reset document '{document_id}' while it is being processed.")
    doc.status = DocumentProcessingStatus.UPLOADED
    db.commit()
    logger.info(f"[document] {document_id} reset — reason: {body.reason}")
    return ok(_doc_to_dict(doc),
              message=f"Document reset. Reason: {body.reason}.")


# ---------------------------------------------------------------------------
# Text / Sections
# ---------------------------------------------------------------------------

@app.get("/api/v1/documents/{document_id}/raw-text", tags=["Text"])
def get_raw_text(document_id: str = Path(...), db: Session = Depends(get_db)):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    if doc.status == DocumentProcessingStatus.UPLOADED:
        raise_409("WORKFLOW_CONFLICT", "Text extraction has not been completed yet.")
    sections = DocumentSectionRepository(db).list_by_document(document_id)
    full_text = "\n\n".join(s.full_text or "" for s in sections if s.full_text)
    return ok({"document_id": document_id, "raw_text": full_text, "cleaned_text": full_text})


@app.get("/api/v1/documents/{document_id}/sections", tags=["Text"])
def get_sections(document_id: str = Path(...), db: Session = Depends(get_db)):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    sections = DocumentSectionRepository(db).list_by_document(document_id)
    return ok({
        "document_id": document_id,
        "sections": [
            {
                "section_id": s.section_id,
                "name": s.name,
                "type": s.type.value if s.type else None,
                "order_index": s.order_index,
                "text_preview": s.text_preview,
                "start_char": s.start_char,
                "end_char": s.end_char,
            }
            for s in sections
        ],
    })


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

@app.post("/api/v1/documents/{document_id}/extract-references", status_code=202, tags=["References"])
def extract_references(
    background_tasks: BackgroundTasks,
    document_id: str = Path(...),
    body: DebugStepRequest = DebugStepRequest(),
    db: Session = Depends(get_db),
):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    if doc.status == DocumentProcessingStatus.UPLOADED:
        raise_409("WORKFLOW_CONFLICT", "Text extraction must complete before references can be extracted.")
    background_tasks.add_task(_run_reference_extraction, document_id=document_id)
    return ok({"document_id": document_id, "status": "QUEUED",
               "message": "Reference extraction has been queued."})


@app.get("/api/v1/documents/{document_id}/references", tags=["References"])
def get_references(
    document_id: str = Path(...),
    doi_status: Optional[str] = Query(default=None),
    metadata_status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    repo = ReferenceRepository(db)
    offset = (page - 1) * page_size
    refs = repo.list_by_document(document_id, doi_status=doi_status,
                                  metadata_status=metadata_status,
                                  offset=offset, limit=page_size)
    total = repo.count_by_document(document_id)
    return ok({
        "document_id": document_id,
        "references": [_ref_to_dict(r) for r in refs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    })


@app.get("/api/v1/references/{reference_id}", tags=["References"])
def get_reference(reference_id: str = Path(...), db: Session = Depends(get_db)):
    ref = ReferenceRepository(db).get(reference_id)
    if not ref:
        raise_404("Reference", reference_id)
    return ok(_ref_to_dict(ref))


@app.post("/api/v1/references/{reference_id}/verify-doi", tags=["References"])
def verify_doi(
    reference_id: str = Path(...),
    body: DebugStepRequest = DebugStepRequest(),
    db: Session = Depends(get_db),
):
    ref = ReferenceRepository(db).get(reference_id)
    if not ref:
        raise_404("Reference", reference_id)

    result = lookup_single_reference(reference_id, db, force=body.force or False)
    return ok({
        "reference_id": reference_id,
        "doi_status": result.doi_status.value if result.doi_status else None,
        "metadata_status": result.metadata_status.value if result.metadata_status else None,
        "metadata_quality_score": result.match_score,
        "title_match": result.title_match,
        "year_match": result.year_match,
        "author_match": result.author_match,
        "cached": result.cached,
    })


@app.get("/api/v1/references/{reference_id}/metadata", tags=["References"])
def get_reference_metadata(reference_id: str = Path(...), db: Session = Depends(get_db)):
    ref = ReferenceRepository(db).get(reference_id)
    if not ref:
        raise_404("Reference", reference_id)
    meta = SourceMetadataRepository(db).get_by_reference(reference_id)
    if not meta:
        return ok({
            "reference_id": reference_id,
            "metadata_status": ref.metadata_status.value if ref.metadata_status else "NOT_LOOKED_UP",
            "doi": ref.doi_normalized,
            "title": None,
            "authors": None,
            "year": None,
            "journal": None,
            "publisher": None,
            "url": None,
            "abstract": None,
            "fetched_at": None,
        })
    return ok({
        "reference_id": reference_id,
        "metadata_status": meta.metadata_status.value if meta.metadata_status else None,
        "doi": meta.doi,
        "title": meta.title,
        "authors": meta.authors,
        "year": meta.year,
        "journal": meta.journal,
        "publisher": meta.publisher,
        "url": meta.url,
        "abstract": meta.abstract,
        "fetched_at": meta.fetched_at.isoformat() if meta.fetched_at else None,
    })


@app.post("/api/v1/documents/{document_id}/verify-dois", status_code=202, tags=["References"])
def verify_all_dois(
    background_tasks: BackgroundTasks,
    document_id: str = Path(...),
    body: DebugStepRequest = DebugStepRequest(),
    db: Session = Depends(get_db),
):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    background_tasks.add_task(_run_doi_lookup, document_id=document_id)
    return ok({"document_id": document_id, "status": "QUEUED",
               "message": "DOI verification has been queued."})


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

@app.post("/api/v1/documents/{document_id}/extract-claims", status_code=202, tags=["Claims"])
def extract_claims(
    document_id: str = Path(...),
    body: DebugStepRequest = DebugStepRequest(),
    db: Session = Depends(get_db),
):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    doc.status = DocumentProcessingStatus.CLAIMS_EXTRACTING
    db.commit()
    return ok({"document_id": document_id, "status": "QUEUED",
               "message": "Claim extraction has been queued."})


@app.get("/api/v1/documents/{document_id}/claims", tags=["Claims"])
def get_claims(
    document_id: str = Path(...),
    claim_type: Optional[str] = Query(default=None),
    mapping_status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    repo = ClaimRepository(db)
    offset = (page - 1) * page_size
    claims = repo.list_by_document(document_id, claim_type=claim_type,
                                    mapping_status=mapping_status,
                                    offset=offset, limit=page_size)
    total = repo.count_by_document(document_id)
    return ok({
        "document_id": document_id,
        "claims": [_claim_to_dict(c) for c in claims],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    })


@app.get("/api/v1/documents/{document_id}/citations", tags=["Claims"])
def get_citations(document_id: str = Path(...), db: Session = Depends(get_db)):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    citations = CitationRepository(db).list_by_document(document_id)
    return ok({
        "document_id": document_id,
        "citations": [_citation_to_dict(c) for c in citations],
    })


@app.get("/api/v1/documents/{document_id}/claim-reference-links", tags=["Claims"])
def get_claim_reference_links(document_id: str = Path(...), db: Session = Depends(get_db)):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    links = ClaimReferenceLinkRepository(db).list_by_document(document_id)
    return ok({
        "document_id": document_id,
        "pairs": [_link_to_dict(l) for l in links],
    })


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

@app.post("/api/v1/documents/{document_id}/prepare-evidence", status_code=202, tags=["Evidence"])
def prepare_evidence(
    document_id: str = Path(...),
    body: DebugStepRequest = DebugStepRequest(),
    db: Session = Depends(get_db),
):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    doc.status = DocumentProcessingStatus.EVIDENCE_PREPARING
    db.commit()
    return ok({"document_id": document_id, "status": "QUEUED",
               "message": "Evidence preparation has been queued."})


@app.get("/api/v1/claims/{claim_id}/evidence-package", tags=["Evidence"])
def get_evidence_package(claim_id: str = Path(...), db: Session = Depends(get_db)):
    pkg = EvidencePackageRepository(db).get_by_claim(claim_id)
    if not pkg:
        raise_404("EvidencePackage", claim_id)
    meta = SourceMetadataRepository(db).get_by_reference(pkg.reference_id) if pkg.reference_id else None
    return ok({
        "claim_id": pkg.claim_id,
        "reference_id": pkg.reference_id,
        "claim_text": pkg.claim.claim_text if pkg.claim else None,
        "citation_text": pkg.claim.citation_text if pkg.claim else None,
        "doi": pkg.reference.doi_normalized if pkg.reference else None,
        "doi_status": pkg.reference.doi_status.value if pkg.reference and pkg.reference.doi_status else None,
        "evidence_level": pkg.evidence_level.value if pkg.evidence_level else None,
        "source_evidence": {
            "evidence_availability": pkg.evidence_level.value if pkg.evidence_level else None,
            "text": pkg.source_evidence_text,
            "source_url": pkg.source_evidence_url,
        },
        "policy": {
            "embedding_model_version": pkg.embedding_model_version,
            "prompt_version": pkg.prompt_version,
            "verification_policy_version": pkg.verification_policy_version,
        },
        "metadata": {
            "reference_id": pkg.reference_id,
            "metadata_status": meta.metadata_status.value if meta and meta.metadata_status else None,
            "doi": meta.doi if meta else None,
            "title": meta.title if meta else None,
            "authors": meta.authors if meta else None,
            "year": meta.year if meta else None,
            "journal": meta.journal if meta else None,
            "abstract": meta.abstract if meta else None,
        } if meta else None,
    })


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@app.post("/api/v1/claims/{claim_id}/check-cache", tags=["Cache"])
def check_cache(
    claim_id: str = Path(...),
    body: CacheCheckRequest = CacheCheckRequest(),
    db: Session = Depends(get_db),
):
    entry = CacheIndexRepository(db).get_by_claim(claim_id)
    if not entry:
        return ok({
            "claim_id": claim_id,
            "cache_status": "NO_HIT",
            "cache_source": None,
            "matched_result_id": None,
            "semantic_similarity": None,
            "reuse_allowed": False,
            "recommendation": "RERUN",
        })
    return ok({
        "claim_id": claim_id,
        "cache_status": entry.cache_status.value,
        "cache_source": entry.cache_source.value if entry.cache_source else None,
        "matched_result_id": entry.matched_result_id,
        "semantic_similarity": entry.semantic_similarity,
        "reuse_allowed": entry.reuse_allowed,
        "recommendation": "REUSE" if entry.reuse_allowed else "RERUN",
    })


@app.get("/api/v1/claims/{claim_id}/cache-result", tags=["Cache"])
def get_cache_result(claim_id: str = Path(...), db: Session = Depends(get_db)):
    entry = CacheIndexRepository(db).get_by_claim(claim_id)
    if not entry:
        raise_404("CacheEntry", claim_id)
    vr = entry.matched_result
    return ok({
        "claim_id": claim_id,
        "cache_source": entry.cache_source.value if entry.cache_source else None,
        "semantic_similarity": entry.semantic_similarity,
        "verification_result": _vr_to_dict(vr) if vr else None,
    })


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

@app.post("/api/v1/claims/{claim_id}/retrieve-evidence", tags=["Retrieval"])
def retrieve_evidence(
    claim_id: str = Path(...),
    body: RetrieveEvidenceRequest = RetrieveEvidenceRequest(),
    db: Session = Depends(get_db),
):
    pkg = EvidencePackageRepository(db).get_by_claim(claim_id)
    if not pkg:
        raise_409("WORKFLOW_CONFLICT", f"No evidence package found for claim '{claim_id}'.")
    result = RetrievalRepository(db).get_by_claim(claim_id)
    if not result:
        raise_404("RetrievalResult", claim_id)
    return ok({
        "claim_id": claim_id,
        "retrieval_status": result.retrieval_status.value,
        "top_chunks": [
            {
                "chunk_id": c.chunk_id,
                "chunk_text": c.chunk_text,
                "similarity_score": c.similarity_score,
                "evidence_type": c.evidence_type,
                "source": c.source,
            }
            for c in result.chunks[:body.top_k]
        ],
        "overall_similarity_score": result.overall_similarity_score,
        "retrieval_confidence": result.retrieval_confidence,
        "semantic_cache_hit": False,
        "service_error_detail": None,
    })


@app.get("/api/v1/claims/{claim_id}/retrieval-results", tags=["Retrieval"])
def get_retrieval_results(claim_id: str = Path(...), db: Session = Depends(get_db)):
    result = RetrievalRepository(db).get_by_claim(claim_id)
    if not result:
        raise_404("RetrievalResult", claim_id)
    return ok({
        "claim_id": claim_id,
        "retrieval_status": result.retrieval_status.value,
        "top_chunks": [
            {
                "chunk_id": c.chunk_id,
                "chunk_text": c.chunk_text,
                "similarity_score": c.similarity_score,
                "evidence_type": c.evidence_type,
                "source": c.source,
            }
            for c in result.chunks
        ],
        "overall_similarity_score": result.overall_similarity_score,
        "retrieval_confidence": result.retrieval_confidence,
        "semantic_cache_hit": False,
        "service_error_detail": None,
    })


# ---------------------------------------------------------------------------
# Pipeline runs
# ---------------------------------------------------------------------------

@app.post("/api/v1/documents/{document_id}/pipeline-runs", status_code=202, tags=["Verification"])
def start_pipeline_run(
    document_id: str = Path(...),
    body: PipelineRunRequest = PipelineRunRequest(),
    db: Session = Depends(get_db),
):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    pr_repo = PipelineRunRepository(db)
    active = pr_repo.get_active_for_document(document_id)
    if active:
        raise_409("WORKFLOW_CONFLICT",
                  f"Pipeline run '{active.pipeline_run_id}' is already active for this document.")

    run = PipelineRun(
        pipeline_run_id=new_id("run_"),
        document_id=document_id,
        status=PipelineRunStatus.QUEUED,
        mode=PipelineRunMode(body.mode),
        progress_percentage=0,
        use_cache=body.use_cache,
        use_rag=body.use_rag,
        use_genai_safety_review=body.use_genai_safety_review,
        generate_report=body.generate_report,
    )
    pr_repo.create(run)
    for step_name in ALL_PIPELINE_STEPS:
        pr_repo.add_step(PipelineRunStep(
            pipeline_run_id=run.pipeline_run_id,
            step=step_name,
            status=PipelineStepStatus.PENDING,
        ))
    doc.status = DocumentProcessingStatus.TEXT_EXTRACTING
    db.commit()
    logger.info(f"[pipeline] {run.pipeline_run_id} started for {document_id} — mode: {body.mode}")
    return ok({
        "pipeline_run_id": run.pipeline_run_id,
        "document_id": document_id,
        "status": "QUEUED",
        "message": "Verification pipeline has been queued.",
    }, message="Pipeline run started.")


@app.get("/api/v1/pipeline-runs/{pipeline_run_id}", tags=["Verification"])
def get_pipeline_run(pipeline_run_id: str = Path(...), db: Session = Depends(get_db)):
    run = PipelineRunRepository(db).get(pipeline_run_id)
    if not run:
        raise_404("PipelineRun", pipeline_run_id)
    return ok(_pipeline_run_to_dict(run))


@app.get("/api/v1/pipeline-runs/{pipeline_run_id}/steps", tags=["Verification"])
def get_pipeline_run_steps(pipeline_run_id: str = Path(...), db: Session = Depends(get_db)):
    repo = PipelineRunRepository(db)
    run = repo.get(pipeline_run_id)
    if not run:
        raise_404("PipelineRun", pipeline_run_id)
    steps = repo.list_steps(pipeline_run_id)
    return ok({
        "pipeline_run_id": pipeline_run_id,
        "steps": [_step_to_dict(s) for s in steps],
    })


@app.post("/api/v1/pipeline-runs/{pipeline_run_id}/cancel", tags=["Verification"])
def cancel_pipeline_run(pipeline_run_id: str = Path(...), db: Session = Depends(get_db)):
    run = PipelineRunRepository(db).get(pipeline_run_id)
    if not run:
        raise_404("PipelineRun", pipeline_run_id)
    if run.status in (PipelineRunStatus.COMPLETED, PipelineRunStatus.FAILED,
                      PipelineRunStatus.CANCELLED):
        raise_409("WORKFLOW_CONFLICT",
                  f"Pipeline run '{pipeline_run_id}' is already {run.status.value}.")
    run.status = PipelineRunStatus.CANCELLED
    db.commit()
    logger.info(f"[pipeline] {pipeline_run_id} cancelled")
    return ok(_pipeline_run_to_dict(run), message="Pipeline run cancelled.")


# Deprecated
@app.post("/api/v1/documents/{document_id}/run-verification", status_code=202,
          tags=["Verification"], deprecated=True)
def run_verification(document_id: str = Path(...), db: Session = Depends(get_db)):
    """Deprecated. Use POST /documents/{document_id}/pipeline-runs instead."""
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    return ok({"document_id": document_id, "status": "QUEUED",
               "message": "Deprecated. Use /pipeline-runs instead."})


# ---------------------------------------------------------------------------
# Verification results
# ---------------------------------------------------------------------------

@app.get("/api/v1/documents/{document_id}/verification-results", tags=["Verification"])
def get_verification_results(
    document_id: str = Path(...),
    support_status: Optional[str] = Query(default=None),
    human_review_required: Optional[bool] = Query(default=None),
    cache_source: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    repo = VerificationResultRepository(db)
    offset = (page - 1) * page_size
    results = repo.list_by_document(
        document_id,
        support_status=support_status,
        human_review_required=human_review_required,
        cache_source=cache_source,
        offset=offset,
        limit=page_size,
    )
    total = repo.count_by_document(document_id)
    human_review_count = repo.count_by_document(document_id, human_review_required=True)
    return ok({
        "document_id": document_id,
        "results": [_vr_to_dict(r) for r in results],
        "total": total,
        "human_review_count": human_review_count,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    })


@app.get("/api/v1/verification-results/{result_id}", tags=["Verification"])
def get_verification_result(result_id: str = Path(...), db: Session = Depends(get_db)):
    vr = VerificationResultRepository(db).get(result_id)
    if not vr:
        raise_404("VerificationResult", result_id)
    return ok(_vr_to_dict(vr))


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

@app.get("/api/v1/verification-results/{result_id}/safety-checks", tags=["Safety"])
def get_safety_checks(result_id: str = Path(...), db: Session = Depends(get_db)):
    vr = VerificationResultRepository(db).get(result_id)
    if not vr:
        raise_404("VerificationResult", result_id)
    checks = SafetyCheckRepository(db).list_by_result(result_id)
    return ok({
        "result_id": result_id,
        "checks": [_safety_to_dict(c) for c in checks],
        "any_triggered": any(c.triggered for c in checks),
        "final_status": vr.support_status.value if vr.support_status else None,
    })


@app.get("/api/v1/documents/{document_id}/safety-summary", tags=["Safety"])
def get_safety_summary(document_id: str = Path(...), db: Session = Depends(get_db)):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    results = VerificationResultRepository(db).list_by_document(document_id)
    all_checks = []
    for vr in results:
        all_checks.extend(SafetyCheckRepository(db).list_by_result(vr.result_id))
    triggered = [c for c in all_checks if c.triggered]
    from collections import defaultdict
    rule_map = defaultdict(list)
    for c in triggered:
        rule_map[c.rule_id].append(c.verification_result_id)
    return ok({
        "document_id": document_id,
        "total_claims_checked": len(results),
        "rules_triggered": [
            {"rule": rule, "triggered_count": len(ids), "affected_claim_ids": ids}
            for rule, ids in rule_map.items()
        ],
    })


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@app.get("/api/v1/documents/{document_id}/summary", tags=["Reports"])
def get_document_summary(document_id: str = Path(...), db: Session = Depends(get_db)):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    reports = ReportRepository(db).list_by_document(document_id)
    if reports:
        r = reports[0]
        return ok({
            "document_id": document_id,
            "total_claims": r.total_claims,
            "total_references": r.total_references,
            "supported": r.supported,
            "partially_supported": r.partially_supported,
            "not_supported": r.not_supported,
            "insufficient_evidence": r.insufficient_evidence,
            "needs_human_review": r.needs_human_review,
            "valid_dois": r.valid_dois,
            "missing_dois": r.missing_dois,
            "invalid_dois": r.invalid_dois,
            "overall_risk_level": r.overall_risk_level,
            "high_risk_claim_ids": r.high_risk_claim_ids or [],
            "safety_rules_triggered": r.safety_rules_triggered or [],
            "limitations": r.limitations,
        })
    return ok({"document_id": document_id, "message": "No report generated yet."})


@app.post("/api/v1/documents/{document_id}/reports", status_code=202, tags=["Reports"])
def generate_report(document_id: str = Path(...), db: Session = Depends(get_db)):
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    report = Report(
        report_id=new_id("rpt_"),
        document_id=document_id,
        title=f"Verification Report — {doc.title or doc.filename}",
        format=ReportFormat.JSON,
        total_claims=doc.claims_count,
        total_references=doc.references_count,
        generated_at=datetime.now(timezone.utc),
    )
    ReportRepository(db).create(report)
    db.commit()
    return ok({
        "report_id": report.report_id,
        "document_id": document_id,
        "status": "QUEUED",
        "message": "Report generation has been queued.",
    }, message="Report generation queued.")


@app.get("/api/v1/reports/{report_id}", tags=["Reports"])
def get_report(report_id: str = Path(...), db: Session = Depends(get_db)):
    report = ReportRepository(db).get(report_id)
    if not report:
        raise_404("Report", report_id)
    return ok(_report_to_dict(report))


@app.get("/api/v1/reports/{report_id}/download", tags=["Reports"])
def download_report(
    report_id: str = Path(...),
    format: str = Query(default="PDF", enum=["PDF", "HTML"]),
    db: Session = Depends(get_db),
):
    report = ReportRepository(db).get(report_id)
    if not report:
        raise_404("Report", report_id)
    if format == "HTML":
        html = f"""<!DOCTYPE html>
<html><head><title>Verification Report — {report_id}</title></head>
<body>
  <h1>Verification Report</h1>
  <p><strong>Report ID:</strong> {report_id}</p>
  <p><strong>Document:</strong> {report.document_id}</p>
  <p><strong>Total claims:</strong> {report.total_claims} &nbsp;
     <strong>Supported:</strong> {report.supported} &nbsp;
     <strong>Needs review:</strong> {report.needs_human_review}</p>
  <p><em>{report.limitations or ""}</em></p>
</body></html>"""
        return HTMLResponse(content=html)
    raise HTTPException(status_code=501, detail=err("NOT_IMPLEMENTED", "PDF export not yet available."))


# Deprecated
@app.get("/api/v1/documents/{document_id}/report", tags=["Reports"], deprecated=True)
def get_document_report_deprecated(
    document_id: str = Path(...),
    format: str = Query(default="json"),
    db: Session = Depends(get_db),
):
    """Deprecated. Use POST /documents/{document_id}/reports and GET /reports/{report_id}."""
    return ok({"deprecated": True, "message": "Use POST /documents/{id}/reports instead."})


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

@app.post("/api/v1/verification-results/{result_id}/feedback", status_code=201, tags=["Reports"])
def submit_feedback(
    result_id: str = Path(...),
    body: FeedbackRequest = ...,
    db: Session = Depends(get_db),
):
    vr = VerificationResultRepository(db).get(result_id)
    if not vr:
        raise_404("VerificationResult", result_id)
    existing = UserFeedbackRepository(db).get_by_result(result_id)
    if existing:
        raise_409("FEEDBACK_ALREADY_SUBMITTED",
                  f"Feedback '{existing.feedback_id}' already submitted for result '{result_id}'.")
    feedback = UserFeedback(
        feedback_id=new_id("fb_"),
        verification_result_id=result_id,
        feedback_type=FeedbackType.VERIFICATION_RESULT,
        user_label=body.user_label,
        user_comment=body.user_comment,
        user_role=body.user_role,
    )
    UserFeedbackRepository(db).create(feedback)
    db.commit()
    logger.info(f"[feedback] {feedback.feedback_id} submitted for result {result_id} — label: {body.user_label}")
    return ok({
        "feedback_id": feedback.feedback_id,
        "result_id": result_id,
        "user_label": feedback.user_label,
        "stored": True,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
        "updated_at": None,
    }, message="Feedback submitted successfully.")


@app.post("/api/v1/claim-reference-links/{link_id}/feedback", status_code=201, tags=["Reports"])
def submit_mapping_feedback(
    link_id: str = Path(...),
    body: MappingFeedbackRequest = ...,
    db: Session = Depends(get_db),
):
    link = ClaimReferenceLinkRepository(db).get(link_id)
    if not link:
        raise_404("ClaimReferenceLink", link_id)
    feedback = UserFeedback(
        feedback_id=new_id("fb_"),
        claim_reference_link_id=link_id,
        feedback_type=FeedbackType.MAPPING,
        user_label=body.feedback_type,
        user_comment=body.comment,
        suggested_reference_id=body.suggested_reference_id,
    )
    UserFeedbackRepository(db).create(feedback)
    db.commit()
    logger.info(f"[feedback] {feedback.feedback_id} mapping feedback for link {link_id} — type: {body.feedback_type}")
    return ok({
        "feedback_id": feedback.feedback_id,
        "result_id": None,
        "user_label": feedback.user_label,
        "stored": True,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
        "updated_at": None,
    }, message="Mapping feedback submitted successfully.")


@app.post("/api/v1/uat/surveys", status_code=201, tags=["Reports"])
def submit_uat_survey(body: UatSurveyRequest, db: Session = Depends(get_db)):
    doc = DocumentRepository(db).get(body.document_id)
    if not doc:
        raise_404("Document", body.document_id)
    survey = UatSurvey(
        survey_id=new_id("srv_"),
        document_id=body.document_id,
        user_id=body.user_id,
        responses=body.responses,
        overall_rating=body.overall_rating,
        free_text=body.free_text,
    )
    UatSurveyRepository(db).create(survey)
    db.commit()
    return ok({
        "survey_id": survey.survey_id,
        "document_id": survey.document_id,
        "stored": True,
        "created_at": survey.created_at.isoformat() if survey.created_at else None,
    }, message="UAT survey submitted successfully.")


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

@app.post("/api/v1/internal/rag/embed", tags=["Internal"])
def internal_rag_embed(body: dict, db: Session = Depends(get_db)):
    return ok({"embedding": [0.12, -0.34, 0.56, 0.78, -0.90],
               "model_version": "text-embedding-3-small-v1"})


@app.post("/api/v1/internal/rag/search", tags=["Internal"])
def internal_rag_search(body: dict, db: Session = Depends(get_db)):
    return ok({"results": [], "total": 0})


@app.post("/api/v1/internal/genai/verify", tags=["Internal"])
def internal_genai_verify(body: dict, db: Session = Depends(get_db)):
    return ok({"support_status": "SUPPORTED", "confidence_score": 0.87,
               "explanation": "Placeholder — real GenAI call not yet implemented.",
               "raw_response": None})


@app.post("/api/v1/internal/genai/extract-claims", tags=["Internal"])
def internal_genai_extract_claims(body: dict, db: Session = Depends(get_db)):
    return ok({"claims": [], "raw_response": None})


# ---------------------------------------------------------------------------
# Missing endpoints from openapi_full_final_corrected.yaml
# ---------------------------------------------------------------------------

# ── Documents ────────────────────────────────────────────────────────────────

@app.post("/api/v1/documents/{document_id}/extract-text", status_code=202, tags=["Debug"])
def extract_text_debug(
    background_tasks: BackgroundTasks,
    document_id: str = Path(...),
    db: Session = Depends(get_db),
):
    """[Debug] Manually trigger text extraction for a document."""
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise_404("Document", document_id)
    background_tasks.add_task(_run_text_extraction_from_db, document_id=document_id)
    return ok({"document_id": document_id, "status": "QUEUED",
               "message": "Text extraction has been queued."})


# ── Claims ───────────────────────────────────────────────────────────────────

@app.post("/api/v1/claims/{claim_id}/verify", status_code=202, tags=["Verification"])
def verify_claim(
    background_tasks: BackgroundTasks,
    claim_id: str = Path(...),
    db: Session = Depends(get_db),
):
    """Trigger verification for a single claim. Implemented in BE-9."""
    claim = ClaimRepository(db).get(claim_id)
    if not claim:
        raise_404("Claim", claim_id)
    return ok({"claim_id": claim_id, "status": "QUEUED",
               "message": "Claim verification queued. Implemented in BE-9."})


# ── Internal GenAI ────────────────────────────────────────────────────────────

@app.post("/internal/genai/generate-explanation", tags=["Internal"])
def internal_genai_generate_explanation(body: dict, db: Session = Depends(get_db)):
    """Generate a human-readable explanation for a verification result."""
    return ok({"explanation": "Placeholder — BE-9.", "raw_response": None})


@app.post("/internal/genai/generate-report-summary", tags=["Internal"])
def internal_genai_generate_report_summary(body: dict, db: Session = Depends(get_db)):
    """Generate a report summary for a document verification run."""
    return ok({"summary": "Placeholder — BE-11.", "raw_response": None})


@app.post("/internal/genai/map-citations", tags=["Internal"])
def internal_genai_map_citations(body: dict, db: Session = Depends(get_db)):
    """Map in-text citations to extracted references."""
    return ok({"mappings": [], "raw_response": None})


@app.post("/internal/genai/safety-review", tags=["Internal"])
def internal_genai_safety_review(body: dict, db: Session = Depends(get_db)):
    """Run a safety review on a verification result."""
    return ok({"safe": True, "flags": [], "raw_response": None})


@app.post("/internal/genai/understand-document", tags=["Internal"])
def internal_genai_understand_document(body: dict, db: Session = Depends(get_db)):
    """Generate a high-level document understanding summary."""
    return ok({"document_type": "research_paper", "language": "en",
               "summary": "Placeholder — BE-5.", "raw_response": None})


@app.post("/internal/genai/verify-claim", tags=["Internal"])
def internal_genai_verify_claim(body: dict, db: Session = Depends(get_db)):
    """Core GenAI claim verification call. Implemented in BE-9."""
    return ok({"support_status": "SUPPORTED", "confidence_score": 0.87,
               "explanation": "Placeholder — BE-9.", "raw_response": None})


# ── Internal RAG ──────────────────────────────────────────────────────────────

@app.post("/internal/rag/check-semantic-cache", tags=["Internal"])
def internal_rag_check_semantic_cache(body: dict, db: Session = Depends(get_db)):
    """Check semantic cache for a similar claim verification."""
    return ok({"cache_hit": False, "similarity_score": None, "cached_result": None})


@app.post("/internal/rag/retrieve-evidence", tags=["Internal"])
def internal_rag_retrieve_evidence(body: dict, db: Session = Depends(get_db)):
    """Retrieve evidence chunks for a claim from the RAG index."""
    return ok({"chunks": [], "total": 0, "model_version": "text-embedding-3-small-v1"})
