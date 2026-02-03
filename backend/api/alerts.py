"""
Alerts API routes.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Alert

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

    class Config:
        # Pydantic v2 migration: renamed from orm_mode
        from_attributes = True


class AlertListResponse(BaseModel):
    alerts: List[AlertResponse]
    total: int
    page: int
    page_size: int


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
    db: Session = Depends(get_db),
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
        db.commit()
        db.refresh(alert)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create alert",
        )
    return _serialize_alert(alert)


@router.get("/", response_model=AlertListResponse)
async def list_alerts(
    severity: Optional[str] = Query(None, description="Severity filter (info, warning, critical)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Alert status filter"),
    alert_type: Optional[str] = Query(None, alias="type", description="Alert type filter"),
    search: Optional[str] = Query(None, description="Keyword search for title or message"),
    since: Optional[datetime] = Query(None, description="Return alerts created after this timestamp"),
    until: Optional[datetime] = Query(None, description="Return alerts created before this timestamp"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=200, description="Number of alerts per page"),
    db: Session = Depends(get_db),
) -> AlertListResponse:
    """List alerts with optional filtering and pagination."""
    severity_filter = None
    if severity:
        try:
            severity_filter = _normalize_severity_value(severity)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )
    try:
        query = db.query(Alert)
        if severity_filter:
            query = query.filter(Alert.severity == severity_filter)
        if status_filter:
            query = query.filter(Alert.status == status_filter)
        if alert_type:
            query = query.filter(Alert.type == alert_type)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Alert.title.ilike(pattern),
                    Alert.message.ilike(pattern),
                )
            )
        if since:
            query = query.filter(Alert.created_at >= since)
        if until:
            query = query.filter(Alert.created_at <= until)

        total = query.count()
        alerts = (
            query.order_by(desc(Alert.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to list alerts",
        )

    return AlertListResponse(
        alerts=[_serialize_alert(alert) for alert in alerts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: int, db: Session = Depends(get_db)) -> AlertResponse:
    """Retrieve a single alert by ID."""
    try:
        alert = db.get(Alert, alert_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch alert",
        )
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    return _serialize_alert(alert)


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: int,
    request: AlertUpdateRequest,
    db: Session = Depends(get_db),
) -> AlertResponse:
    """Partially update alert metadata."""
    try:
        alert = db.get(Alert, alert_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch alert for update",
        )
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
        db.commit()
        db.refresh(alert)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update alert",
        )
    return _serialize_alert(alert)


@router.patch("/{alert_id}/status", response_model=AlertResponse)
async def update_alert_status(
    alert_id: int,
    request: AlertStatusUpdateRequest,
    db: Session = Depends(get_db),
) -> AlertResponse:
    """Update only the status/action fields of an alert."""
    try:
        alert = db.get(Alert, alert_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch alert for status update",
        )
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
        db.commit()
        db.refresh(alert)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update alert status",
        )
    return _serialize_alert(alert)


@router.post("/bulk/status", response_model=BulkStatusUpdateResponse)
async def bulk_update_status(
    request: BulkStatusUpdateRequest,
    db: Session = Depends(get_db),
) -> BulkStatusUpdateResponse:
    """Update status/action metadata for multiple alerts."""
    try:
        alerts = db.query(Alert).filter(Alert.id.in_(request.ids)).all()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch alerts for bulk update",
        )
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
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to apply bulk alert updates",
        )
    return BulkStatusUpdateResponse(updated=len(alerts))
