"""Export endpoints providing CSV and filtered strategy data."""

import csv
import logging
from datetime import datetime, date, time
from io import StringIO
from typing import Dict, Iterator, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator, validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.exceptions import DatabaseException
from db.database import get_async_db
from db.models import Strategy, Trade, User

logger = logging.getLogger("cryptotrader.export")
router = APIRouter()


class TradeExportParams(BaseModel):
    """Optional filters for the trade export endpoint."""

    start_time: Optional[datetime] = Field(
        None,
        description="Include trades with entry_time on or after this ISO timestamp.",
    )
    end_time: Optional[datetime] = Field(
        None,
        description="Include trades with entry_time on or before this ISO timestamp.",
    )

    # Pydantic v2 migration: replaced @root_validator with @model_validator(mode='after')
    @model_validator(mode="after")
    def validate_time_range(self) -> "TradeExportParams":
        """Ensure the start time is not after the end time."""
        if self.start_time and self.end_time and self.start_time > self.end_time:
            raise ValueError("start_time must be earlier than or equal to end_time")
        return self


class StrategyExportParams(BaseModel):
    """Filters for the strategy export endpoint."""

    start_date: Optional[datetime] = Field(
        None,
        description="Include strategies created on or after this date (inclusive).",
    )
    end_date: Optional[datetime] = Field(
        None,
        description="Include strategies created on or before this date (inclusive).",
    )

    @validator("start_date", pre=True)
    def normalize_start_date(cls, value: Optional[Union[datetime, date, str]]) -> Optional[datetime]:
        """Normalize dates to UTC datetimes starting at the beginning of the day."""
        return cls._normalize_date_value(value, is_end=False)

    @validator("end_date", pre=True)
    def normalize_end_date(cls, value: Optional[Union[datetime, date, str]]) -> Optional[datetime]:
        """Normalize dates to UTC datetimes ending at the end of the day."""
        return cls._normalize_date_value(value, is_end=True)

    # Pydantic v2 migration: replaced @root_validator with @model_validator(mode='after')
    @model_validator(mode="after")
    def validate_date_range(self) -> "StrategyExportParams":
        """Ensure the start date is not after the end date."""
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be earlier than or equal to end_date")
        return self

    @classmethod
    def _normalize_date_value(
        cls,
        value: Optional[Union[datetime, date, str]],
        *,
        is_end: bool,
    ) -> Optional[datetime]:
        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, date):
            boundary = time.max if is_end else time.min
            return datetime.combine(value, boundary)

        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None

            if cleaned.endswith("Z"):
                cleaned = f"{cleaned[:-1]}+00:00"

            try:
                parsed = datetime.fromisoformat(cleaned)
            except ValueError as exc:
                raise ValueError("Invalid date format for export filters") from exc

            is_date_only = "T" not in cleaned and " " not in cleaned
            if is_date_only:
                boundary = time.max if is_end else time.min
                parsed_date = parsed.date()
                tzinfo = parsed.tzinfo
                return datetime.combine(
                    parsed_date,
                    boundary.replace(tzinfo=tzinfo),
                )

            return parsed

        raise ValueError("Invalid date type for export filters")


class StrategyExportItem(BaseModel):
    """Fields returned by the strategy export endpoint."""

    id: int
    name: str
    description: Optional[str]
    source: str
    status: str
    github_url: Optional[str]
    promoted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


TRADES_CSV_HEADERS = [
    "trade_id",
    "strategy_id",
    "symbol",
    "side",
    "entry_price",
    "exit_price",
    "quantity",
    "pnl",
    "fees",
    "ai_model_used",
    "entry_time",
    "exit_time",
    "is_paper",
    "is_manual",
]


def _format_value(value: Optional[object]) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _serialize_strategy(strategy: Strategy) -> StrategyExportItem:
    return StrategyExportItem(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        source=strategy.source or "manual",
        status=strategy.status or "paper",
        github_url=strategy.github_url,
        promoted_at=strategy.promoted_at,
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
    )


def _generate_trade_csv_rows(trades: List[Trade]) -> Iterator[bytes]:
    """Yield CSV chunks for trades to support streaming responses."""
    csv_buffer = StringIO()
    writer = csv.writer(csv_buffer)
    try:
        writer.writerow(TRADES_CSV_HEADERS)
        yield csv_buffer.getvalue().encode("utf-8")
        csv_buffer.truncate(0)
        csv_buffer.seek(0)
        for trade in trades:
            writer.writerow([
                _format_value(trade.id),
                _format_value(trade.strategy_id),
                _format_value(trade.symbol),
                _format_value(trade.side),
                _format_value(trade.entry_price),
                _format_value(trade.exit_price),
                _format_value(trade.quantity),
                _format_value(trade.pnl),
                _format_value(trade.fees),
                _format_value(trade.ai_model_used),
                _format_value(trade.entry_time),
                _format_value(trade.exit_time),
                _format_value(trade.is_paper),
                _format_value(trade.is_manual),
            ])
            chunk = csv_buffer.getvalue().encode("utf-8")
            if chunk:
                yield chunk
            csv_buffer.truncate(0)
            csv_buffer.seek(0)
    finally:
        csv_buffer.close()


@router.get("/trades", status_code=status.HTTP_200_OK)
async def export_trades(
    filters: TradeExportParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> StreamingResponse:
    """Stream trades as a CSV file, optionally filtering by entry time."""
    try:
        stmt = select(Trade)
        if filters.start_time:
            stmt = stmt.where(Trade.entry_time >= filters.start_time)
        if filters.end_time:
            stmt = stmt.where(Trade.entry_time <= filters.end_time)
        stmt = stmt.order_by(Trade.entry_time.desc())
        result = await db.execute(stmt)
        trades = list(result.scalars().all())
    except SQLAlchemyError as exc:
        logger.error("Failed to query trades for export", exc_info=True)
        raise DatabaseException(
            message="Unable to export trades",
            details={"operation": "export_trades"},
        ) from exc

    headers = {
        "Content-Disposition": "attachment; filename=trades_export.csv",
    }

    return StreamingResponse(
        _generate_trade_csv_rows(trades),
        media_type="text/csv",
        headers=headers,
    )


@router.get("/strategies", response_model=List[StrategyExportItem], status_code=status.HTTP_200_OK)
async def export_strategies(
    filters: StrategyExportParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> List[StrategyExportItem]:
    """Return strategies matching the requested creation date range."""
    try:
        stmt = select(Strategy)
        if filters.start_date:
            stmt = stmt.where(Strategy.created_at >= filters.start_date)
        if filters.end_date:
            stmt = stmt.where(Strategy.created_at <= filters.end_date)
        stmt = stmt.order_by(Strategy.created_at.desc())
        result = await db.execute(stmt)
        strategies = list(result.scalars().all())
    except SQLAlchemyError as exc:
        logger.error("Failed to query strategies for export", exc_info=True)
        raise DatabaseException(
            message="Unable to export strategies",
            details={"operation": "export_strategies"},
        ) from exc

    return [_serialize_strategy(strategy) for strategy in strategies]
