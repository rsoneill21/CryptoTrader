"""Risk management API routes."""

from datetime import datetime
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, conint, confloat, root_validator, validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.settings import ThemeMode, get_user_settings_store
from db.database import get_db
from db.models import RiskSettings

router = APIRouter()


class RiskSettingsResponse(BaseModel):
    """Representation of the active risk configuration in the system."""

    max_position_size_pct: float
    max_concurrent_positions: int
    daily_loss_limit: float
    max_drawdown_pct: float
    max_risk_score: float
    current_risk_score: float
    pending_ai_adjustment: bool
    last_ai_recommendation_json: Optional[Any]
    updated_at: Optional[datetime]


class RiskSettingsUpdate(BaseModel):
    """Payload for updating the persisted risk management settings."""

    max_position_size_pct: Optional[confloat(ge=0.0, le=100.0)] = Field(
        None, description="Maximum percentage of equity allowed per single position"
    )
    max_concurrent_positions: Optional[conint(ge=0)] = Field(
        None, description="Cap on simultaneously open positions"
    )
    daily_loss_limit: Optional[confloat(ge=0.0)] = Field(
        None, description="Dollar limit for cumulative losses in a trading day"
    )
    max_drawdown_pct: Optional[confloat(ge=0.0, le=100.0)] = Field(
        None, description="Maximum permitted drawdown percentage"
    )
    max_risk_score: Optional[confloat(ge=0.0, le=100.0)] = Field(
        None, description="Threshold score used for triggering alerts"
    )
    last_ai_recommendation_json: Optional[Any] = Field(
        None, description="Optional context from an AI recommendation for future adjustments"
    )
    pending_ai_adjustment: Optional[bool] = Field(
        None, description="Whether an AI suggestion is awaiting confirmation"
    )


class RiskScoreResponse(BaseModel):
    """Current risk score snapshot returned to UI components."""

    current_score: float
    threshold: float
    ratio: float
    status: str = Field(..., description="Indicator of whether the threshold has been breached")
    last_updated: Optional[datetime]


def _validate_dnd_time(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not re.match(r"^\d{2}:\d{2}$", value):
        raise ValueError("Do-not-disturb times must use HH:MM format")
    hour, minute = map(int, value.split(":"))
    if hour >= 24 or minute >= 60:
        raise ValueError("Do-not-disturb values must fall within a 24-hour clock")
    return value


class SessionSettingsResponse(BaseModel):
    """Surface active session timeout settings consumed by the UI."""

    timeout_seconds: int = Field(..., description="Amount of time before a session expires")
    idle_warning_seconds: int = Field(..., description="Seconds before expiry when a warning appears")


class SessionSettingsUpdate(BaseModel):
    """Payload for adjusting session timeout values."""

    timeout_seconds: Optional[int] = Field(
        None, ge=60, description="Session remaining time in seconds (minimum 1 minute)"
    )
    idle_warning_seconds: Optional[int] = Field(
        None, ge=15, description="How soon before timeout to prompt the user"
    )

    @root_validator
    def _ensure_idle_before_timeout(cls, values):
        timeout = values.get("timeout_seconds")
        idle = values.get("idle_warning_seconds")
        if timeout is not None and idle is not None and idle >= timeout:
            raise ValueError("Idle warning must occur before the session timeout")
        return values


class NotificationSettingsResponse(BaseModel):
    """Current notification preferences shown in Settings."""

    email_alerts: bool
    sms_alerts: bool
    webhook_alerts: bool
    digest_frequency_minutes: int
    do_not_disturb_start: Optional[str]
    do_not_disturb_end: Optional[str]


class NotificationSettingsUpdate(BaseModel):
    """Payload for updating notification delivery preferences."""

    email_alerts: Optional[bool] = None
    sms_alerts: Optional[bool] = None
    webhook_alerts: Optional[bool] = None
    digest_frequency_minutes: Optional[int] = Field(
        None, ge=15, le=1440, description="Minutes between digest deliveries"
    )
    do_not_disturb_start: Optional[str] = None
    do_not_disturb_end: Optional[str] = None

    @validator("do_not_disturb_start", "do_not_disturb_end")
    def _validate_dnd_format(cls, value):
        return _validate_dnd_time(value)


class ThemeSettingsResponse(BaseModel):
    """Theme configuration returned for the Settings page."""

    mode: ThemeMode
    high_contrast: bool
    auto_follow_system: bool


class ThemeSettingsUpdate(BaseModel):
    """Payload describing UI theme adjustments."""

    mode: Optional[ThemeMode] = Field(None, description="Dark, light, or system-follow mode")
    high_contrast: Optional[bool] = None
    auto_follow_system: Optional[bool] = None


class APIKeyEntry(BaseModel):
    """Single API key update request."""

    name: str = Field(..., min_length=1, description="Friendly label for the key")
    value: Optional[str] = Field(None, description="Plain text value to store (masked when retrieved)")
    enabled: Optional[bool] = None


class APIKeyUpdateRequest(BaseModel):
    """Batch request for updating API keys."""

    updates: List[APIKeyEntry]


class APIKeySummary(BaseModel):
    """Representation of an API key in the UI."""

    name: str
    enabled: bool
    status: str
    masked_value: str
    created_at: datetime
    last_updated: datetime


class APIKeyListResponse(BaseModel):
    keys: List[APIKeySummary]


def _get_latest_settings(db: Session) -> RiskSettings:
    """Return the most recently written risk settings record, creating one if necessary."""

    settings = (
        db.query(RiskSettings)
        .order_by(RiskSettings.updated_at.desc())
        .first()
    )
    if settings:
        return settings

    settings = RiskSettings()
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def _build_settings_response(settings: RiskSettings) -> RiskSettingsResponse:
    """Translate the SQLAlchemy model into the API response model."""

    return RiskSettingsResponse(
        max_position_size_pct=float(settings.max_position_size_pct or 0.0),
        max_concurrent_positions=int(settings.max_concurrent_positions or 0),
        daily_loss_limit=float(settings.daily_loss_limit or 0.0),
        max_drawdown_pct=float(settings.max_drawdown_pct or 0.0),
        max_risk_score=float(settings.max_risk_score or 0.0),
        current_risk_score=float(settings.current_risk_score or 0.0),
        pending_ai_adjustment=bool(settings.pending_ai_adjustment),
        last_ai_recommendation_json=settings.last_ai_recommendation_json,
        updated_at=settings.updated_at,
    )


def _build_score_response(settings: RiskSettings) -> RiskScoreResponse:
    """Build a lean response that highlights the current risk exposure."""

    threshold = float(settings.max_risk_score or 0.0)
    score = float(settings.current_risk_score or 0.0)
    ratio = score / threshold if threshold > 0 else 0.0
    status = "alert" if threshold > 0 and score >= threshold else "ok"
    return RiskScoreResponse(
        current_score=score,
        threshold=threshold,
        ratio=ratio,
        status=status,
        last_updated=settings.updated_at,
    )


@router.get("/settings", response_model=RiskSettingsResponse)
async def get_risk_settings(db: Session = Depends(get_db)) -> RiskSettingsResponse:
    """Return the latest risk configuration so the UI can render the active guardrails."""

    try:
        settings = _get_latest_settings(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load risk settings at this time",
        ) from exc
    return _build_settings_response(settings)


@router.put("/settings", response_model=RiskSettingsResponse)
async def update_risk_settings(
    payload: RiskSettingsUpdate, db: Session = Depends(get_db)
) -> RiskSettingsResponse:
    """Persist configuration changes that are either manually entered or confirmed from AI recommendations."""

    settings = _get_latest_settings(db)
    update_payload = payload.model_dump(exclude_unset=True)
    if not update_payload:
        return _build_settings_response(settings)

    for field_name, value in update_payload.items():
        setattr(settings, field_name, value)

    try:
        db.add(settings)
        db.commit()
        db.refresh(settings)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to persist risk settings",
        ) from exc

    return _build_settings_response(settings)


@router.get("/score", response_model=RiskScoreResponse)
async def get_risk_score(db: Session = Depends(get_db)) -> RiskScoreResponse:
    """Expose the current risk score and compare it with the configured alert threshold."""

    try:
        settings = _get_latest_settings(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to resolve risk score",
        ) from exc

    return _build_score_response(settings)


@router.get("/settings/session", response_model=SessionSettingsResponse)
async def get_session_settings() -> SessionSettingsResponse:
    """Return the current session timeout configuration."""

    store = get_user_settings_store()
    snapshot = store.session_snapshot()
    return SessionSettingsResponse(**snapshot)


@router.put("/settings/session", response_model=SessionSettingsResponse)
async def update_session_settings(
    payload: SessionSettingsUpdate,
) -> SessionSettingsResponse:
    """Adjust the configured session timeout and warning window."""

    store = get_user_settings_store()
    snapshot = store.session_snapshot()
    proposed_timeout = (
        payload.timeout_seconds if payload.timeout_seconds is not None else snapshot["timeout_seconds"]
    )
    proposed_idle = (
        payload.idle_warning_seconds
        if payload.idle_warning_seconds is not None
        else snapshot["idle_warning_seconds"]
    )
    if proposed_idle >= proposed_timeout:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Idle warning must be configured before the session timeout.",
        )
    updated = store.update_session(
        timeout_seconds=payload.timeout_seconds,
        idle_warning_seconds=payload.idle_warning_seconds,
    )
    return SessionSettingsResponse(**updated)


@router.get("/settings/notifications", response_model=NotificationSettingsResponse)
async def get_notification_settings() -> NotificationSettingsResponse:
    """Read the notification preferences that drive alerts and digests."""

    store = get_user_settings_store()
    return NotificationSettingsResponse(**store.notification_snapshot())


@router.put("/settings/notifications", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    payload: NotificationSettingsUpdate,
) -> NotificationSettingsResponse:
    """Update the notification delivery targets and quiet hours."""

    store = get_user_settings_store()
    update_payload = payload.model_dump(exclude_none=True)
    if not update_payload:
        return NotificationSettingsResponse(**store.notification_snapshot())
    try:
        updated = store.update_notifications(**update_payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to persist notification preferences.",
        ) from exc
    return NotificationSettingsResponse(**updated)


@router.get("/settings/theme", response_model=ThemeSettingsResponse)
async def get_theme_settings() -> ThemeSettingsResponse:
    """Return the UI theme configuration currently in effect."""

    store = get_user_settings_store()
    return ThemeSettingsResponse(**store.theme_snapshot())


@router.put("/settings/theme", response_model=ThemeSettingsResponse)
async def update_theme_settings(payload: ThemeSettingsUpdate) -> ThemeSettingsResponse:
    """Adjust the theme mode or accessibility toggles."""

    store = get_user_settings_store()
    update_payload = payload.model_dump(exclude_none=True)
    if not update_payload:
        return ThemeSettingsResponse(**store.theme_snapshot())
    updated = store.update_theme(
        mode=update_payload.get("mode"),
        high_contrast=update_payload.get("high_contrast"),
        auto_follow_system=update_payload.get("auto_follow_system"),
    )
    return ThemeSettingsResponse(**updated)


@router.get("/settings/api-keys", response_model=APIKeyListResponse)
async def list_api_keys() -> APIKeyListResponse:
    """List the API keys managed via the Settings page."""

    store = get_user_settings_store()
    entries = store.list_api_keys()
    return APIKeyListResponse(keys=[APIKeySummary(**entry) for entry in entries])


@router.put("/settings/api-keys", response_model=APIKeyListResponse)
async def update_api_keys(payload: APIKeyUpdateRequest) -> APIKeyListResponse:
    """Create or update credentials that the platform can use for external services."""

    if not payload.updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one API key update must be provided.",
        )
    store = get_user_settings_store()
    updates = [item.model_dump(exclude_none=True) for item in payload.updates]
    try:
        store.apply_api_key_updates(updates)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to persist API key changes.",
        ) from exc
    entries = store.list_api_keys()
    return APIKeyListResponse(keys=[APIKeySummary(**entry) for entry in entries])
