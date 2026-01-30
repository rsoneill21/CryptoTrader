"""Helpers for recording audit trails around trading operations."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Iterable, Optional, Sequence

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive

from backend.core.tasks import log_system_event

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "x-request-id"
SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie"}

DEFAULT_AUDIT_PATHS = ("/api/trades", "/api/strategies")
DEFAULT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

def _parse_body(body: bytes) -> Optional[Any]:
    if not body:
        return None
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return str(body)


def _filter_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Return headers excluding entries that expose sensitive data."""
    sanitized: dict[str, str] = {}
    for name, value in headers:
        if name.lower() in SENSITIVE_HEADERS:
            continue
        sanitized[name] = value
    return sanitized


def _resolve_request_id(request: Request) -> str:
    """Use an incoming request ID header or generate a new identifier."""
    request_id = request.headers.get(REQUEST_ID_HEADER)
    return request_id or str(uuid.uuid4())


def _extract_actor(request: Request) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """Pull actor identifiers from the request state for logging."""
    user = getattr(request.state, "user", None)
    email = getattr(user, "email", None)
    user_id = getattr(user, "id", None)
    identifier: Optional[str]
    if email:
        identifier = email
    elif user_id is not None:
        identifier = f"user:{user_id}"
    else:
        identifier = None
    return identifier, email, user_id


def _log_to_python_logger(
    action: str,
    request_id: str,
    level: str,
    details: dict[str, Any],
) -> None:
    """Mirror structured audit events back into the Python logger for review."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    actor_identity = details.get("actor_email") or details.get("actor_id") or "system"
    message = (
        "Audit %s req=%s status=%s duration=%sms actor=%s"
        % (
            action,
            request_id,
            details.get("response_status"),
            details.get("duration_ms"),
            actor_identity,
        )
    )
    try:
        logger.log(numeric_level, message, extra={"audit": details})
    except Exception as exc:  # pragma: no cover - best effort logging
        logger.debug("Failed to emit audit log line: %s", exc)

def _replay_receive(body: bytes) -> Receive:
    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    return receive

def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    try:
        serialized = json.dumps(details, default=str)
        return json.loads(serialized)
    except (ValueError, TypeError) as exc:
        logger.debug("Failed to serialize audit details: %s", exc)
        return {"raw": str(details)}

def _determine_level(status_code: int, exc: Optional[Exception]) -> str:
    if exc:
        code = getattr(exc, "status_code", status_code)
        return "error" if code >= 500 else "warning"
    if status_code >= 500:
        return "error"
    if status_code >= 400:
        return "warning"
    return "info"

def log_audit_event(
    action: str,
    actor: Optional[str] = None,
    *,
    details: Optional[dict[str, Any]] = None,
    status_code: Optional[int] = None,
    success: bool = True,
    level: Optional[str] = None,
) -> None:
    """Record an audit event in the SystemLog table."""
    payload: dict[str, Any] = (details or {}).copy()
    payload.setdefault("action", action)
    payload.setdefault("actor", actor or "system")
    payload.setdefault("success", success)
    payload.setdefault("timestamp", datetime.utcnow().isoformat() + "Z")
    if status_code is not None:
        payload["status_code"] = status_code
    message = f"Audit {action}"
    computed_level = level or _determine_level(status_code or (500 if not success else 200), None)

    try:
        log_system_event.delay(computed_level, "audit", message, _sanitize_details(payload))
    except Exception as exc:  # pragma: no cover - best effort logging
        logger.warning("Unable to enqueue audit log: %s", exc)


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware that records state-changing trading requests for auditing."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        path_prefixes: Sequence[str] = DEFAULT_AUDIT_PATHS,
        methods: Iterable[str] = DEFAULT_METHODS,
    ) -> None:
        super().__init__(app)
        self._path_prefixes = tuple(prefix.rstrip("/") for prefix in path_prefixes)
        self._methods = {method.upper() for method in methods}

    def _should_record(self, request: Request) -> bool:
        if request.method.upper() not in self._methods:
            return False
        path = request.url.path.rstrip("/")
        return any(path.startswith(prefix) for prefix in self._path_prefixes)

    async def dispatch(self, request: Request, call_next):
        if not self._should_record(request):
            return await call_next(request)

        body_bytes = await request.body()
        request._receive = _replay_receive(body_bytes)
        parsed_body = _parse_body(body_bytes)
        response: Optional[Response] = None
        exc: Optional[Exception] = None
        request_id = _resolve_request_id(request)
        start_timestamp = datetime.utcnow().isoformat() + "Z"
        start_perf = time.perf_counter()

        try:
            response = await call_next(request)
            return response
        except Exception as error:  # pragma: no cover - allow upstream handlers to process
            exc = error
            raise
        finally:
            status_code = response.status_code if response else getattr(exc, "status_code", 500)
            duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)
            action = f"{request.method} {request.url.path}"
            actor_identifier, actor_email, actor_id = _extract_actor(request)
            response_headers = (
                _filter_headers(response.headers.items()) if response else {}
            )
            response_content_type = response.headers.get("content-type") if response else None
            response_content_length = response.headers.get("content-length") if response else None

            # Capture the sanitized request/response context used by both DB entries and logs.
            details: dict[str, Any] = {
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "start_timestamp": start_timestamp,
                "action": action,
                "path": request.url.path,
                "method": request.method,
                "query_params": dict(request.query_params),
                "request_headers": _filter_headers(request.headers.items()),
                "request_content_type": request.headers.get("content-type"),
                "request_size": len(body_bytes),
                "request_body": parsed_body,
                "client_ip": request.client.host if request.client else None,
                "client_port": request.client.port if request.client else None,
                "user_agent": request.headers.get("user-agent"),
                "actor_email": actor_email,
                "actor_id": actor_id,
                "response_status": status_code,
                "response_headers": response_headers,
                "response_content_type": response_content_type,
                "response_content_length": response_content_length,
                "response_detail": getattr(getattr(exc, "detail", None), "detail", None)
                if exc and hasattr(exc, "detail")
                else None,
                "duration_ms": duration_ms,
            }
            if exc:
                details["error_type"] = exc.__class__.__name__
                details["error_message"] = getattr(exc, "detail", str(exc))

            success = status_code < 400 and exc is None
            details["success"] = success
            level = _determine_level(status_code, exc)
            log_audit_event(
                details["action"],
                actor=actor_identifier,
                details=details,
                status_code=status_code,
                success=success,
                level=level,
            )
            # Mirror the structured details in the standard log stream for debugging.
            _log_to_python_logger(action, request_id, level, details)
