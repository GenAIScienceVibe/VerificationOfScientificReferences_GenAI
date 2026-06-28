from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppException, ErrorCode
from app.core.responses import success_response
from app.db.session import get_db
from app.services.doi_metadata_lookup import MetadataLookupService
from app.services.reference_extraction import get_reference

router = APIRouter(prefix="/references", tags=["references"])


@router.get("/{reference_id}")
async def reference_details(request: Request, reference_id: str, db: Session = Depends(get_db)):
    data = get_reference(reference_id, db)
    return success_response(request=request, data=data, message="Reference details returned")


@router.post("/{reference_id}/verify-doi")
async def verify_reference_doi(request: Request, reference_id: str, db: Session = Depends(get_db)):
    data = MetadataLookupService().verify_reference_doi(
        reference_id,
        db,
        request_id=getattr(request.state, "request_id", None),
    )
    return success_response(request=request, data=data, message="Reference DOI metadata lookup completed")


@router.get("/{reference_id}/metadata")
async def reference_metadata(request: Request, reference_id: str, db: Session = Depends(get_db)):
    data = MetadataLookupService().get_reference_metadata(reference_id, db)
    return success_response(request=request, data=data, message="Reference metadata returned")


@router.post("/{reference_id}/upload-source-pdf")
async def upload_source_pdf(
    request: Request,
    reference_id: str,
    file: UploadFile = File(..., description="PDF of the cited source paper (e.g. from institutional access)."),
    db: Session = Depends(get_db),
):
    """Upload a PDF for a paywalled reference so its full text can be used for verification.

    After uploading, run POST /documents/{document_id}/prepare-evidence to rebuild
    the evidence packages — the reference will then show FULL_TEXT_AVAILABLE.
    """
    settings = get_settings()
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise AppException(
            status_code=400,
            code=ErrorCode.FILE_REQUIRED,
            field="file",
            detail="Only PDF files are accepted.",
            message="Invalid file type",
        )
    pdf_bytes = await file.read()
    if len(pdf_bytes) > settings.fulltext_max_bytes:
        raise AppException(
            status_code=413,
            code=ErrorCode.FILE_REQUIRED,
            field="file",
            detail=f"File exceeds the maximum allowed size of {settings.fulltext_max_bytes // (1024 * 1024)} MB.",
            message="File too large",
        )
    data = MetadataLookupService().inject_fulltext_from_uploaded_pdf(
        reference_id=reference_id,
        pdf_bytes=pdf_bytes,
        filename=file.filename,
        db=db,
    )
    return success_response(request=request, data=data, message="Source PDF uploaded and full text extracted")
