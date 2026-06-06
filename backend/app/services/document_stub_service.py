from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppException, ErrorCode
from app.models import Document
from app.models.enums import DocumentStatus, UploadType
from app.repositories import DocumentRepository


def _safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", filename).strip("._")
    return cleaned or "uploaded_document.pdf"


def _stub_note() -> str:
    return (
        "BE-2 database-backed stub only. Full extraction, DOI lookup, claims, RAG, GenAI, verification, "
        "reports, and feedback are deferred to later phases."
    )


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(value)


def document_to_dict(document: Document) -> dict[str, Any]:
    return {
        "document_id": document.id,
        "filename": document.filename,
        "title": document.title,
        "upload_type": document.upload_type,
        "status": document.status,
        "file_size_bytes": document.file_size_bytes or 0,
        "pages_count": document.pages_count,
        "references_count": document.references_count,
        "claims_count": document.claims_count,
        "latest_pipeline_run_id": document.latest_pipeline_run_id or "not_started_be2_db_stub",
        "created_at": _iso(document.created_at),
        "updated_at": _iso(document.updated_at),
        "phase": "BE-2",
        "is_stub": True,
        "stub_note": _stub_note(),
    }


async def create_upload_document(
    *, file: UploadFile, document_title: str | None, uploaded_by: str | None, settings: Settings, db: Session
) -> dict[str, Any]:
    filename = file.filename or "uploaded_document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise AppException(
            status_code=415,
            code=ErrorCode.INVALID_FILE_TYPE,
            field="file",
            detail="Only PDF files are supported in the BE-2 upload stub.",
            message="Invalid file type",
        )

    content = await file.read()
    file_size_bytes = len(content)
    if file_size_bytes > settings.max_upload_size_bytes:
        raise AppException(
            status_code=413,
            code=ErrorCode.FILE_TOO_LARGE,
            field="file",
            detail=f"Uploaded file is larger than the configured limit of {settings.max_upload_size_bytes} bytes.",
            message="Uploaded file is too large",
        )

    safe_filename = _safe_filename(filename)
    settings.file_storage_dir.mkdir(parents=True, exist_ok=True)

    # Create the Document first so the stable string id is used in the storage path.
    repo = DocumentRepository(db)
    document = repo.create(
        filename=filename,
        title=document_title or Path(filename).stem,
        upload_type=UploadType.PDF.value,
        status=DocumentStatus.UPLOADED.value,
        file_size_bytes=file_size_bytes,
        commit=True,
    )
    storage_path = settings.file_storage_dir / f"{document.id}_{safe_filename}"
    storage_path.write_bytes(content)
    document.file_storage_path = str(storage_path)
    db.commit()
    db.refresh(document)
    return document_to_dict(document) | {"uploaded_by": uploaded_by}


def create_text_document(*, title: str, text: str, db: Session) -> dict[str, Any]:
    repo = DocumentRepository(db)
    document = repo.create(
        filename="submitted_text.txt",
        title=title,
        upload_type=UploadType.TEXT.value,
        status=DocumentStatus.UPLOADED.value,
        file_size_bytes=len(text.encode("utf-8")),
        raw_text=text,
        cleaned_text=text,
        commit=True,
    )
    return document_to_dict(document) | {"text_size_chars": len(text)}


def get_document(document_id: str, db: Session) -> dict[str, Any]:
    document = DocumentRepository(db).get(document_id)
    if not document:
        raise AppException(
            status_code=404,
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            field="document_id",
            detail=f"Document '{document_id}' was not found in the BE-2 database.",
            message="Document not found",
        )
    return document_to_dict(document)


def get_document_status(document_id: str, db: Session) -> dict[str, Any]:
    record = get_document(document_id, db)
    return {
        "document_id": record["document_id"],
        "status": record["status"],
        "frontend_status": "Uploaded / stored in BE-2 database stub",
        "progress_percentage": 0,
        "current_step": "Database record created; BE-3 document processing has not run yet.",
        "latest_pipeline_run_id": record["latest_pipeline_run_id"],
        "phase": "BE-2",
        "is_stub": True,
        "stub_note": _stub_note(),
    }
