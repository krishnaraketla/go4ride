"""Map exceptions to the standard `{ success, message, data }` error envelope."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.schemas.response import fail


def _parse_http_detail(detail: Any) -> tuple[str, str, list[Any] | None]:
    if isinstance(detail, dict):
        if "code" in detail:
            message = detail.get("detail", detail.get("message", "Error"))
            if not isinstance(message, str):
                message = str(message)
            return message, str(detail["code"]), detail.get("errors")
        if "detail" in detail:
            message = detail["detail"]
            if not isinstance(message, str):
                message = str(message)
            return message, str(detail.get("code", "ERROR")), None
    return str(detail), "ERROR", None


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        message, code, errors = _parse_http_detail(exc.detail)
        body = fail(message, code, errors=errors)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc, AppError):
            raise exc
        message, code, errors = _parse_http_detail(exc.detail)
        body = fail(message, code, errors=errors)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        body = fail("Validation error", "VALIDATION_ERROR", errors=exc.errors())
        return JSONResponse(status_code=422, content=body.model_dump())
