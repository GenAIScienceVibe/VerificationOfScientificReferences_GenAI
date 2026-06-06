from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppException, ErrorCode
from app.core.responses import success_response
from app.db.session import get_db
from app.schemas.documents import TextSubmissionRequest
from app.services.document_stub_service import create_text_document, create_upload_document, get_document, get_document_status

router = APIRouter(prefix="/documents", tags=["documents"])


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
    record = await create_upload_document(
        file=file, document_title=document_title, uploaded_by=uploaded_by, settings=get_settings(), db=db
    )
    data = {
        "document_id": record["document_id"],
        "filename": record["filename"],
        "upload_type": record["upload_type"],
        "status": record["status"],
        "file_size_bytes": record["file_size_bytes"],
        "created_at": record["created_at"],
        "phase": record["phase"],
        "is_stub": record["is_stub"],
        "stub_note": record["stub_note"],
    }
    return success_response(request=request, data=data, message="Document upload stored by BE-2 database stub")


@router.post("/text")
async def submit_document_text(request: Request, payload: TextSubmissionRequest, db: Session = Depends(get_db)):
    record = create_text_document(title=payload.title, text=payload.text, db=db)
    data = {
        "document_id": record["document_id"],
        "title": record["title"],
        "upload_type": record["upload_type"],
        "status": record["status"],
        "created_at": record["created_at"],
        "phase": record["phase"],
        "is_stub": record["is_stub"],
        "stub_note": record["stub_note"],
    }
    return success_response(request=request, data=data, message="Text submission stored by BE-2 database stub")


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
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "phase": record["phase"],
        "is_stub": record["is_stub"],
        "stub_note": record["stub_note"],
    }
    return success_response(request=request, data=data, message="Document metadata returned from BE-2 database stub")


@router.get("/{document_id}/status")
async def document_status(request: Request, document_id: str, db: Session = Depends(get_db)):
    data = get_document_status(document_id, db)
    return success_response(request=request, data=data, message="Document status returned from BE-2 database stub")
