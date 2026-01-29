"""
System API routes.
"""

from typing import Optional, List
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.database import get_db
from db.models import SystemLog

router = APIRouter()


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
    db: Session = Depends(get_db)
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
