"""
System API routes.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, List

from datetime import datetime
from fastapi import APIRouter, Query, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.settings import get_app_settings
from db.database import (
    get_async_db,
    backup_sqlite_database,
    list_sqlite_backups,
    restore_sqlite_database,
    log_system_error,
)
from db.models import SystemLog, User
from services.kraken import kraken_service, KrakenAPIError
from core.exceptions import ServiceUnavailableException

router = APIRouter()
logger = logging.getLogger("cryptotrader.system")


def _log_backup_event(
    level: str,
    operation: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
) -> None:
    payload = {"operation": operation}
    if details:
        payload.update(details)
    log_system_error(level, "system.backups", message, payload)


def _raise_dependency_unavailable(
    *,
    endpoint: str,
    dependency: str,
    operation: str,
    exc: Exception,
    log_event: Optional[str] = None,
    extra_details: Optional[Dict[str, Any]] = None,
    retry_after: int = 60,
) -> None:
    """Log a dependency outage and raise ServiceUnavailableException."""
    context: Dict[str, Any] = {
        "endpoint": endpoint,
        "dependency": dependency,
        "operation": operation,
    }
    if extra_details:
        context.update(extra_details)
    logger.error(
        log_event or f"system.{endpoint}.{dependency}_unavailable",
        extra=context,
        exc_info=True,
    )
    detail_payload = {**context, "error": str(exc), "error_type": exc.__class__.__name__}
    raise ServiceUnavailableException(
        service=dependency,
        retry_after=retry_after,
        endpoint=endpoint,
        dependency=dependency,
        operation=operation,
        details=detail_payload,
    ) from exc


async def _probe_kraken_latency(*, endpoint: str):
    """Ping Kraken to calculate latency and raise typed errors on failure."""
    loop = asyncio.get_running_loop()
    start_time = loop.time()
    operation = "kraken.get_server_time"
    try:
        await kraken_service.get_server_time()
        elapsed_ms = (loop.time() - start_time) * 1000
        return KrakenConnectionStatus(
            authenticated=True,
            reachable=True,
            latency_ms=round(elapsed_ms, 1),
        )
    except KrakenAPIError as exc:
        extra_details = {"kraken_errors": getattr(exc, "errors", [])}
        _raise_dependency_unavailable(
            endpoint=endpoint,
            dependency="kraken",
            operation=operation,
            exc=exc,
            log_event=f"system.{endpoint}.kraken_api_error",
            extra_details=extra_details,
        )
    except Exception as exc:
        _raise_dependency_unavailable(
            endpoint=endpoint,
            dependency="kraken",
            operation=operation,
            exc=exc,
            log_event=f"system.{endpoint}.kraken_unexpected_error",
        )


# --- Request/Response Models ---

class ServiceStatus(BaseModel):
    database: str
    agents: str
    redis: str = "not_configured"
    kraken: str = "not_configured"


class KrakenConnectionStatus(BaseModel):
    authenticated: bool
    reachable: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    services: ServiceStatus
    kraken_details: Optional[KrakenConnectionStatus] = None


class LogEntry(BaseModel):
    id: int
    level: str
    source: str
    message: str
    details: Optional[dict] = None
    timestamp: datetime


class LogsResponse(BaseModel):
    logs: List[LogEntry]
    total: int
    page: int
    page_size: int


class DatabaseBackupResponse(BaseModel):
    """High-level summary returned after a backup completes."""

    file_name: str
    path: str
    size_bytes: int
    timestamp: datetime
    message: str


class DatabaseBackupEntry(BaseModel):
    file_name: str
    path: str
    size_bytes: int
    timestamp: datetime


class DatabaseBackupsResponse(BaseModel):
    backups: List[DatabaseBackupEntry]


class DatabaseRestoreRequest(BaseModel):
    file_name: str = Field(..., min_length=1)


class DatabaseRestoreResponse(BaseModel):
    file_name: str
    path: str
    size_bytes: int
    restored_at: datetime
    message: str


# --- Routes ---

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Returns status of all system services including live Kraken API connectivity
    and raises ServiceUnavailableException when dependencies fail.
    """
    kraken_status = "not_configured"
    kraken_details = None

    if kraken_service.is_authenticated:
        kraken_details = await _probe_kraken_latency(endpoint="health")
        kraken_status = "connected"
    else:
        kraken_details = KrakenConnectionStatus(
            authenticated=False, reachable=False,
            error="API credentials not configured",
        )

    return HealthResponse(
        status="healthy",
        version="0.1.0",
        services=ServiceStatus(
            database="connected",
            agents="initializing",
            kraken=kraken_status,
        ),
        kraken_details=kraken_details,
    )


@router.get("/connection-status", response_model=KrakenConnectionStatus)
async def connection_status():
    """Check Kraken API connection status independently, failing closed on outages."""
    if not kraken_service.is_authenticated:
        return KrakenConnectionStatus(
            authenticated=False, reachable=False,
            error="API credentials not configured",
        )

    return await _probe_kraken_latency(endpoint="connection-status")


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    level: Optional[str] = Query(
        None, description="Filter by log level (debug, info, warning, error, critical)"
    ),
    source: Optional[str] = Query(None, description="Filter by source/component"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_async_db),
    user: User = Depends(get_current_user),
):
    """
    Get system logs with filtering and pagination.

    - Supports filtering by level and source
    - Paginated results
    - Ordered by timestamp descending (newest first)
    """
    conditions = []
    if level:
        conditions.append(SystemLog.level == level)
    if source:
        conditions.append(SystemLog.source.ilike(f"%{source}%"))

    count_stmt = select(func.count(SystemLog.id)).select_from(SystemLog)
    for condition in conditions:
        count_stmt = count_stmt.where(condition)
    count_result = await db.execute(count_stmt)
    total = int(count_result.scalar_one() or 0)

    offset = (page - 1) * page_size
    logs_stmt = select(SystemLog)
    for condition in conditions:
        logs_stmt = logs_stmt.where(condition)
    logs_stmt = (
        logs_stmt.order_by(desc(SystemLog.timestamp)).offset(offset).limit(page_size)
    )
    logs = (await db.execute(logs_stmt)).scalars().all()

    # Convert to response format
    log_entries = [
        LogEntry(
            id=log.id,
            level=log.level,
            source=log.source,
            message=log.message,
            details=log.details_json,
            timestamp=log.timestamp,
        )
        for log in logs
    ]

    return LogsResponse(
        logs=log_entries,
        total=total,
        page=page,
        page_size=page_size
    )


@router.post(
    "/backups",
    response_model=DatabaseBackupResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_database_backup(user: User = Depends(get_current_user)):
    """Trigger a snapshot of the sqlite database file."""
    settings = get_app_settings()
    if not settings.database_backup_enabled:
        _log_backup_event(
            "warning",
            "create_backup",
            "Database backups disabled",
            {"user_id": user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database backups are disabled",
        )

    try:
        result = await asyncio.to_thread(
            backup_sqlite_database,
            backup_dir=settings.backup_dir_path,
            prefix=settings.database_backup_prefix,
            retention_days=settings.database_backup_retention_days,
        )
    except ValueError as exc:
        logger.error("Invalid backup configuration", exc_info=True)
        _log_backup_event(
            "warning",
            "create_backup",
            "Invalid backup configuration",
            {"user_id": user.id, "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except FileNotFoundError as exc:
        logger.error("Database file missing when creating backup", exc_info=True)
        _log_backup_event(
            "error",
            "create_backup",
            "Database file missing when creating backup",
            {"user_id": user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database file not available for backup",
        )
    except Exception as exc:
        logger.exception("Unexpected error while creating database backup")
        _log_backup_event(
            "error",
            "create_backup",
            "Unexpected error while creating database backup",
            {"user_id": user.id},
        )
        raise ServiceUnavailableException(
            service="database_backup",
            details={"operation": "create_backup"},
        ) from exc

    return DatabaseBackupResponse(
        file_name=result.file_name,
        path=str(result.path),
        size_bytes=result.size_bytes,
        timestamp=result.timestamp,
        message="Database backup completed successfully",
    )


@router.get("/backups", response_model=DatabaseBackupsResponse)
async def list_database_backups(user: User = Depends(get_current_user)):
    """List available sqlite database backups."""
    settings = get_app_settings()
    if not settings.database_backup_enabled:
        _log_backup_event(
            "warning",
            "list_backups",
            "Database backups disabled for listing",
            {"user_id": user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database backups are disabled",
        )

    try:
        results = await asyncio.to_thread(
            list_sqlite_backups,
            backup_dir=settings.backup_dir_path,
            prefix=settings.database_backup_prefix,
        )
    except ValueError as exc:
        logger.error("Invalid backup configuration", exc_info=True)
        _log_backup_event(
            "warning",
            "list_backups",
            "Invalid backup configuration while listing backups",
            {"user_id": user.id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Unexpected error while listing database backups")
        _log_backup_event(
            "error",
            "list_backups",
            "Unexpected error while listing database backups",
            {"user_id": user.id},
        )
        raise ServiceUnavailableException(
            service="database_backup",
            details={"operation": "list_backups"},
        ) from exc

    entries = [
        DatabaseBackupEntry(
            file_name=result.file_name,
            path=str(result.path),
            size_bytes=result.size_bytes,
            timestamp=result.timestamp,
        )
        for result in results
    ]

    return DatabaseBackupsResponse(backups=entries)


@router.post("/backups/restore", response_model=DatabaseRestoreResponse)
async def restore_database_backup(
    payload: DatabaseRestoreRequest,
    user: User = Depends(get_current_user),
):
    """Restore a sqlite database from a selected backup."""
    settings = get_app_settings()
    if not settings.database_backup_enabled:
        _log_backup_event(
            "warning",
            "restore_backup",
            "Database backups disabled, restore unavailable",
            {"user_id": user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database backups are disabled",
        )
    if not settings.database_restore_enabled:
        _log_backup_event(
            "warning",
            "restore_backup",
            "Database restores disabled",
            {"user_id": user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database restores are disabled",
        )

    try:
        result = await asyncio.to_thread(
            restore_sqlite_database,
            backup_dir=settings.backup_dir_path,
            prefix=settings.database_backup_prefix,
            file_name=payload.file_name,
        )
    except ValueError as exc:
        logger.error("Invalid restore request", exc_info=True)
        _log_backup_event(
            "warning",
            "restore_backup",
            "Invalid restore request",
            {"user_id": user.id, "file_name": payload.file_name, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except FileNotFoundError as exc:
        logger.warning("Requested backup missing: %s", payload.file_name, exc_info=True)
        _log_backup_event(
            "error",
            "restore_backup",
            "Backup file not found during restore",
            {"user_id": user.id, "file_name": payload.file_name},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup file not found",
        )
    except Exception as exc:
        logger.exception("Unexpected error while restoring database backup")
        _log_backup_event(
            "error",
            "restore_backup",
            "Unexpected error while restoring database backup",
            {"user_id": user.id, "file_name": payload.file_name},
        )
        raise ServiceUnavailableException(
            service="database_backup",
            details={"operation": "restore_backup"},
        ) from exc

    return DatabaseRestoreResponse(
        file_name=result.file_name,
        path=str(result.path),
        size_bytes=result.size_bytes,
        restored_at=result.restored_at,
        message="Database restored successfully",
    )
