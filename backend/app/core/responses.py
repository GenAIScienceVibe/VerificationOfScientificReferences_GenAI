from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas.common import ApiError


def get_request_id(request: Request | None) -> str:
    if request is not None and hasattr(request.state, "request_id"):
        return str(request.state.request_id)
    return "req_unavailable"


def success_response(
    *,
    request: Request,
    data: Any,
    message: str = "Request completed successfully",
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
            "message": message,
            "errors": [],
            "request_id": get_request_id(request),
        },
    )


def error_response(
    *,
    request: Request | None,
    message: str,
    errors: list[ApiError],
    status_code: int,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "data": None,
            "message": message,
            "errors": [error.model_dump() for error in errors],
            "request_id": get_request_id(request),
        },
    )
