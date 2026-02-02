"""Central alert generator that normalizes severity and collapses duplicates."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, validator
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.models import Alert

logger = logging.getLogger(__name__)

DEFAULT_DEDUP_WINDOW = timedelta(minutes=10)
FINAL_STATUSES = frozenset({"actioned", "dismissed"})
SEVERITY_PRIORITY = {"info": 0, "warning": 1, "critical": 2}


class AlertSeverity(str, Enum):
    """Supported alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertPayload(BaseModel):
    """Basic payload consumed by the alert generation service."""

    type: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    message: Optional[str] = None
    severity: AlertSeverity = Field(default=AlertSeverity.INFO)
    status: str = Field("new", min_length=1)
    related_strategy_id: Optional[int] = None
    related_trade_id: Optional[int] = None
    action_taken: Optional[str] = None
    actioned_at: Optional[datetime] = None
    ai_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    dedup_window_seconds: Optional[int] = Field(None, ge=1)

    model_config = ConfigDict(str_strip_whitespace=True)

    @validator("type", "title", pre=True)
    def _non_empty_string(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must supply a non-empty string")
        return value.strip()

    @validator("status", pre=True)
    def _normalize_status(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("status must not be empty")
        return normalized.lower()


class AlertService:
    """Encapsulates severity normalization, deduplication, and persistence."""

    def __init__(self, dedup_window: timedelta = DEFAULT_DEDUP_WINDOW) -> None:
        self._dedup_window = dedup_window

    async def emit_alert(self, db: Session, payload: AlertPayload) -> Alert:
        """Create or update an alert while enforcing deduplication rules."""

        duplicate = self._find_duplicate(db, payload)
        try:
            if duplicate:
                logger.info(
                    "Deduplicating alert %s/%s against id=%s",
                    payload.type,
                    payload.title,
                    duplicate.id,
                )
                alert_record = self._merge_existing(duplicate, payload)
            else:
                logger.info(
                    "Creating alert %s/%s severity=%s",
                    payload.type,
                    payload.title,
                    payload.severity.value,
                )
                alert_record = self._build_new_alert(payload)
                db.add(alert_record)
            db.commit()
            db.refresh(alert_record)
            return alert_record
        except SQLAlchemyError as exc:
            db.rollback()
            logger.exception(
                "Unable to persist alert %s/%s: %s",
                payload.type,
                payload.title,
                exc,
            )
            raise

    def _find_duplicate(self, db: Session, payload: AlertPayload) -> Optional[Alert]:
        window = self._effective_dedup_window(payload)
        cutoff = datetime.utcnow() - window
        filters = [
            Alert.type == payload.type,
            Alert.title == payload.title,
            Alert.created_at >= cutoff,
            Alert.status.notin_(FINAL_STATUSES),
            self._nullable_equals(Alert.related_strategy_id, payload.related_strategy_id),
            self._nullable_equals(Alert.related_trade_id, payload.related_trade_id),
        ]
        return (
            db.query(Alert)
            .filter(*filters)
            .order_by(desc(Alert.created_at))
            .first()
        )

    def _merge_existing(self, record: Alert, payload: AlertPayload) -> Alert:
        record.message = payload.message or record.message
        record.action_taken = payload.action_taken or record.action_taken
        if payload.ai_confidence is not None:
            record.ai_confidence = payload.ai_confidence
        if payload.related_strategy_id is not None:
            record.related_strategy_id = payload.related_strategy_id
        if payload.related_trade_id is not None:
            record.related_trade_id = payload.related_trade_id
        record.severity = self._choose_severity(record.severity, payload.severity.value)
        record.status = payload.status
        record.actioned_at = self._resolve_actioned_timestamp(payload, record.actioned_at)
        return record

    def _build_new_alert(self, payload: AlertPayload) -> Alert:
        return Alert(
            type=payload.type,
            title=payload.title,
            message=payload.message,
            severity=payload.severity.value,
            status=payload.status,
            related_strategy_id=payload.related_strategy_id,
            related_trade_id=payload.related_trade_id,
            action_taken=payload.action_taken,
            actioned_at=self._resolve_actioned_timestamp(payload, None),
            ai_confidence=payload.ai_confidence,
        )

    @staticmethod
    def _nullable_equals(column: Any, value: Optional[int]) -> Any:
        if value is None:
            return column.is_(None)
        return column == value

    def _effective_dedup_window(self, payload: AlertPayload) -> timedelta:
        if payload.dedup_window_seconds is not None:
            return timedelta(seconds=payload.dedup_window_seconds)
        return self._dedup_window

    def _choose_severity(self, existing: str, candidate: str) -> str:
        existing_priority = SEVERITY_PRIORITY.get(existing, 0)
        candidate_priority = SEVERITY_PRIORITY.get(candidate, 0)
        return candidate if candidate_priority >= existing_priority else existing

    def _resolve_actioned_timestamp(
        self, payload: AlertPayload, current_value: Optional[datetime]
    ) -> Optional[datetime]:
        if payload.actioned_at is not None:
            return payload.actioned_at
        if payload.status in FINAL_STATUSES:
            return current_value or datetime.utcnow()
        return None


alert_service = AlertService()
