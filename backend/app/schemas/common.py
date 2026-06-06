from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiError(BaseModel):
    code: str = Field(..., description="Machine-readable error code.")
    field: str | None = Field(default=None, description="Request field related to the error, if applicable.")
    detail: str = Field(..., description="Human-readable error detail.")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None
    message: str
    errors: list[ApiError]
    request_id: str


class EmptyData(BaseModel):
    pass


JsonDict = dict[str, Any]
