from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppException, ErrorCode
from app.models import Document, DocumentSection
from app.models.enums import DocumentStatus, UploadType
from app.repositories import DocumentRepository, DocumentSectionRepository
from app.services.pdf_text_extraction import PdfTextExtractionService
from app.services.text_processing import clean_text, detect_basic_sections

MIN_TEXT_CHARS = 20
_ALLOWED_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream", ""}


def _safe_original_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", filename).strip("._")
    return cleaned or "uploaded_document.pdf"


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(value)


def _processing_note() -> str:
    return (
        "BE-3 document upload and text processing is implemented. Reference extraction, DOI lookup, claims, "
        "RAG, GenAI verification, reports, and feedback are deferred to later backend phases."
    )


def _status_progress(status: str, section_count: int = 0) -> tuple[str, int, str]:
    if status == DocumentStatus.REFERENCES_EXTRACTED.value:
        return "References extracted and ready for DOI metadata lookup", 45, "REFERENCES_EXTRACTED"
    if status == DocumentStatus.REFERENCES_EXTRACTING.value:
        return "Reference extraction in progress", 40, "REFERENCES_EXTRACTING"
    if status == DocumentStatus.TEXT_EXTRACTED.value:
        return "Text extracted and ready for reference extraction", 30, "COMPLETED" if section_count else "TEXT_EXTRACTION"
    if status == DocumentStatus.TEXT_EXTRACTING.value:
        return "Text extraction in progress", 15, "TEXT_EXTRACTION"
    if status == DocumentStatus.PARTIAL_FAILED.value:
        return "Processing partially completed with warnings", 25, "PARTIAL_FAILED"
    if status == DocumentStatus.FAILED.value:
        return "Document processing failed", 0, "FAILED"
    return "Document uploaded", 10, "UPLOAD"


def document_to_dict(document: Document, *, include_processing_note: bool = True) -> dict[str, Any]:
    sections_count = len(document.sections) if getattr(document, "sections", None) is not None else 0
    data = {
        "document_id": document.id,
        "filename": document.filename,
        "title": document.title,
        "upload_type": document.upload_type,
        "status": document.status,
        "file_size_bytes": document.file_size_bytes or 0,
        "pages_count": document.pages_count,
        "references_count": document.references_count,
        "claims_count": document.claims_count,
        "sections_count": sections_count,
        "latest_pipeline_run_id": document.latest_pipeline_run_id,
        "created_at": _iso(document.created_at),
        "updated_at": _iso(document.updated_at),
        "phase": "BE-3",
        "is_stub": False,
    }
    if include_processing_note:
        data["processing_note"] = _processing_note()
    return data


def section_to_dict(section: DocumentSection, *, include_text: bool = False) -> dict[str, Any]:
    data = {
        "section_id": section.id,
        "name": section.name,
        "order_index": section.order_index,
        "text_preview": section.text_preview,
        "page_start": section.page_start,
        "page_end": section.page_end,
    }
    if include_text:
        data["text"] = section.text
    return data


def _validate_text(text: str) -> str:
    if text is None or not text.strip():
        raise AppException(
            status_code=400,
            code=ErrorCode.TEXT_REQUIRED,
            field="text",
            detail="Document text is required.",
            message="Text is required",
        )
    stripped = text.strip()
    if len(stripped) < MIN_TEXT_CHARS:
        raise AppException(
            status_code=400,
            code=ErrorCode.TEXT_TOO_SHORT,
            field="text",
            detail=f"Document text must contain at least {MIN_TEXT_CHARS} non-whitespace characters for BE-3 processing.",
            message="Text is too short",
        )
    return stripped


def _persist_sections(*, document_id: str, cleaned_text: str, db: Session) -> list[DocumentSection]:
    try:
        detected = detect_basic_sections(cleaned_text)
        section_payloads = [
            {
                "name": section.name,
                "order_index": section.order_index,
                "text": section.text,
                "text_preview": section.text_preview,
                "page_start": section.page_start,
                "page_end": section.page_end,
            }
            for section in detected
        ]
        return DocumentSectionRepository(db).replace_for_document(document_id=document_id, sections=section_payloads, commit=True)
    except AppException:
        raise
    except Exception as exc:
        raise AppException(
            status_code=500,
            code=ErrorCode.SECTION_DETECTION_FAILED,
            field=None,
            detail="Basic section detection failed while processing the document.",
            message="Section detection failed",
        ) from exc


def _validate_pdf_upload(file: UploadFile, content: bytes, settings: Settings) -> str:
    filename = file.filename or "uploaded_document.pdf"
    safe_name = _safe_original_filename(filename)
    if not safe_name.lower().endswith(".pdf"):
        raise AppException(
            status_code=415,
            code=ErrorCode.INVALID_FILE_TYPE,
            field="file",
            detail="Only PDF files are supported by /documents/upload in BE-3.",
            message="Invalid file type",
        )
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_PDF_CONTENT_TYPES:
        raise AppException(
            status_code=415,
            code=ErrorCode.INVALID_FILE_TYPE,
            field="file",
            detail="The uploaded file must use a PDF content type.",
            message="Invalid file type",
        )
    if not content:
        raise AppException(
            status_code=400,
            code=ErrorCode.FILE_REQUIRED,
            field="file",
            detail="A non-empty PDF file is required.",
            message="File is required",
        )
    if len(content) > settings.max_upload_size_bytes:
        raise AppException(
            status_code=413,
            code=ErrorCode.FILE_TOO_LARGE,
            field="file",
            detail=f"Uploaded file is larger than the configured limit of {settings.max_upload_size_bytes} bytes.",
            message="Uploaded file is too large",
        )
    return safe_name


async def create_uploaded_pdf_document(
    *, file: UploadFile, document_title: str | None, uploaded_by: str | None, settings: Settings, db: Session
) -> dict[str, Any]:
    content = await file.read()
    safe_original_name = _validate_pdf_upload(file=file, content=content, settings=settings)
    settings.file_storage_dir.mkdir(parents=True, exist_ok=True)

    repo = DocumentRepository(db)
    document = repo.create(
        filename=file.filename or safe_original_name,
        title=document_title or Path(safe_original_name).stem,
        upload_type=UploadType.PDF.value,
        status=DocumentStatus.UPLOADED.value,
        file_size_bytes=len(content),
        commit=True,
    )

    storage_path = settings.file_storage_dir / f"{document.id}.pdf"
    try:
        storage_path.write_bytes(content)
    except Exception as exc:
        document.status = DocumentStatus.FAILED.value
        db.commit()
        raise AppException(
            status_code=500,
            code=ErrorCode.FILE_STORAGE_FAILED,
            field="file",
            detail="Uploaded file could not be saved to backend storage.",
            message="File storage failed",
        ) from exc

    document.file_storage_path = str(storage_path)
    document.status = DocumentStatus.TEXT_EXTRACTING.value
    db.commit()
    db.refresh(document)

    try:
        extraction_result = PdfTextExtractionService().extract(storage_path)
        cleaned = clean_text(extraction_result.raw_text)
        sections = _persist_sections(document_id=document.id, cleaned_text=cleaned, db=db)
        document.raw_text = extraction_result.raw_text
        document.cleaned_text = cleaned
        document.pages_count = extraction_result.pages_count
        document.status = DocumentStatus.TEXT_EXTRACTED.value
        db.commit()
        db.refresh(document)
    except AppException as exc:
        document.status = DocumentStatus.FAILED.value
        db.commit()
        # Keep the saved file and failed DB record for audit/debug, but return standard error wrapper.
        raise exc

    data = document_to_dict(document)
    data.update(
        {
            "sections_count": len(sections),
            "uploaded_by": uploaded_by,
            "warnings": extraction_result.warnings,
        }
    )
    return data


def create_text_document(*, title: str | None, text: str, db: Session) -> dict[str, Any]:
    raw_text = _validate_text(text)
    cleaned = clean_text(raw_text)
    if len(cleaned) < MIN_TEXT_CHARS:
        raise AppException(
            status_code=400,
            code=ErrorCode.TEXT_TOO_SHORT,
            field="text",
            detail=f"Cleaned document text must contain at least {MIN_TEXT_CHARS} characters.",
            message="Text is too short",
        )

    repo = DocumentRepository(db)
    document = repo.create(
        filename="submitted_text.txt",
        title=title.strip() if title and title.strip() else "Submitted Text Document",
        upload_type=UploadType.TEXT.value,
        status=DocumentStatus.UPLOADED.value,
        file_size_bytes=len(raw_text.encode("utf-8")),
        raw_text=raw_text,
        cleaned_text=cleaned,
        pages_count=0,
        commit=True,
    )
    sections = _persist_sections(document_id=document.id, cleaned_text=cleaned, db=db)
    document.status = DocumentStatus.TEXT_EXTRACTED.value
    db.commit()
    db.refresh(document)
    data = document_to_dict(document)
    data.update({"sections_count": len(sections), "text_size_chars": len(raw_text)})
    return data


def get_document_or_raise(document_id: str, db: Session) -> Document:
    document = DocumentRepository(db).get_with_sections(document_id)
    if not document:
        raise AppException(
            status_code=404,
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            field="document_id",
            detail=f"Document '{document_id}' was not found.",
            message="Document not found",
        )
    return document


def get_document(document_id: str, db: Session) -> dict[str, Any]:
    document = get_document_or_raise(document_id, db)
    return document_to_dict(document)


def get_document_status(document_id: str, db: Session) -> dict[str, Any]:
    document = get_document_or_raise(document_id, db)
    frontend_status, progress_percentage, current_step = _status_progress(document.status, len(document.sections))
    return {
        "document_id": document.id,
        "status": document.status,
        "frontend_status": frontend_status,
        "progress_percentage": progress_percentage,
        "current_step": current_step,
        "latest_pipeline_run_id": document.latest_pipeline_run_id,
        "phase": "BE-3",
        "is_stub": False,
        "processing_note": _processing_note(),
    }


def get_document_sections(document_id: str, db: Session, *, include_text: bool = False) -> dict[str, Any]:
    get_document_or_raise(document_id, db)
    sections = DocumentSectionRepository(db).list_for_document(document_id)
    return {
        "document_id": document_id,
        "sections": [section_to_dict(section, include_text=include_text) for section in sections],
        "phase": "BE-3",
        "processing_note": "Sections are broad BE-3 sections only. Individual reference extraction belongs to BE-4.",
    }


def get_document_raw_text(document_id: str, db: Session) -> dict[str, Any]:
    document = get_document_or_raise(document_id, db)
    return {
        "document_id": document.id,
        "raw_text": document.raw_text,
        "cleaned_text": document.cleaned_text,
        "pages_count": document.pages_count,
        "phase": "BE-3",
        "debug_note": "Developer/debug endpoint. Do not use this as a public document download endpoint.",
    }
