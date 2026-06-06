from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import AppException, ErrorCode

_DOCUMENTS: dict[str, dict[str, Any]] = {}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _new_document_id() -> str:
    return f"doc_{uuid.uuid4().hex[:12]}"


def _safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", filename).strip("._")
    return cleaned or "uploaded_document.pdf"


def _stub_note() -> str:
    return "BE-1 stub only. Full extraction, DOI lookup, claims, RAG, GenAI, verification, reports, and feedback are deferred to later phases."


async def create_upload_document(*, file: UploadFile, document_title: str | None, uploaded_by: str | None, settings: Settings) -> dict[str, Any]:
    filename = file.filename or "uploaded_document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise AppException(
            status_code=415,
            code=ErrorCode.INVALID_FILE_TYPE,
            field="file",
            detail="Only PDF files are supported in the BE-1 upload stub.",
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

    document_id = _new_document_id()
    created_at = utc_now_iso()
    safe_filename = _safe_filename(filename)
    settings.file_storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = settings.file_storage_dir / f"{document_id}_{safe_filename}"
    storage_path.write_bytes(content)

    record = {
        "document_id": document_id,
        "filename": filename,
        "title": document_title or Path(filename).stem,
        "upload_type": "PDF_UPLOAD",
        "status": "QUEUED",
        "file_size_bytes": file_size_bytes,
        "pages_count": 0,
        "references_count": 0,
        "claims_count": 0,
        "created_at": created_at,
        "updated_at": created_at,
        "uploaded_by": uploaded_by,
        "storage_path": str(storage_path),
        "phase": "BE-1",
        "is_stub": True,
        "stub_note": _stub_note(),
    }
    _DOCUMENTS[document_id] = record
    return record


def create_text_document(*, title: str, text: str) -> dict[str, Any]:
    document_id = _new_document_id()
    created_at = utc_now_iso()
    record = {
        "document_id": document_id,
        "filename": "submitted_text.txt",
        "title": title,
        "upload_type": "TEXT_SUBMISSION",
        "status": "QUEUED",
        "text_size_chars": len(text),
        "pages_count": 0,
        "references_count": 0,
        "claims_count": 0,
        "created_at": created_at,
        "updated_at": created_at,
        "phase": "BE-1",
        "is_stub": True,
        "stub_note": _stub_note(),
    }
    _DOCUMENTS[document_id] = record
    return record


def get_document(document_id: str) -> dict[str, Any]:
    record = _DOCUMENTS.get(document_id)
    if not record:
        raise AppException(
            status_code=404,
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            field="document_id",
            detail=f"Document '{document_id}' was not found in the BE-1 in-memory stub store.",
            message="Document not found",
        )
    return record


def get_document_status(document_id: str) -> dict[str, Any]:
    record = get_document(document_id)
    return {
        "document_id": record["document_id"],
        "status": record["status"],
        "frontend_status": "Uploaded / queued in BE-1 stub",
        "progress_percentage": 0,
        "current_step": "Backend foundation stub created; BE-3 document processing has not run yet.",
        "latest_pipeline_run_id": "not_started_be1_stub",
        "phase": "BE-1",
        "is_stub": True,
        "stub_note": _stub_note(),
    }
