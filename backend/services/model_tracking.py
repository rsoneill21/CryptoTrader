"""Tracks per-model AI decisions and writes summaries to the database."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from pydantic import BaseModel, Field, validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.models import ModelPerformance

logger = logging.getLogger(__name__)


DEFAULT_PERIOD_WINDOW = timedelta(days=1)


class ModelDecisionRecord(BaseModel):
    """Validated payload representing the outcome of a single model decision."""

    model_name: str = Field(..., min_length=1)
    strategy_id: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correct: bool = Field(...)
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Normalized confidence score reported by the AI model",
    )
    pnl: Optional[float] = Field(
        None, description="Profit and loss realized for the decision (if settled)"
    )

    class Config:  # noqa: D106
        anystr_strip_whitespace = True

    @validator("model_name")
    def _non_empty_model(cls, value: str) -> str:  # pragma: no cover - trivial
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model_name must not be empty")
        return cleaned


class ModelTrackingService:
    """Encapsulates aggregation logic for the ``model_performance`` table."""

    def __init__(self, period_window: timedelta = DEFAULT_PERIOD_WINDOW) -> None:
        self._period_window = period_window

    async def record_decision(
        self,
        db: Session,
        decision: ModelDecisionRecord,
    ) -> ModelPerformance:
        """Persist a model decision and update the matching performance bucket."""
        period_start, period_end = self._period_bounds(decision.timestamp)
        logger.debug(
            "Recording decision for %s strat=%s period=%s-%s",
            decision.model_name,
            decision.strategy_id,
            period_start,
            period_end,
        )

        performance = self._fetch_existing(db, decision, period_start, period_end)
        try:
            if performance is None:
                performance = ModelPerformance(
                    model_name=decision.model_name,
                    strategy_id=decision.strategy_id,
                    period_start=period_start,
                    period_end=period_end,
                )
                db.add(performance)

            self._apply_decision(performance, decision)
            db.commit()
            db.refresh(performance)
            return performance
        except SQLAlchemyError as exc:
            db.rollback()
            logger.exception(
                "Failed to persist model performance for %s: %s",
                decision.model_name,
                exc,
            )
            raise

    def _period_bounds(self, reference: datetime) -> Tuple[datetime, datetime]:
        """Return a day-aligned [start, end) window to aggregate a decision."""
        start = reference.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + self._period_window
        return start, end

    def _fetch_existing(
        self,
        db: Session,
        decision: ModelDecisionRecord,
        period_start: datetime,
        period_end: datetime,
    ) -> Optional[ModelPerformance]:
        filters = [
            ModelPerformance.model_name == decision.model_name,
            ModelPerformance.period_start == period_start,
            ModelPerformance.period_end == period_end,
        ]
        if decision.strategy_id is None:
            filters.append(ModelPerformance.strategy_id.is_(None))
        else:
            filters.append(ModelPerformance.strategy_id == decision.strategy_id)

        return db.query(ModelPerformance).filter(*filters).one_or_none()

    def _apply_decision(
        self,
        performance: ModelPerformance,
        decision: ModelDecisionRecord,
    ) -> None:
        performance.total_decisions = (performance.total_decisions or 0) + 1
        if decision.correct:
            performance.correct_decisions = (performance.correct_decisions or 0) + 1

        performance.accuracy = self._safe_ratio(
            performance.correct_decisions, performance.total_decisions
        )
        performance.win_rate = performance.accuracy

        if decision.pnl is not None:
            performance.total_pnl = (performance.total_pnl or 0.0) + decision.pnl

        if decision.confidence is not None:
            prior_count = max(performance.total_decisions - 1, 0)
            performance.avg_confidence = self._update_average(
                performance.avg_confidence, prior_count, decision.confidence
            )

    def _safe_ratio(self, numerator: Optional[int], denominator: Optional[int]) -> float:
        if not denominator:
            return 0.0
        return float((numerator or 0)) / float(denominator)

    def _update_average(
        self, prior_average: Optional[float], prior_count: int, new_value: float
    ) -> float:
        base = max(prior_count, 0)
        existing = prior_average or 0.0
        return ((existing * base) + new_value) / float(base + 1)


model_tracking_service = ModelTrackingService()
