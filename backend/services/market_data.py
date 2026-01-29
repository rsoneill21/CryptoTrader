"""Market data persistence helpers."""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable, Iterable, List, Optional

from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from db.database import SessionLocal
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

    class Config:
        orm_mode = True
        anystr_strip_whitespace = True

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


market_data_service = MarketDataService()
