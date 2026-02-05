"""
Structured application exception hierarchy.

Provides typed exceptions with consistent error codes, messages, details,
and header support (e.g., Retry-After) for API responses.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class BaseAppException(HTTPException):
    """
    Base exception for all application errors.

    Captures error_code, message, details, and optional headers
    for consistent API error responses. Inherits from FastAPI's
    HTTPException for framework compatibility.
    """

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize a structured application exception.

        Args:
            status_code: HTTP status code (e.g., 429, 503, 500)
            error_code: Machine-readable error type (e.g., "rate_limit_exceeded")
            message: Human-readable error message
            details: Additional context for debugging or client consumption
            headers: Optional HTTP headers (e.g., {"Retry-After": "60"})
        """
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.headers = headers or {}

        # Build detail dict for HTTPException compatibility
        detail = {
            "code": error_code,
            "message": message,
            "details": self.details,
        }

        super().__init__(
            status_code=status_code,
            detail=detail,
            headers=self.headers if self.headers else None,
        )

        # Log at creation for observability
        logger.warning(
            "app_exception",
            extra={
                "error_code": error_code,
                "message": message,
                "status_code": status_code,
                "details": self.details,
            },
        )

    def to_payload(self) -> Dict[str, Any]:
        """
        Convert exception to error payload for API response.

        Returns:
            Dict with structure: {"error": {"code": ..., "message": ..., "details": ...}}
        """
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            }
        }

    def __repr__(self) -> str:
        """Logging-friendly representation."""
        return (
            f"{self.__class__.__name__}("
            f"status_code={self.status_code}, "
            f"error_code={self.error_code!r}, "
            f"message={self.message!r}, "
            f"details={self.details!r})"
        )


class RateLimitException(BaseAppException):
    """
    Rate limit exceeded.

    Raised when request count exceeds configured rate limit window.
    Includes Retry-After header to indicate when client can retry.
    """

    def __init__(self, retry_after: int = 60, details: Optional[Dict[str, Any]] = None):
        """
        Initialize rate limit exception.

        Args:
            retry_after: Seconds until client can retry
            details: Additional context (e.g., current limit, window)
        """
        merged_details = {"retry_after": retry_after}
        if details:
            merged_details.update(details)

        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="rate_limit_exceeded",
            message="Too many requests. Please try again later.",
            details=merged_details,
            headers={"Retry-After": str(retry_after)},
        )


class ServiceUnavailableException(BaseAppException):
    """
    External service temporarily unavailable.

    Raised when dependency (e.g., Redis, database, external API) is down
    or circuit breaker is open. Includes Retry-After header.
    """

    def __init__(
        self,
        service: str,
        retry_after: int = 60,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize service unavailable exception.

        Args:
            service: Name of unavailable service (e.g., "rate_limiter", "database")
            retry_after: Seconds until client can retry
            details: Additional context (e.g., error message from service)
        """
        merged_details = {"service": service, "retry_after": retry_after}
        if details:
            merged_details.update(details)

        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="service_unavailable",
            message=f"{service} temporarily unavailable",
            details=merged_details,
            headers={"Retry-After": str(retry_after)},
        )


class DatabaseException(BaseAppException):
    """
    Database operation failed.

    Raised when database query, commit, or connection fails.
    Provides context for debugging without leaking internals to client.
    """

    def __init__(
        self,
        message: str = "Database operation failed",
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize database exception.

        Args:
            message: Human-readable description of failure
            details: Safe context (e.g., operation type, entity type)
                    DO NOT include sensitive data or raw SQL
        """
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="database_error",
            message=message,
            details=details,
        )
