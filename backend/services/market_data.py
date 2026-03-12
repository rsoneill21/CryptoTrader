"""Market data persistence helpers."""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field, validator
from sqlalchemy.orm import Session

from db.database import SessionLocal, get_mobile_table_hints
from db.models import MarketData

logger = logging.getLogger(__name__)


def _parse_retention_days(value: Optional[str]) -> int:
    if value is None:
        return 30
    try:
        parsed = int(value)
        return max(0, parsed)
    except ValueError:
        logger.warning("MARKET_DATA_RETENTION_DAYS must be numeric; defaulting to 30")
        return 30


DEFAULT_RETENTION_DAYS = _parse_retention_days(os.getenv("MARKET_DATA_RETENTION_DAYS"))


class MarketDataCandle(BaseModel):
    """Validated OHLCV record that will be persisted to the database."""

    symbol: str = Field(..., min_length=1)
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    timeframe: str = Field(default="1m", min_length=1)
    source: str = Field(default="kraken", min_length=1)

    model_config = ConfigDict(
        # Pydantic v2 migration: renamed from orm_mode
        from_attributes=True,
        # Pydantic v2 migration: renamed from anystr_strip_whitespace
        str_strip_whitespace=True,
    )

    @validator("symbol", "timeframe", "source")
    def _ensure_upper(cls, value: str) -> str:
        return value.strip().upper()

    def to_db_kwargs(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": float(self.volume),
            "source": self.source,
            "timeframe": self.timeframe,
        }


class MobileTableColumn(BaseModel):
    """Metadata describing a mobile-friendly table column."""

    key: str
    label: str
    align: str = Field("right")


class MarketDataTableLayout(BaseModel):
    """Layout hints specific to the market data summary table."""

    visible_columns: List[MobileTableColumn]
    column_count: int
    allow_horizontal_scroll: bool
    max_visible_columns: int
    min_viewport_width: int
    gutter_spacing: int
    data_precision: int


MOBILE_TABLE_COLUMNS: List[MobileTableColumn] = [
    MobileTableColumn(key="timestamp", label="Time", align="left"),
    MobileTableColumn(key="symbol", label="Symbol", align="left"),
    MobileTableColumn(key="close", label="Last", align="right"),
    MobileTableColumn(key="volume", label="Vol", align="right"),
    MobileTableColumn(key="high", label="High", align="right"),
    MobileTableColumn(key="low", label="Low", align="right"),
]


class MarketDataService:
    """Stores OHLCV candles and enforces data retention."""

    def __init__(
        self,
        db_factory: Callable[[], Session] = SessionLocal,
        retention_days: Optional[int] = None,
    ) -> None:
        self._db_factory = db_factory
        retention_days = retention_days if retention_days is not None else DEFAULT_RETENTION_DAYS
        self._retention_days = max(0, retention_days)
        self._lock = asyncio.Lock()

    def get_mobile_table_layout(self) -> MarketDataTableLayout:
        """Return layout hints for tabular market data tailored to narrow screens."""

        hints = get_mobile_table_hints()
        column_limit = min(hints.max_visible_columns, len(MOBILE_TABLE_COLUMNS))
        if column_limit == 0:
            column_limit = 1
        return MarketDataTableLayout(
            visible_columns=MOBILE_TABLE_COLUMNS[:column_limit],
            column_count=column_limit,
            allow_horizontal_scroll=hints.allow_horizontal_scroll,
            max_visible_columns=hints.max_visible_columns,
            min_viewport_width=hints.min_viewport_width,
            gutter_spacing=hints.gutter_spacing,
            data_precision=hints.data_precision,
        )

    async def store_candle(self, candle: MarketDataCandle) -> int:
        """Store a single OHLCV candle."""

        return await self.store_candles([candle])

    async def store_candles(self, candles: Iterable[MarketDataCandle]) -> int:
        """Persist validated candles in a single transaction."""

        items: List[MarketDataCandle] = list(candles)
        if not items:
            return 0

        async with self._lock:
            return await asyncio.to_thread(self._persist_candles, items)

    def _persist_candles(self, candles: List[MarketDataCandle]) -> int:
        db = self._db_factory()
        processed = 0
        try:
            for candle in candles:
                values = candle.to_db_kwargs()
                existing = (
                    db.query(MarketData)
                    .filter_by(
                        symbol=values["symbol"],
                        timestamp=values["timestamp"],
                        timeframe=values["timeframe"],
                    )
                    .one_or_none()
                )
                if existing:
                    existing.open = values["open"]
                    existing.high = values["high"]
                    existing.low = values["low"]
                    existing.close = values["close"]
                    existing.volume = values["volume"]
                    existing.source = values["source"]
                else:
                    db.add(MarketData(**values))
                processed += 1

            if processed:
                db.commit()
            return processed
        except Exception as exc:
            db.rollback()
            logger.exception("Failed to persist market data candles: %s", exc)
            raise
        finally:
            db.close()

    async def purge_old_data(self) -> int:
        """Remove candles older than the retention window."""

        if self._retention_days <= 0:
            return 0

        cutoff = datetime.utcnow() - timedelta(days=self._retention_days)
        async with self._lock:
            return await asyncio.to_thread(self._delete_older_than, cutoff)

    def _delete_older_than(self, cutoff: datetime) -> int:
        db = self._db_factory()
        try:
            deleted = (
                db.query(MarketData)
                .filter(MarketData.timestamp < cutoff)
                .delete(synchronize_session=False)
            )
            if deleted:
                db.commit()
                logger.info("Purged %d market data rows older than %s", deleted, cutoff.isoformat())
            return deleted
        except Exception as exc:
            db.rollback()
            logger.exception("Failed to purge market data: %s", exc)
            return 0
        finally:
            db.close()

    async def fetch_recent_candles(
        self,
        symbol: str,
        reference: datetime,
        lookback: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return the latest persisted candles for a symbol up to a reference time."""

        if lookback <= 0:
            lookback = 1
        async with self._lock:
            return await asyncio.to_thread(self._load_recent_candles, symbol, reference, lookback)

    def _load_recent_candles(
        self,
        symbol: str,
        reference: datetime,
        lookback: int,
    ) -> List[Dict[str, Any]]:
        db = self._db_factory()
        try:
            rows = (
                db.query(MarketData)
                .filter(
                    MarketData.symbol == symbol,
                    MarketData.timestamp <= reference,
                )
                .order_by(MarketData.timestamp.desc())
                .limit(lookback)
                .all()
            )
            rows.reverse()
            return [
                {
                    "timestamp": entry.timestamp,
                    "open": entry.open,
                    "high": entry.high,
                    "low": entry.low,
                    "close": entry.close,
                    "volume": entry.volume,
                    "source": entry.source,
                    "timeframe": entry.timeframe,
                }
                for entry in rows
            ]
        finally:
            db.close()


    async def summarize_symbol(
        self,
        symbol: str,
        lookback: int = 20,
        reference: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Produce lightweight technical highlights for a symbol."""

        target_reference = reference or datetime.utcnow()
        sanitized = max(1, min(lookback, 200))
        candles = await self.fetch_recent_candles(symbol, target_reference, sanitized)
        return self._build_summary(symbol, candles)

    def _build_summary(self, symbol: str, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        data_points = len(candles)
        if data_points == 0:
            return {
                "symbol": symbol,
                "data_points": 0,
                "direction": "unknown",
                "last_price": None,
                "previous_price": None,
                "average": None,
                "high": None,
                "low": None,
                "momentum": None,
                "volatility": None,
                "price_range": None,
                "range_pct": None,
                "last_updated": None,
            }

        close_values: List[Decimal] = []
        high_values: List[Decimal] = []
        low_values: List[Decimal] = []
        last_updated = None

        for entry in candles:
            close_val = self._to_decimal(entry.get("close"))
            if close_val is not None:
                close_values.append(close_val)
            high_val = self._to_decimal(entry.get("high"))
            if high_val is not None:
                high_values.append(high_val)
            low_val = self._to_decimal(entry.get("low"))
            if low_val is not None:
                low_values.append(low_val)
            if entry.get("timestamp"):
                last_updated = entry["timestamp"]

        if not close_values:
            return {
                "symbol": symbol,
                "data_points": data_points,
                "direction": "unknown",
                "last_price": None,
                "previous_price": None,
                "average": None,
                "high": max(high_values) if high_values else None,
                "low": min(low_values) if low_values else None,
                "momentum": None,
                "volatility": None,
                "price_range": None,
                "range_pct": None,
                "last_updated": last_updated,
            }

        last_price = close_values[-1]
        previous_price = close_values[-2] if len(close_values) > 1 else last_price
        average = sum(close_values, Decimal("0")) / Decimal(len(close_values))
        high = max(high_values) if high_values else None
        low = min(low_values) if low_values else None
        direction = "unknown"
        if last_price is not None and previous_price is not None:
            if last_price > previous_price:
                direction = "rising"
            elif last_price < previous_price:
                direction = "falling"
            else:
                direction = "flat"

        momentum = None
        if previous_price and previous_price != Decimal("0"):
            momentum = (last_price - previous_price) / previous_price

        price_range = None
        if high is not None and low is not None:
            price_range = high - low

        volatility = None
        range_pct = None
        if average and price_range is not None:
            if average != Decimal("0"):
                volatility = price_range / average
                range_pct = volatility

        return {
            "symbol": symbol,
            "data_points": data_points,
            "direction": direction,
            "last_price": last_price,
            "previous_price": previous_price,
            "average": average,
            "high": high,
            "low": low,
            "momentum": momentum,
            "volatility": volatility,
            "price_range": price_range,
            "range_pct": range_pct,
            "last_updated": last_updated,
        }

    @staticmethod
    def _to_decimal(value: Any) -> Optional[Decimal]:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (TypeError, ValueError, ArithmeticError):
            return None


market_data_service = MarketDataService()
