"""
Database configuration and initialization.
"""

import logging
import os
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, validator
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker, declarative_base

# Database URL - SQLite for development
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cryptotrader.db")

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency that provides database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Apply migrations so the database schema is up to date."""

    from db import models  # Import models to register them
    from db.migrations import run_migrations

    run_migrations()
    _register_user_email_listeners()
    print("Database schema verified via Alembic migrations")


logger = logging.getLogger(__name__)


class MobileTableHints(BaseModel):
    """Layout hints that downstream components can use to keep tables responsive."""

    allow_horizontal_scroll: bool = True
    min_viewport_width: int = Field(
        360,
        ge=240,
        le=768,
        description="Minimum mobile viewport width (px) that should keep the table readable.",
    )
    max_visible_columns: int = Field(
        6,
        ge=3,
        le=12,
        description="Target number of columns visible before horizontal scrolling is required.",
    )
    data_precision: int = Field(
        3,
        ge=0,
        le=8,
        description="Decimal precision used when formatting numeric cells for narrow layouts.",
    )
    gutter_spacing: int = Field(
        12,
        ge=0,
        le=40,
        description="Horizontal spacing (px) between cells to keep touch targets comfortable.",
    )

    @validator("max_visible_columns")
    def _enforce_column_targets(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_visible_columns must be positive")
        return value


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    logger.warning("%s must be a boolean value; defaulting to %s", name, default)
    return default


def _parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning("%s must be an integer; defaulting to %s", name, default)
        return default


@lru_cache()
def get_mobile_table_hints() -> MobileTableHints:
    """Return the mobile table layout hints to keep data grids readable."""

    hints = MobileTableHints(
        allow_horizontal_scroll=_parse_bool_env("TABLE_ALLOW_HORIZONTAL_SCROLL", True),
        min_viewport_width=_parse_int_env("TABLE_MIN_VIEWPORT_WIDTH", 360),
        max_visible_columns=_parse_int_env("TABLE_MAX_VISIBLE_COLUMNS", 6),
        data_precision=_parse_int_env("TABLE_DATA_PRECISION", 3),
        gutter_spacing=_parse_int_env("TABLE_GUTTER_SPACING", 12),
    )
    logger.debug("Mobile table hints loaded: %s", hints.model_dump())
    return hints


_USER_EMAIL_LISTENERS_REGISTERED = False


def _normalize_email(target: Any) -> str:
    """Ensure emails are trimmed and lowercased."""

    if not isinstance(target.email, str):
        return target.email

    normalized = target.email.strip().lower()
    target.email = normalized
    return normalized


def _register_user_email_listeners() -> None:
    """Attach SQLAlchemy events to keep emails normalized and unique."""

    global _USER_EMAIL_LISTENERS_REGISTERED
    if _USER_EMAIL_LISTENERS_REGISTERED:
        return

    from db.models import User

    @event.listens_for(User, "before_insert")
    def _on_before_insert(mapper, connection, target: User) -> None:
        _normalize_email(target)

    @event.listens_for(User, "before_update")
    def _on_before_update(mapper, connection, target: User) -> None:
        _normalize_email(target)

    @event.listens_for(SessionLocal, "before_flush")
    def _enforce_unique_email(session: Session, flush_context, instances) -> None:
        if not session.new:
            return

        bucket: Dict[str, List[User]] = defaultdict(list)
        for instance in session.new:
            if isinstance(instance, User) and instance.email:
                normalized = _normalize_email(instance)
                bucket[normalized].append(instance)

        for normalized_email, users in bucket.items():
            if len(users) > 1:
                raise IntegrityError(
                    statement="duplicate_email",
                    params={"email": normalized_email},
                    orig=Exception("Email already registered"),
                )

            query = select(User.id).where(func.lower(User.email) == normalized_email)
            exists = session.execute(query).scalar_one_or_none()
            if exists is not None:
                raise IntegrityError(
                    statement="duplicate_email",
                    params={"email": normalized_email},
                    orig=Exception("Email already registered"),
                )

    _USER_EMAIL_LISTENERS_REGISTERED = True


def fetch_ai_decisions(
    session: Session,
    strategy_id: Optional[int] = None,
    since: Optional[datetime] = None,
    limit: int = 50,
) -> Tuple[int, List["AIDecision"]]:
    """Return recent AI decisions, optionally filtered by strategy or time window."""

    from db.models import AIDecision

    query = session.query(AIDecision)
    if strategy_id is not None:
        query = query.filter(AIDecision.related_strategy_id == strategy_id)
    if since is not None:
        query = query.filter(AIDecision.timestamp >= since)

    total = query.count()
    decisions = (
        query.order_by(AIDecision.timestamp.desc())
        .limit(limit)
        .all()
    )
    return total, decisions
