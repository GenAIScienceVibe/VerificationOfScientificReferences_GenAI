from __future__ import annotations

from pydantic import BaseModel, Field


class TextSubmissionRequest(BaseModel):
    """Plain text document submission.

    Validation is intentionally completed in the BE-3 service so the backend can
    return stable project-specific error codes such as TEXT_REQUIRED and
    TEXT_TOO_SHORT instead of only framework validation messages.
    """

    title: str | None = Field(default=None, max_length=512)
    text: str = Field(...)


class DocumentUploadData(BaseModel):
    document_id: str
    filename: str
    title: str | None = None
    upload_type: str
    status: str
    file_size_bytes: int
    pages_count: int = 0
    sections_count: int = 0
    created_at: str
    phase: str = "BE-3"
    is_stub: bool = False
    processing_note: str


class DocumentTextData(BaseModel):
    document_id: str
    title: str | None
    upload_type: str
    status: str
    pages_count: int
    sections_count: int
    created_at: str
    phase: str = "BE-3"
    is_stub: bool = False
    processing_note: str


class DocumentMetadataData(BaseModel):
    document_id: str
    filename: str
    title: str | None
    upload_type: str
    status: str
    pages_count: int
    references_count: int
    claims_count: int
    created_at: str
    updated_at: str
    phase: str = "BE-3"
    is_stub: bool = False
    processing_note: str


class DocumentStatusData(BaseModel):
    document_id: str
    status: str
    frontend_status: str
    progress_percentage: int
    current_step: str
    latest_pipeline_run_id: str | None = None
    phase: str = "BE-3"
    is_stub: bool = False
    processing_note: str


class DocumentSectionData(BaseModel):
    section_id: str
    name: str
    order_index: int
    text_preview: str | None = None
    text: str | None = None
    page_start: int | None = None
    page_end: int | None = None


class DocumentSectionsResponseData(BaseModel):
    document_id: str
    sections: list[DocumentSectionData]


class DocumentRawTextData(BaseModel):
    document_id: str
    raw_text: str | None = None
    cleaned_text: str | None = None
    pages_count: int
    phase: str = "BE-3"
    debug_note: str
