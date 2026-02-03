"""Shared API error models and formatting helpers."""

from __future__ import annotations

from http import HTTPStatus
import logging
from typing import Any, Mapping, Optional, Sequence, Union

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class APIErrorDetail(BaseModel):
    """Structured payload embedded in every API error response."""

    code: str
    message: str
    details: Optional[Any] = None


class APIErrorResponse(BaseModel):
    """Wrapper returned by the centralized error handlers."""

    error: APIErrorDetail


def _default_message(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "An error occurred while processing the request."


def _format_message(detail: Union[str, Mapping[str, Any], Sequence[Any], None]) -> Optional[str]:
    if isinstance(detail, str):
        return detail

    if isinstance(detail, Mapping):
        return detail.get("message") or detail.get("detail")

    if isinstance(detail, Sequence) and not isinstance(detail, (str, bytes)):
        text_segments = [str(item.get("msg") if isinstance(item, Mapping) else item) for item in detail]
        return "; ".join([segment for segment in text_segments if segment])

    return None


def _format_code(
    detail: Union[str, Mapping[str, Any], Sequence[Any], None],
    default_code: Optional[str] = None,
) -> str:
    if isinstance(detail, Mapping):
        if detail.get("code"):
            return detail["code"]
        if detail.get("error_code"):
            return detail["error_code"]
    if isinstance(detail, str):
        normalized = detail.strip().lower()
        if "email already registered" in normalized:
            return "duplicate_email"
    if default_code:
        return default_code
    return "http_error"


def build_error_payload(
    status_code: int,
    detail: Union[str, Mapping[str, Any], Sequence[Any], None] = None,
    default_code: Optional[str] = None,
) -> APIErrorResponse:
    """Create a consistent API error response from the provided detail."""

    message = _format_message(detail) or _default_message(status_code)
    code = _format_code(detail, default_code or f"http_{status_code}")
    details = None

    if isinstance(detail, Mapping) and detail.get("details") is not None:
        details = detail["details"]
    elif isinstance(detail, Sequence) and not isinstance(detail, (str, bytes)):
        details = detail

    return APIErrorResponse(
        error=APIErrorDetail(
            code=code,
            message=message,
            details=details,
        )
    )


def build_validation_error_payload(exc: RequestValidationError) -> APIErrorResponse:
    """Generate an error response that exposes validation failures."""

    errors = exc.errors()
    summary = "Validation failed"
    if errors:
        first_msg = errors[0].get("msg")
        if first_msg:
            summary = first_msg

    return APIErrorResponse(
        error=APIErrorDetail(
            code="validation_error",
            message=summary,
            details=errors,
        )
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """FastAPI exception handler for HTTPException instances."""

    payload = build_error_payload(exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """FastAPI handler for request validation failures."""

    payload = build_validation_error_payload(exc)
    return JSONResponse(status_code=422, content=payload.model_dump())


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler to keep the error format consistent."""

    logger.exception("Unhandled exception for %s %s", request.method, request.url, exc=exc)
    payload = build_error_payload(500, None, default_code="unexpected_error")
    return JSONResponse(status_code=500, content=payload.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    """Register the structured error handlers on the FastAPI app."""

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
