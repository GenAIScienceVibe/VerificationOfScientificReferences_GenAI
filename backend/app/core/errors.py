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


class AppException(Exception):
    """Known application exception that should be returned using the standard API wrapper."""

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
