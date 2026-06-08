from __future__ import annotations

from enum import StrEnum

from app.schemas.common import ApiError


class ErrorCode(StrEnum):
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    FILE_REQUIRED = "FILE_REQUIRED"
    INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    PIPELINE_RUN_NOT_FOUND = "PIPELINE_RUN_NOT_FOUND"

    # BE-3 document upload and text-processing errors.
    PDF_READ_FAILED = "PDF_READ_FAILED"
    TEXT_REQUIRED = "TEXT_REQUIRED"
    TEXT_TOO_SHORT = "TEXT_TOO_SHORT"
    TEXT_EXTRACTION_FAILED = "TEXT_EXTRACTION_FAILED"
    SECTION_DETECTION_FAILED = "SECTION_DETECTION_FAILED"
    FILE_STORAGE_FAILED = "FILE_STORAGE_FAILED"

    # BE-4 reference and DOI extraction errors.
    DOCUMENT_TEXT_NOT_FOUND = "DOCUMENT_TEXT_NOT_FOUND"
    REFERENCE_SECTION_NOT_FOUND = "REFERENCE_SECTION_NOT_FOUND"
    REFERENCE_EXTRACTION_FAILED = "REFERENCE_EXTRACTION_FAILED"
    REFERENCE_NOT_FOUND = "REFERENCE_NOT_FOUND"
    DOI_MALFORMED = "DOI_MALFORMED"
    DEBUG_ENDPOINT_DISABLED = "DEBUG_ENDPOINT_DISABLED"
    REFERENCE_REEXTRACTION_BLOCKED = "REFERENCE_REEXTRACTION_BLOCKED"


class AppException(Exception):
    """Known application exception returned using the standard API wrapper."""

    def __init__(
        self,
        *,
        status_code: int = 400,
        code: ErrorCode = ErrorCode.INTERNAL_SERVER_ERROR,
        detail: str,
        field: str | None = None,
        message: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.error = ApiError(code=code.value, field=field, detail=detail)
        self.message = message or detail
        super().__init__(detail)
