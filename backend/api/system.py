"""
System API routes.
"""

import asyncio
import logging
from typing import Optional, List

from datetime import datetime
from fastapi import APIRouter, Query, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from core.auth import get_current_user
from core.settings import get_app_settings
from db.database import (
    get_db,
    backup_sqlite_database,
    list_sqlite_backups,
    restore_sqlite_database,
)
from db.models import SystemLog, User

router = APIRouter()
logger = logging.getLogger("cryptotrader.system")


# --- Request/Response Models ---

class ServiceStatus(BaseModel):
    database: str
    agents: str
    redis: str = "not_configured"
    kraken: str = "not_configured"


class HealthResponse(BaseModel):
    status: str
    version: str
    services: ServiceStatus


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

    Returns status of all system services.
    """
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        services=ServiceStatus(
            database="connected",
            agents="initializing"
        )
    )


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    level: Optional[str] = Query(None, description="Filter by log level (debug, info, warning, error, critical)"),
    source: Optional[str] = Query(None, description="Filter by source/component"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Get system logs with filtering and pagination.

    - Supports filtering by level and source
    - Paginated results
    - Ordered by timestamp descending (newest first)
    """
    # Build query
    query = db.query(SystemLog)

    # Apply filters
    if level:
        query = query.filter(SystemLog.level == level)
    if source:
        query = query.filter(SystemLog.source.ilike(f"%{source}%"))

    # Get total count
    total = query.count()

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    logs = query.order_by(desc(SystemLog.timestamp)).offset(offset).limit(page_size).all()

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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except FileNotFoundError:
        logger.error("Database file missing when creating backup")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database file not available for backup",
        )
    except Exception:
        logger.exception("Unexpected error while creating database backup")
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception:
        logger.exception("Unexpected error while listing database backups")
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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database backups are disabled",
        )
    if not settings.database_restore_enabled:
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except FileNotFoundError:
        logger.warning("Requested backup missing: %s", payload.file_name)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup file not found",
        )
    except Exception:
        logger.exception("Unexpected error while restoring database backup")
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
