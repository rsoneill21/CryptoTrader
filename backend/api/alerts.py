"""Alerts API routes."""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import desc, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import DatabaseException
from db.database import get_async_db
from db.models import Alert
from core.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    apply_cursor_pagination,
    decode_cursor,
    encode_cursor,
)

logger = logging.getLogger("cryptotrader.alerts")
router = APIRouter()

ACTIONED_STATUSES = {"actioned", "dismissed"}
VALID_SEVERITIES = {"info", "warning", "critical"}


def _normalize_severity_value(value: Optional[str], *, default: Optional[str] = None) -> Optional[str]:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if not normalized:
        raise ValueError("Severity cannot be blank.")
    if normalized not in VALID_SEVERITIES:
        raise ValueError(f"Severity must be one of {', '.join(sorted(VALID_SEVERITIES))}.")
    return normalized


class AlertResponse(BaseModel):
    id: int
    type: str
    title: str
    message: Optional[str]
    severity: str
    status: str
    related_strategy_id: Optional[int]
    related_trade_id: Optional[int]
    created_at: datetime
    actioned_at: Optional[datetime]
    action_taken: Optional[str]
    ai_confidence: Optional[float]

    model_config = ConfigDict(from_attributes=True)


class AlertListResponse(BaseModel):
    """
    Cursor-paginated alert list response.

    Uses cursor-based pagination to provide stable results even when
    new alerts are inserted. Cursors encode (timestamp, id) to maintain
    consistent ordering across page fetches.

    Default limit: 25 alerts per page
    """
    alerts: List[AlertResponse]
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
    limit: int
    has_more: bool = False


class AlertChatContextResponse(BaseModel):
    alert_id: int
    title: str
    message: Optional[str]
    severity: Optional[str]
    status: Optional[str]
    type: Optional[str]
    related_strategy_id: Optional[int]
    related_trade_id: Optional[int]
    created_at: datetime
    prompt: str

    model_config = ConfigDict(from_attributes=True)


class AlertCreateRequest(BaseModel):
    type: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    message: Optional[str] = None
    severity: str = Field("info")
    status: str = Field("new")
    related_strategy_id: Optional[int] = None
    related_trade_id: Optional[int] = None
    action_taken: Optional[str] = None
    actioned_at: Optional[datetime] = None
    ai_confidence: Optional[float] = None

    @field_validator("severity", mode="before")
    @classmethod
    def _validate_severity(cls, value: Optional[str]) -> str:
        normalized = _normalize_severity_value(value, default="info")
        assert normalized is not None
        return normalized


class AlertUpdateRequest(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    action_taken: Optional[str] = None
    actioned_at: Optional[datetime] = None
    ai_confidence: Optional[float] = None

    @field_validator("severity", mode="before")
    @classmethod
    def _validate_severity(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_severity_value(value, default=None)


class AlertStatusUpdateRequest(BaseModel):
    status: str = Field(..., min_length=1)
    action_taken: Optional[str] = None
    actioned_at: Optional[datetime] = None


class BulkStatusUpdateRequest(BaseModel):
    ids: List[int] = Field(..., min_items=1)
    status: str = Field(..., min_length=1)
    action_taken: Optional[str] = None
    actioned_at: Optional[datetime] = None


class BulkStatusUpdateResponse(BaseModel):
    updated: int


def _serialize_alert(alert: Alert) -> AlertResponse:
    return AlertResponse.from_orm(alert)


def _build_alert_chat_prompt(alert: Alert) -> str:
    title = alert.title or 'Untitled alert'
    message = (alert.message or 'No additional details provided.').strip()
    if not message:
        message = 'No additional details provided.'
    type_segment = f"Type: {alert.type}." if alert.type else ''
    severity_segment = f"Severity: {alert.severity}." if alert.severity else ''
    status_segment = f"Status: {alert.status}." if alert.status else ''
    prompt_segments = [
        f'Reviewing alert "{title}".',
        type_segment,
        severity_segment,
        status_segment,
        f'Summary: {message}',
        'Provide next steps, risk considerations, and any follow-up questions.',
    ]
    return ' '.join(segment for segment in prompt_segments if segment)


def _apply_actioned_timestamp(
    alert: Alert, status_value: Optional[str], actioned_at: Optional[datetime]
) -> None:
    if actioned_at is not None:
        alert.actioned_at = actioned_at
        return
    requested_status = status_value or alert.status
    if requested_status in ACTIONED_STATUSES and alert.actioned_at is None:
        alert.actioned_at = datetime.utcnow()


@router.post(
    "/",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_alert(
    request: AlertCreateRequest,
    db: AsyncSession = Depends(get_async_db),
) -> AlertResponse:
    """Create a new alert entry."""
    alert = Alert(
        type=request.type,
        title=request.title,
        message=request.message,
        severity=request.severity,
        status=request.status,
        related_strategy_id=request.related_strategy_id,
        related_trade_id=request.related_trade_id,
        action_taken=request.action_taken,
        actioned_at=request.actioned_at,
        ai_confidence=request.ai_confidence,
    )
    _apply_actioned_timestamp(alert, request.status, request.actioned_at)
    try:
        db.add(alert)
        await db.commit()
        await db.refresh(alert)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to create alert", exc_info=True)
        raise DatabaseException(
            message="Unable to create alert",
            details={"operation": "create_alert"},
        ) from exc
    return _serialize_alert(alert)


@router.get("/", response_model=AlertListResponse)
async def list_alerts(
    cursor: Optional[str] = Query(None, description="Cursor token for pagination"),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT, description="Number of alerts per page"),
    severity: Optional[str] = Query(None, description="Severity filter (info, warning, critical)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Alert status filter"),
    alert_type: Optional[str] = Query(None, alias="type", description="Alert type filter"),
    search: Optional[str] = Query(None, description="Keyword search for title or message"),
    since: Optional[datetime] = Query(None, description="Return alerts created after this timestamp"),
    until: Optional[datetime] = Query(None, description="Return alerts created before this timestamp"),
    db: AsyncSession = Depends(get_async_db),
) -> AlertListResponse:
    """
    List alerts with cursor-based pagination and optional filtering.

    Cursor pagination ensures stable results even when new alerts are inserted.
    Alerts are ordered by created_at DESC, then id DESC for deterministic sorting.

    Query parameters:
        cursor: Pagination cursor (from previous response's next_cursor/prev_cursor)
        limit: Number of alerts to return (default 25, max 100)
        severity: Filter by severity level (info, warning, critical)
        status: Filter by alert status
        type: Filter by alert type
        search: Keyword search in title or message
        since: Return alerts created after this timestamp
        until: Return alerts created before this timestamp

    Returns:
        AlertListResponse with alerts list, next_cursor, prev_cursor, and has_more flag
    """
    # Validate severity if provided
    severity_filter = None
    if severity:
        try:
            severity_filter = _normalize_severity_value(severity)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )

    cursor_timestamp: Optional[datetime] = None
    cursor_id: Optional[int] = None
    if cursor:
        try:
            cursor_timestamp, cursor_id = decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid cursor: {exc}",
            )

    try:
        # Build base query with filters
        query = select(Alert)

        if severity_filter:
            query = query.where(Alert.severity == severity_filter)
        if status_filter:
            query = query.where(Alert.status == status_filter)
        if alert_type:
            query = query.where(Alert.type == alert_type)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    Alert.title.ilike(pattern),
                    Alert.message.ilike(pattern),
                )
            )
        if since:
            query = query.where(Alert.created_at >= since)
        if until:
            query = query.where(Alert.created_at <= until)

        # Apply cursor filter (for pagination continuation)
        cursor_tuple = (
            (cursor_timestamp, cursor_id)
            if cursor_timestamp is not None and cursor_id is not None
            else None
        )
        query, _, _ = apply_cursor_pagination(
            query,
            cursor_values=cursor_tuple,
            timestamp_column=Alert.created_at,
            id_column=Alert.id,
        )

        # Order by created_at DESC, id DESC for stable sorting
        query = query.order_by(desc(Alert.created_at), desc(Alert.id))

        # Fetch limit + 1 to check if there are more results
        query = query.limit(limit + 1)

        result = await db.execute(query)
        alerts_list = list(result.scalars().all())

    except SQLAlchemyError as exc:
        logger.error("Failed to list alerts", exc_info=True)
        raise DatabaseException(
            message="Unable to list alerts",
            details={"operation": "list_alerts"},
        ) from exc

    # Determine if there are more results
    has_more = len(alerts_list) > limit
    if has_more:
        alerts_list = alerts_list[:limit]  # Trim to requested limit

    # Generate next_cursor from last item
    next_cursor = None
    if has_more and alerts_list:
        last_alert = alerts_list[-1]
        next_cursor = encode_cursor(last_alert.created_at, last_alert.id)

    # Generate prev_cursor from first item (if we came from a cursor)
    prev_cursor = None
    if cursor and alerts_list:
        first_alert = alerts_list[0]
        prev_cursor = encode_cursor(first_alert.created_at, first_alert.id)

    return AlertListResponse(
        alerts=[_serialize_alert(alert) for alert in alerts_list],
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
        limit=limit,
        has_more=has_more,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: int, db: AsyncSession = Depends(get_async_db)) -> AlertResponse:
    """Retrieve a single alert by ID."""
    try:
        alert = await db.get(Alert, alert_id)
    except SQLAlchemyError as exc:
        logger.error("Failed to fetch alert %s", alert_id, exc_info=True)
        raise DatabaseException(
            message="Unable to fetch alert",
            details={"operation": "get_alert", "alert_id": alert_id},
        ) from exc
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    return _serialize_alert(alert)


@router.get("/{alert_id}/chat-context", response_model=AlertChatContextResponse)
async def get_alert_chat_context(alert_id: int, db: AsyncSession = Depends(get_async_db)) -> AlertChatContextResponse:
    """Return structured context for starting a chat about an alert."""
    try:
        alert = await db.get(Alert, alert_id)
    except SQLAlchemyError as exc:
        logger.error("Failed to fetch alert context %s", alert_id, exc_info=True)
        raise DatabaseException(
            message="Unable to fetch alert context",
            details={"operation": "get_alert_context", "alert_id": alert_id},
        ) from exc
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    return AlertChatContextResponse(
        alert_id=alert.id,
        title=alert.title,
        message=alert.message,
        severity=alert.severity,
        status=alert.status,
        type=alert.type,
        related_strategy_id=alert.related_strategy_id,
        related_trade_id=alert.related_trade_id,
        created_at=alert.created_at,
        prompt=_build_alert_chat_prompt(alert),
    )


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: int,
    request: AlertUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
) -> AlertResponse:
    """Partially update alert metadata."""
    try:
        alert = await db.get(Alert, alert_id)
    except SQLAlchemyError as exc:
        logger.error("Failed to load alert %s for update", alert_id, exc_info=True)
        raise DatabaseException(
            message="Unable to load alert",
            details={"operation": "update_alert_load", "alert_id": alert_id},
        ) from exc
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    if request.title is not None:
        alert.title = request.title
    if request.message is not None:
        alert.message = request.message
    if request.severity is not None:
        alert.severity = request.severity
    if request.status is not None:
        alert.status = request.status
    if request.action_taken is not None:
        alert.action_taken = request.action_taken
    if request.ai_confidence is not None:
        alert.ai_confidence = request.ai_confidence
    _apply_actioned_timestamp(alert, request.status, request.actioned_at)

    try:
        await db.commit()
        await db.refresh(alert)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to update alert %s", alert_id, exc_info=True)
        raise DatabaseException(
            message="Unable to update alert",
            details={"operation": "update_alert", "alert_id": alert_id},
        ) from exc
    return _serialize_alert(alert)


@router.patch("/{alert_id}/status", response_model=AlertResponse)
async def update_alert_status(
    alert_id: int,
    request: AlertStatusUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
) -> AlertResponse:
    """Update only the status/action fields of an alert."""
    try:
        alert = await db.get(Alert, alert_id)
    except SQLAlchemyError as exc:
        logger.error("Failed to load alert %s for status update", alert_id, exc_info=True)
        raise DatabaseException(
            message="Unable to load alert",
            details={"operation": "update_alert_status_load", "alert_id": alert_id},
        ) from exc
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    alert.status = request.status
    if request.action_taken is not None:
        alert.action_taken = request.action_taken
    _apply_actioned_timestamp(alert, request.status, request.actioned_at)

    try:
        await db.commit()
        await db.refresh(alert)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to update alert status for %s", alert_id, exc_info=True)
        raise DatabaseException(
            message="Unable to update alert status",
            details={"operation": "update_alert_status", "alert_id": alert_id},
        ) from exc
    return _serialize_alert(alert)


@router.post("/bulk/status", response_model=BulkStatusUpdateResponse)
async def bulk_update_status(
    request: BulkStatusUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
) -> BulkStatusUpdateResponse:
    """Update status/action metadata for multiple alerts."""
    try:
        result = await db.execute(select(Alert).where(Alert.id.in_(request.ids)))
        alerts = list(result.scalars().all())
    except SQLAlchemyError as exc:
        logger.error("Failed to fetch alerts for bulk update", exc_info=True)
        raise DatabaseException(
            message="Unable to fetch alerts",
            details={"operation": "bulk_update_status"},
        ) from exc
    if not alerts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No alerts found for provided IDs",
        )
    for alert in alerts:
        alert.status = request.status
        if request.action_taken is not None:
            alert.action_taken = request.action_taken
        _apply_actioned_timestamp(alert, request.status, request.actioned_at)

    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to apply bulk alert updates", exc_info=True)
        raise DatabaseException(
            message="Unable to apply bulk alert updates",
            details={"operation": "bulk_update_status_commit"},
        ) from exc
    return BulkStatusUpdateResponse(updated=len(alerts))
