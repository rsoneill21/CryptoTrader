"""Risk management API routes."""

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, conint, confloat
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

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
