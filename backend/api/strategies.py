"""Strategy management endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import get_current_user
from db.database import get_db
from db.models import Strategy, User

logger = logging.getLogger("cryptotrader.strategies")
router = APIRouter()
_FIELD_MISSING = object()

STATUS_HINT = "paper, live, paused, archived"


class StrategyCreate(BaseModel):
    """Payload accepted when the UI creates a new strategy."""

    name: str = Field(..., description="Human readable strategy name")
    description: Optional[str] = Field(None, max_length=1024)
    rules: Dict[str, Any] = Field(..., description="Rule definition stored as JSON")
    source: Optional[str] = Field(None, description="Origin of the strategy")
    status: Optional[str] = Field(None, description="Deployment status")
    github_url: Optional[str] = Field(None, description="Associated GitHub reference")
    ai_modifications: Optional[Dict[str, Any]] = Field(
        None,
        description="Ai adjustments applied to the base definition",
        alias="ai_modifications",
    )
    promoted_at: Optional[datetime] = Field(None, description="Timestamp when strategy was promoted")
    promoted_by_recommendation: bool = Field(
        False,
        description="Whether the promotion was driven by the recommendation engine",
    )

    class Config:
        # Pydantic v2 migration: renamed from allow_population_by_field_name
        populate_by_name = True


class StrategyUpdate(BaseModel):
    """Fields that may be updated for an existing strategy."""

    name: Optional[str] = Field(None, description="Human readable strategy name")
    description: Optional[str] = Field(None, max_length=1024)
    rules: Optional[Dict[str, Any]] = Field(None, description="Rule definition stored as JSON")
    source: Optional[str] = Field(None, description="Origin of the strategy")
    status: Optional[str] = Field(None, description="Deployment status")
    github_url: Optional[str] = Field(None, description="Associated GitHub reference")
    ai_modifications: Optional[Dict[str, Any]] = Field(
        None,
        description="Ai adjustments applied to the base definition",
        alias="ai_modifications",
    )
    promoted_at: Optional[datetime] = Field(None, description="Timestamp when strategy was promoted")
    promoted_by_recommendation: Optional[bool] = Field(
        None,
        description="Whether the promotion was driven by the recommendation engine",
    )

    class Config:
        # Pydantic v2 migration: renamed from allow_population_by_field_name
        populate_by_name = True


class StrategyResponse(BaseModel):
    """Serialized strategy response."""

    id: int
    name: str
    description: Optional[str]
    rules: Dict[str, Any]
    source: str
    status: str
    github_url: Optional[str]
    ai_modifications: Optional[Dict[str, Any]]
    promoted_at: Optional[datetime]
    promoted_by_recommendation: bool
    created_at: datetime
    updated_at: datetime


class StrategyPromoteRequest(BaseModel):
    """Payload required to promote a strategy to live."""

    confirm: bool = Field(
        ..., description="Explicit confirmation is required to promote a strategy to live."
    )


def _serialize_strategy(strategy: Strategy) -> StrategyResponse:
    return StrategyResponse(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        rules=strategy.rules_json or {},
        source=strategy.source or "manual",
        status=strategy.status or "paper",
        github_url=strategy.github_url,
        ai_modifications=strategy.ai_modifications_json,
        promoted_at=strategy.promoted_at,
        promoted_by_recommendation=bool(strategy.promoted_by_recommendation),
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
    )


def _normalize_status_filters(values: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    for raw in values or []:
        if not raw:
            continue
        candidate = raw.strip().lower()
        if not candidate:
            continue
        normalized.append(candidate)
    return normalized


@router.get("/", response_model=List[StrategyResponse], status_code=status.HTTP_200_OK)
async def list_strategies(
    status: Optional[List[str]] = Query(
        None,
        alias="status",
        description=f"Return strategies matching a status ({STATUS_HINT}).",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[StrategyResponse]:
    """List strategies, optionally filtering by status."""
    filters = _normalize_status_filters(status)
    try:
        query = db.query(Strategy)
        if filters:
            query = query.filter(Strategy.status.in_(filters))
        strategies = query.order_by(Strategy.updated_at.desc()).all()
    except Exception as exc:  # pragma: no cover - defensive DB guard
        logger.error("Strategy list fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve strategies",
        )

    return [_serialize_strategy(strategy) for strategy in strategies]


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyResponse:
    """Return a single strategy by id."""
    try:
        strategy = db.get(Strategy, strategy_id)
    except Exception as exc:  # pragma: no cover
        logger.error("Failed loading strategy %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load strategy",
        )

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    return _serialize_strategy(strategy)


@router.post("/{strategy_id}/promote", response_model=StrategyResponse)
async def promote_strategy(
    strategy_id: int,
    payload: StrategyPromoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyResponse:
    """Mark a strategy as live after explicit confirmation."""
    try:
        strategy = db.get(Strategy, strategy_id)
    except Exception as exc:
        logger.error("Failed loading strategy for promotion %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load strategy",
        )

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Promotion requires explicit confirmation",
        )

    if strategy.status == "live":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strategy is already live",
        )

    strategy.status = "live"
    strategy.promoted_at = datetime.utcnow()
    strategy.promoted_by_recommendation = False

    try:
        db.commit()
        db.refresh(strategy)
    except Exception as exc:  # pragma: no cover
        db.rollback()
        logger.error("Failed to persist strategy promotion %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to promote strategy",
        )

    return _serialize_strategy(strategy)


@router.post("/", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    payload: StrategyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyResponse:
    """Create a new strategy definition."""
    try:
        strategy = Strategy(
            name=payload.name,
            description=payload.description,
            rules_json=payload.rules,
            source=payload.source or "manual",
            status=payload.status or "paper",
            github_url=payload.github_url,
            ai_modifications_json=payload.ai_modifications,
            promoted_at=payload.promoted_at,
            promoted_by_recommendation=payload.promoted_by_recommendation,
        )
        db.add(strategy)
        db.commit()
        db.refresh(strategy)
    except Exception as exc:  # pragma: no cover
        db.rollback()
        logger.error("Failed to create strategy %s: %s", payload.name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create strategy",
        )

    return _serialize_strategy(strategy)


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    payload: StrategyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyResponse:
    """Modify a strategy definition."""
    try:
        strategy = db.get(Strategy, strategy_id)
    except Exception as exc:
        logger.error("Failed loading strategy for update %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load strategy",
        )

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    update_data = payload.dict(exclude_unset=True, by_alias=True)
    if not update_data:
        return _serialize_strategy(strategy)

    rules_payload = update_data.pop("rules", _FIELD_MISSING)
    ai_payload = update_data.pop("ai_modifications", _FIELD_MISSING)
    has_changes = False

    if rules_payload is not _FIELD_MISSING:
        if rules_payload is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Strategy rules cannot be null",
            )
        strategy.rules_json = rules_payload
        has_changes = True

    if ai_payload is not _FIELD_MISSING:
        strategy.ai_modifications_json = ai_payload
        has_changes = True

    for attr, value in update_data.items():
        setattr(strategy, attr, value)
        has_changes = True

    if not has_changes:
        return _serialize_strategy(strategy)

    try:
        db.commit()
        db.refresh(strategy)
    except Exception as exc:  # pragma: no cover
        db.rollback()
        logger.error("Failed to persist strategy update %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update strategy",
        )

    return _serialize_strategy(strategy)


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Remove a strategy from the catalog."""
    try:
        strategy = db.get(Strategy, strategy_id)
    except Exception as exc:
        logger.error("Failed to load strategy for deletion %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load strategy",
        )

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    try:
        db.delete(strategy)
        db.commit()
    except Exception as exc:  # pragma: no cover
        db.rollback()
        logger.error("Failed to delete strategy %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete strategy",
        )
