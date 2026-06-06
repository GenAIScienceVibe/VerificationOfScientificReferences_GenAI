from __future__ import annotations

from pydantic import BaseModel, Field


class TextSubmissionRequest(BaseModel):
    title: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)


class DocumentUploadData(BaseModel):
    document_id: str
    filename: str
    upload_type: str
    status: str
    file_size_bytes: int
    created_at: str
    phase: str = "BE-1"
    is_stub: bool = True
    stub_note: str


class DocumentTextData(BaseModel):
    document_id: str
    title: str
    upload_type: str
    status: str
    created_at: str
    phase: str = "BE-1"
    is_stub: bool = True
    stub_note: str


class DocumentMetadataData(BaseModel):
    document_id: str
    filename: str
    title: str
    upload_type: str
    status: str
    pages_count: int
    references_count: int
    claims_count: int
    created_at: str
    updated_at: str
    phase: str = "BE-1"
    is_stub: bool = True
    stub_note: str


class DocumentStatusData(BaseModel):
    document_id: str
    status: str
    frontend_status: str
    progress_percentage: int
    current_step: str
    latest_pipeline_run_id: str
    phase: str = "BE-1"
    is_stub: bool = True
    stub_note: str
