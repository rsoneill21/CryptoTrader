"""Shared cursor-based pagination utilities."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

DEFAULT_PAGE_LIMIT = 25
MAX_PAGE_LIMIT = 100


def encode_cursor(created_at: datetime, record_id: int) -> str:
    """Encode cursor token using timestamp and primary key."""

    cursor_str = f"{created_at.isoformat()}|{record_id}"
    return base64.urlsafe_b64encode(cursor_str.encode()).decode()


def decode_cursor(cursor: str) -> Tuple[datetime, int]:
    """Decode an encoded cursor back into timestamp and primary key."""

    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        timestamp_str, id_str = decoded.split("|")
        created_at = datetime.fromisoformat(timestamp_str)
        record_id = int(id_str)
        return created_at, record_id
    except (ValueError, UnicodeDecodeError) as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid cursor format: {exc}")


def apply_cursor_pagination(
    query: Select,
    *,
    cursor: Optional[str] = None,
    cursor_values: Optional[Tuple[datetime, int]] = None,
    timestamp_column: ColumnElement[Any],
    id_column: ColumnElement[Any],
    descending: bool = True,
) -> Tuple[Select, Optional[datetime], Optional[int]]:
    """Apply cursor pagination filters to a SQLAlchemy select query.

    Args:
        query: Base select query with ordering already applied.
        cursor: Encoded cursor token from client, if provided.
        cursor_values: Explicit cursor tuple to skip decode step.
        timestamp_column: Column used for chronological ordering.
        id_column: Column used as deterministic tie-breaker.
        descending: Whether the underlying ORDER BY uses DESC columns.
    """

    if cursor_values is not None:
        cursor_timestamp, cursor_id = cursor_values
    elif cursor:
        cursor_timestamp, cursor_id = decode_cursor(cursor)
    else:
        return query, None, None

    if descending:
        comparison = or_(
            timestamp_column > cursor_timestamp,
            (timestamp_column == cursor_timestamp) & (id_column > cursor_id),
        )
    else:
        comparison = or_(
            timestamp_column < cursor_timestamp,
            (timestamp_column == cursor_timestamp) & (id_column < cursor_id),
        )

    query = query.where(comparison)
    return query, cursor_timestamp, cursor_id
