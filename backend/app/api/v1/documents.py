from __future__ import annotations

from sqlalchemy import func
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppException, ErrorCode
from app.core.responses import success_response
from app.db.session import get_db
from app.models.enums import DoiStatus, MetadataStatus, SupportStatus
from app.models.workflow import Document, VerificationResult
from app.schemas.documents import TextSubmissionRequest
from app.services.reference_extraction import extract_references_for_document, list_document_references
from app.services.doi_metadata_lookup import MetadataLookupService
from app.services.document_processing_service import (
    create_text_document,
    create_uploaded_pdf_document,
    get_document,
    get_document_raw_text,
    get_document_sections,
    get_document_status,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/")
async def list_documents(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Return recently processed documents with their computed credibility scores."""
    docs = (
        db.query(Document)
        .filter(Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
        .limit(limit)
        .all()
    )

    counts_by_doc = (
        db.query(
            VerificationResult.document_id,
            VerificationResult.support_status,
            func.count(VerificationResult.id).label("cnt"),
        )
        .filter(
            VerificationResult.document_id.in_([d.id for d in docs]),
            VerificationResult.deleted_at.is_(None),
        )
        .group_by(VerificationResult.document_id, VerificationResult.support_status)
        .all()
    )

    status_map: dict[str, dict[str, int]] = {}
    for doc_id, status, cnt in counts_by_doc:
        status_map.setdefault(doc_id, {})[status] = cnt

    result = []
    for doc in docs:
        counts = status_map.get(doc.id, {})
        total = sum(counts.values())
        if total > 0:
            credibility_score = round(
                (
                    counts.get(SupportStatus.SUPPORTED.value, 0) * 1.0
                    + counts.get(SupportStatus.PARTIALLY_SUPPORTED.value, 0) * 0.5
                )
                / total
                * 100,
                1,
            )
        else:
            credibility_score = None

        result.append({
            "document_id": doc.id,
            "filename": doc.filename,
            "title": doc.title,
            "status": doc.status,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "claims_count": doc.claims_count,
            "credibility_score": credibility_score,
        })

    return success_response(request=request, data=result, message="Documents listed")


@router.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile | None = File(default=None),
    document_title: str | None = Form(default=None),
    uploaded_by: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    if file is None:
        raise AppException(
            status_code=400,
            code=ErrorCode.FILE_REQUIRED,
            field="file",
            detail="A PDF file is required for /documents/upload.",
            message="File is required",
        )
    data = await create_uploaded_pdf_document(
        file=file, document_title=document_title, uploaded_by=uploaded_by, settings=get_settings(), db=db
    )
    public_data = {
        "document_id": data["document_id"],
        "filename": data["filename"],
        "title": data["title"],
        "upload_type": data["upload_type"],
        "status": data["status"],
        "file_size_bytes": data["file_size_bytes"],
        "pages_count": data["pages_count"],
        "sections_count": data["sections_count"],
        "created_at": data["created_at"],
        "phase": data["phase"],
        "is_stub": data["is_stub"],
        "processing_note": data["processing_note"],
        "warnings": data.get("warnings", []),
    }
    return success_response(request=request, data=public_data, message="Document uploaded and text extracted")


@router.post("/text")
async def submit_document_text(request: Request, payload: TextSubmissionRequest, db: Session = Depends(get_db)):
    data = create_text_document(title=payload.title, text=payload.text, db=db)
    public_data = {
        "document_id": data["document_id"],
        "title": data["title"],
        "upload_type": data["upload_type"],
        "status": data["status"],
        "pages_count": data["pages_count"],
        "sections_count": data["sections_count"],
        "created_at": data["created_at"],
        "phase": data["phase"],
        "is_stub": data["is_stub"],
        "processing_note": data["processing_note"],
    }
    return success_response(request=request, data=public_data, message="Text document submitted and processed")


@router.get("/{document_id}")
async def document_metadata(request: Request, document_id: str, db: Session = Depends(get_db)):
    record = get_document(document_id, db)
    data = {
        "document_id": record["document_id"],
        "filename": record["filename"],
        "title": record["title"],
        "upload_type": record["upload_type"],
        "status": record["status"],
        "pages_count": record["pages_count"],
        "references_count": record["references_count"],
        "claims_count": record["claims_count"],
        "sections_count": record["sections_count"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "phase": record["phase"],
        "is_stub": record["is_stub"],
        "processing_note": record["processing_note"],
    }
    return success_response(request=request, data=data, message="Document metadata returned")


@router.get("/{document_id}/status")
async def document_status(request: Request, document_id: str, db: Session = Depends(get_db)):
    data = get_document_status(document_id, db)
    return success_response(request=request, data=data, message="Document status returned")


@router.get("/{document_id}/sections")
async def document_sections(
    request: Request,
    document_id: str,
    include_text: bool = Query(default=False, description="Include full section text for developer/debug inspection."),
    db: Session = Depends(get_db),
):
    data = get_document_sections(document_id, db, include_text=include_text)
    return success_response(request=request, data=data, message="Document sections returned")


@router.get("/{document_id}/raw-text")
async def document_raw_text(request: Request, document_id: str, db: Session = Depends(get_db)):
    data = get_document_raw_text(document_id, db, enabled=get_settings().enable_raw_text_debug_endpoint)
    return success_response(request=request, data=data, message="Document raw and cleaned text returned")


@router.post("/{document_id}/extract-references")
async def extract_document_references(request: Request, document_id: str, db: Session = Depends(get_db)):
    data = extract_references_for_document(
        document_id, db, request_id=getattr(request.state, "request_id", None)
    )
    return success_response(request=request, data=data, message="References and DOI values extracted")


@router.post("/{document_id}/verify-dois")
async def verify_document_dois(
    request: Request,
    document_id: str,
    force_refresh: bool = Query(default=False, description="Re-run the full lookup chain (CrossRef → OpenAlex → Unpaywall + PDF) even for already-cached DOIs."),
    db: Session = Depends(get_db),
):
    data = MetadataLookupService().verify_document_dois(
        document_id,
        db,
        request_id=getattr(request.state, "request_id", None),
        force_refresh=force_refresh,
    )
    return success_response(request=request, data=data, message="Document DOI metadata lookup completed")


@router.get("/{document_id}/references")
async def document_references(
    request: Request,
    document_id: str,
    doi_status: DoiStatus | None = Query(default=None, description="Optional DOI status filter, for example FOUND or MISSING."),
    metadata_status: MetadataStatus | None = Query(default=None, description="Optional metadata status filter, for example NOT_LOOKED_UP."),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    data = list_document_references(
        document_id,
        db,
        doi_status=doi_status.value if doi_status else None,
        metadata_status=metadata_status.value if metadata_status else None,
        page=page,
        page_size=page_size,
    )
    return success_response(request=request, data=data, message="Document references returned")
