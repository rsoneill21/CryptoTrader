"""
Database configuration and initialization.
"""

import json
import logging
import os
import shutil
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, NamedTuple, Optional, Tuple

from pydantic import BaseModel, Field, validator
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Database URL - SQLite for development
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cryptotrader.db")

# Async Database URL - convert sqlite:/// to sqlite+aiosqlite:///
ASYNC_DATABASE_URL = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")
if "postgresql" in DATABASE_URL and "asyncpg" not in DATABASE_URL:
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# Create sync engine (for legacy/logging code)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False
)

# Create async engine
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    # pool_pre_ping ensures connections are valid before use
    pool_pre_ping=True if "postgresql" in ASYNC_DATABASE_URL else False,
)

# Session factories
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Prevent attribute expiration after commit in async context
)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency that provides database session (sync - for legacy code)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    """Async dependency that provides database session."""
    async with AsyncSessionLocal() as session:
        yield session


def init_db():
    """Apply migrations so the database schema is up to date."""
    import asyncio
    from db import models  # Import models to register them
    from db.migrations import run_migrations

    # Run Alembic migrations (uses sync engine)
    run_migrations()

    # Verify async engine can connect without blocking initialization forever.
    async def _verify_async_engine():
        try:
            async with asyncio.timeout(5):
                async with async_engine.begin():
                    # Just verify the connection works
                    pass
        finally:
            await async_engine.dispose()

    try:
        asyncio.run(_verify_async_engine())
    except TimeoutError:
        logger.warning("Async engine verification timed out; continuing startup")
    except Exception as exc:
        logger.warning("Async engine verification skipped or failed: %s", exc)

    _register_user_email_listeners()
    print("Database schema verified via Alembic migrations")


logger = logging.getLogger(__name__)

_SENSITIVE_DETAIL_PARTS = {
    "authorization",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "session",
    "cookie",
}


def _coerce_to_json_serializable(value: Any) -> Any:
    """Ensure the provided value can be serialized as JSON."""

    try:
        serialized = json.dumps(value, default=str)
        return json.loads(serialized)
    except (TypeError, ValueError, json.JSONDecodeError):
        return str(value)


def _sanitize_value(value: Any) -> Any:
    """Sanitize an arbitrary value while keeping complex structures intact."""

    if value is None:
        return None
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    return _coerce_to_json_serializable(value)


def _sanitize_mapping(mapping: Mapping[Any, Any]) -> Dict[str, Any]:
    """Redact sensitive entries within mapping types recursively."""

    sanitized: Dict[str, Any] = {}
    for raw_key, raw_value in mapping.items():
        key = str(raw_key)
        normalized_key = key.lower()
        if any(part in normalized_key for part in _SENSITIVE_DETAIL_PARTS):
            sanitized[key] = "<redacted>"
            continue
        sanitized[key] = _sanitize_value(raw_value)
    return sanitized


def sanitize_log_details(details: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return a copy of the details with sensitive keys redacted."""

    if not details:
        return None

    return _sanitize_mapping(details)


def log_system_error(
    level: str,
    source: str,
    message: str,
    details: Optional[Mapping[str, Any]] = None,
) -> None:
    """Persist a structured entry in the system_logs table."""

    from db.models import SystemLog

    sanitized = sanitize_log_details(details)
    session = SessionLocal()
    try:
        log = SystemLog(
            level=level,
            source=source,
            message=message,
            details_json=sanitized,
        )
        session.add(log)
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.warning("Failed to write system log (%s): %s", source, exc)
    finally:
        session.close()


def purge_expired_sessions(db: Optional[Session] = None) -> int:
    """Delete expired user sessions and return the count removed."""

    from db.models import Session as UserSession

    owns_session = db is None
    session = db or SessionLocal()
    try:
        expired = session.query(UserSession).filter(
            UserSession.expires_at < datetime.utcnow()
        ).delete()
        session.commit()
        return int(expired or 0)
    finally:
        if owns_session:
            session.close()


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


async def fetch_ai_decisions_async(
    session: AsyncSession,
    strategy_id: Optional[int] = None,
    since: Optional[datetime] = None,
    limit: int = 50,
) -> Tuple[int, List["AIDecision"]]:
    """Return recent AI decisions, optionally filtered by strategy or time window."""

    from db.models import AIDecision

    # Count query
    count_query = select(func.count()).select_from(AIDecision)
    if strategy_id is not None:
        count_query = count_query.where(AIDecision.related_strategy_id == strategy_id)
    if since is not None:
        count_query = count_query.where(AIDecision.timestamp >= since)

    count_result = await session.execute(count_query)
    total = count_result.scalar_one()

    # Data query
    query = select(AIDecision)
    if strategy_id is not None:
        query = query.where(AIDecision.related_strategy_id == strategy_id)
    if since is not None:
        query = query.where(AIDecision.timestamp >= since)

    query = query.order_by(AIDecision.timestamp.desc()).limit(limit)
    
    result = await session.execute(query)
    decisions = list(result.scalars().all())
    
    return total, decisions


class DatabaseBackupResult(NamedTuple):
    """Metadata returned after creating a database backup."""

    path: Path
    file_name: str
    timestamp: datetime
    size_bytes: int


class DatabaseRestoreResult(NamedTuple):
    """Metadata returned after restoring a backup."""

    path: Path
    file_name: str
    restored_at: datetime
    size_bytes: int


def _resolve_sqlite_database_path(database_url: str) -> Path:
    """Return the filesystem path backing the configured SQLite database."""

    const_prefix = "sqlite:///"
    if not database_url.startswith(const_prefix):
        raise ValueError("Database backups only supported for sqlite databases")

    relative_path = database_url[len(const_prefix) :]
    if not relative_path:
        raise ValueError("SQLite database path is missing")

    if relative_path == ":memory:":
        raise ValueError("In-memory sqlite databases cannot be backed up")

    candidate = Path(relative_path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()


def _ensure_directory_exists(path: Path) -> None:
    """Create the requested directory tree if missing."""

    path.mkdir(parents=True, exist_ok=True)


def _normalize_backup_prefix(prefix: str) -> str:
    """Sanitize the prefix used for backup filenames."""

    return prefix.strip().replace(" ", "_")


def _prune_old_backups(
    backup_dir: Path,
    prefix: str,
    retention_days: int,
    now: datetime,
) -> None:
    """Remove backup files older than the retention window."""

    cutoff = now - timedelta(days=retention_days)
    for entry in backup_dir.iterdir():
        if not entry.is_file():
            continue
        if not entry.name.startswith(f"{_normalize_backup_prefix(prefix)}-"):
            continue
        if datetime.utcfromtimestamp(entry.stat().st_mtime) < cutoff:
            try:
                entry.unlink()
            except OSError:
                logger.warning("Failed to remove stale backup %s", entry)


def _build_backup_filename(prefix: str, timestamp: datetime) -> str:
    """Generate a timestamped filename for the backup."""

    safe_prefix = _normalize_backup_prefix(prefix)
    return f"{safe_prefix}-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.db"


def backup_sqlite_database(
    *,
    backup_dir: Path,
    prefix: str,
    retention_days: int,
    database_url: str = DATABASE_URL,
) -> DatabaseBackupResult:
    """
    Copy the sqlite database file into the configured backup directory.

    Raises:
        FileNotFoundError: if the sqlite database file is missing.
        ValueError: if the URL is not a sqlite file or retention is invalid.
    """

    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")

    db_path = _resolve_sqlite_database_path(database_url)
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found at {db_path}")

    resolved_dir = backup_dir.expanduser().resolve(strict=False)
    _ensure_directory_exists(resolved_dir)

    now = datetime.utcnow()
    _prune_old_backups(resolved_dir, prefix, retention_days, now)

    filename = _build_backup_filename(prefix, now)
    destination = resolved_dir / filename
    shutil.copy2(db_path, destination)

    size_bytes = destination.stat().st_size
    logger.info("Database backup created at %s (%s bytes)", destination, size_bytes)

    return DatabaseBackupResult(
        path=destination,
        file_name=filename,
        timestamp=now,
        size_bytes=size_bytes,
    )


def list_sqlite_backups(
    *,
    backup_dir: Path,
    prefix: str,
) -> List[DatabaseBackupResult]:
    """Return metadata for backups that match the configured prefix."""

    resolved_dir = backup_dir.expanduser().resolve(strict=False)
    if not resolved_dir.exists():
        return []

    normalized_prefix = _normalize_backup_prefix(prefix)
    backups: List[DatabaseBackupResult] = []

    for entry in resolved_dir.iterdir():
        if not entry.is_file() or entry.suffix.lower() != ".db":
            continue
        if not entry.name.startswith(f"{normalized_prefix}-"):
            continue
        stat = entry.stat()
        backups.append(
            DatabaseBackupResult(
                path=entry.resolve(),
                file_name=entry.name,
                timestamp=datetime.utcfromtimestamp(stat.st_mtime),
                size_bytes=stat.st_size,
            )
        )

    backups.sort(key=lambda entry: entry.timestamp, reverse=True)
    return backups


def restore_sqlite_database(
    *,
    backup_dir: Path,
    prefix: str,
    file_name: str,
    database_url: str = DATABASE_URL,
) -> DatabaseRestoreResult:
    """Replace the active sqlite database with the selected backup."""

    resolved_dir = backup_dir.expanduser().resolve(strict=False)
    normalized_prefix = _normalize_backup_prefix(prefix)
    target = resolved_dir / file_name

    try:
        target_resolved = target.resolve(strict=True)
    except FileNotFoundError:
        raise FileNotFoundError(f"Backup file not found: {file_name}")

    if not target_resolved.is_relative_to(resolved_dir):
        raise ValueError("Backup file must reside in the configured backup directory")
    if not target_resolved.name.startswith(f"{normalized_prefix}-"):
        raise ValueError("Backup file name is invalid")
    if target_resolved.suffix.lower() != ".db":
        raise ValueError("Only .db backup files can be restored")

    db_path = _resolve_sqlite_database_path(database_url)
    shutil.copy2(target_resolved, db_path)

    size_bytes = target_resolved.stat().st_size
    restored_at = datetime.utcnow()
    logger.info(
        "Database restored from backup %s into %s",
        target_resolved,
        db_path,
    )

    return DatabaseRestoreResult(
        path=db_path,
        file_name=target_resolved.name,
        restored_at=restored_at,
        size_bytes=size_bytes,
    )
