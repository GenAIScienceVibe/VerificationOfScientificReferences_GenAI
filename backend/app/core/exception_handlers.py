from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppException, ErrorCode
from app.core.responses import error_response
from app.schemas.common import ApiError

logger = logging.getLogger("app.errors")


def _field_from_location(location: tuple[object, ...]) -> str | None:
    filtered = [str(item) for item in location if item not in ("body", "query", "path", "header", "file")]
    if filtered:
        return ".".join(filtered)
    return str(location[-1]) if location else None


async def app_exception_handler(request: Request, exc: AppException):
    logger.warning(
        "application_error",
        extra={
            "request_id": getattr(request.state, "request_id", "req_unavailable"),
            "error_code": exc.error.code,
            "error_detail": exc.error.detail,
        },
    )
    return error_response(request=request, message=exc.message, errors=[exc.error], status_code=exc.status_code)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        ApiError(
            code=ErrorCode.VALIDATION_ERROR.value,
            field=_field_from_location(tuple(error.get("loc", ()))),
            detail=str(error.get("msg", "Validation error")),
        )
        for error in exc.errors()
    ]
    return error_response(request=request, message="Validation failed", errors=errors, status_code=422)


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = ErrorCode.VALIDATION_ERROR.value if exc.status_code < 500 else ErrorCode.INTERNAL_SERVER_ERROR.value
    detail = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    return error_response(
        request=request,
        message=detail,
        errors=[ApiError(code=code, field=None, detail=detail)],
        status_code=exc.status_code,
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "unhandled_error",
        extra={
            "request_id": getattr(request.state, "request_id", "req_unavailable"),
            "error_code": ErrorCode.INTERNAL_SERVER_ERROR.value,
            "error_detail": str(exc),
        },
    )
    return error_response(
        request=request,
        message="Internal server error",
        errors=[
            ApiError(
                code=ErrorCode.INTERNAL_SERVER_ERROR.value,
                field=None,
                detail="An unexpected backend error occurred.",
            )
        ],
        status_code=500,
    )
