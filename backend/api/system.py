"""
System API routes.
"""

import asyncio
import logging
from typing import Any, Optional, List

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

    Returns status of all system services including live Kraken API connectivity.
    """
    kraken_status = "not_configured"
    kraken_details = None

    if kraken_service.is_authenticated:
        kraken_details = KrakenConnectionStatus(
            authenticated=True, reachable=False
        )
        try:
            start = asyncio.get_event_loop().time()
            await kraken_service.get_server_time()
            elapsed = (asyncio.get_event_loop().time() - start) * 1000
            kraken_status = "connected"
            kraken_details.reachable = True
            kraken_details.latency_ms = round(elapsed, 1)
        except KrakenAPIError as exc:
            kraken_status = "error"
            kraken_details.error = str(exc)
        except Exception as exc:
            kraken_status = "unreachable"
            kraken_details.error = str(exc)
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
    """Check Kraken API connection status independently."""
    if not kraken_service.is_authenticated:
        return KrakenConnectionStatus(
            authenticated=False, reachable=False,
            error="API credentials not configured",
        )

    try:
        start = asyncio.get_event_loop().time()
        await kraken_service.get_server_time()
        elapsed = (asyncio.get_event_loop().time() - start) * 1000
        return KrakenConnectionStatus(
            authenticated=True, reachable=True,
            latency_ms=round(elapsed, 1),
        )
    except KrakenAPIError as exc:
        return KrakenConnectionStatus(
            authenticated=True, reachable=False,
            error=str(exc),
        )
    except Exception as exc:
        return KrakenConnectionStatus(
            authenticated=True, reachable=False,
            error=str(exc),
        )


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
        logger.error("Invalid backup configuration: %s", exc)
        _log_backup_event(
            "warning",
            "create_backup",
            "Invalid backup configuration",
            {"user_id": user.id, "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except FileNotFoundError:
        logger.error("Database file missing when creating backup")
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
    except Exception:
        logger.exception("Unexpected error while creating database backup")
        _log_backup_event(
            "error",
            "create_backup",
            "Unexpected error while creating database backup",
            {"user_id": user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create database backup",
        )

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
        logger.error("Invalid backup configuration: %s", exc)
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
    except Exception:
        logger.exception("Unexpected error while listing database backups")
        _log_backup_event(
            "error",
            "list_backups",
            "Unexpected error while listing database backups",
            {"user_id": user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read database backups",
        )

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
        logger.error("Invalid restore request: %s", exc)
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
    except FileNotFoundError:
        logger.warning("Requested backup missing: %s", payload.file_name)
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
    except Exception:
        logger.exception("Unexpected error while restoring database backup")
        _log_backup_event(
            "error",
            "restore_backup",
            "Unexpected error while restoring database backup",
            {"user_id": user.id, "file_name": payload.file_name},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to restore database backup",
        )

    return DatabaseRestoreResponse(
        file_name=result.file_name,
        path=str(result.path),
        size_bytes=result.size_bytes,
        restored_at=result.restored_at,
        message="Database restored successfully",
    )
