"""Standard API response envelope for all `/api/v1` JSON endpoints."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorData(BaseModel):
    code: str
    errors: list[Any] | None = None


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    message: str
    data: T | None = None


def ok(data: T | None = None, message: str = "Success") -> ApiResponse[T]:
    return ApiResponse(success=True, message=message, data=data)


def fail(message: str, code: str, *, errors: list[Any] | None = None) -> ApiResponse[ErrorData]:
    return ApiResponse(
        success=False,
        message=message,
        data=ErrorData(code=code, errors=errors),
    )
