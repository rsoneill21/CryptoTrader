"""Manual trade detection helpers for CryptoTrader.

This service is responsible for reconciling Kraken trade history with the internal
trade/order records and marking anything the system did not originate as a manual
trade (`is_manual=True`)."""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set

from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import Order, Trade
from services.kraken import KrakenAPIError, KrakenService, kraken_service

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_MINUTES = 60
MATCH_WINDOW = timedelta(minutes=1)
PRICE_TOLERANCE = 0.05
QUANTITY_TOLERANCE = 1e-6


class KrakenTradeSummary(BaseModel):
    """Normalised data returned from Kraken trade history."""

    trade_id: str
    order_id: Optional[str]
    symbol: str
    side: str
    price: Decimal
    volume: Decimal
    cost: Decimal
    fee: Decimal
    timestamp: datetime


class ManualTradeSyncReport(BaseModel):
    """Summary of a manual trade synchronization run."""

    start_time: datetime
    end_time: datetime
    inspected: int
    manual_detected: int
    manual_trade_ids: List[int]
    manual_trades: List[KrakenTradeSummary]


class ManualTradeSyncService:
    """Service that flags Kraken trades the system did not initiate."""

    def __init__(
        self,
        db_factory: Callable[[], Session] = SessionLocal,
        kraken: KrakenService = kraken_service,
        lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
        match_window: timedelta = MATCH_WINDOW,
        price_tolerance: float = PRICE_TOLERANCE,
        quantity_tolerance: float = QUANTITY_TOLERANCE,
    ) -> None:
        self._db_factory = db_factory
        self._kraken = kraken
        self._lookback_minutes = max(1, lookback_minutes)
        self._match_window = match_window
        self._price_tolerance = price_tolerance
        self._quantity_tolerance = quantity_tolerance

    async def detect_manual_trades(
        self,
        lookback_minutes: Optional[int] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
    ) -> ManualTradeSyncReport:
        """Fetch Kraken trade history and flag unmatched rows as manual."""

        resolved_lookback = max(1, lookback_minutes or self._lookback_minutes)
        start_ts, end_ts = self._resolve_time_window(resolved_lookback, start, end)
        logger.debug("Running manual trade sync for window %s-%s", start_ts, end_ts)

        try:
            trades = await self._fetch_trade_history(start_ts, end_ts)
        except KrakenAPIError:
            logger.exception("Unable to fetch Kraken trade history")
            raise

        system_order_ids = await asyncio.to_thread(self._load_system_order_ids)
        manual_trade_ids: List[int] = []
        manual_trades: List[KrakenTradeSummary] = []

        for trade in trades:
            if trade.order_id and trade.order_id in system_order_ids:
                continue

            recorded_trade = await asyncio.to_thread(self._ensure_manual_trade, trade)
            if recorded_trade:
                manual_trade_ids.append(recorded_trade.id)
                manual_trades.append(trade)

        start_dt = datetime.utcfromtimestamp(start_ts)
        end_dt = datetime.utcfromtimestamp(end_ts)
        logger.info(
            "Manual trade sync inspected %d Kraken trades and flagged %d manual entries between %s and %s",
            len(trades),
            len(manual_trade_ids),
            start_dt.isoformat(),
            end_dt.isoformat(),
        )

        return ManualTradeSyncReport(
            start_time=start_dt,
            end_time=end_dt,
            inspected=len(trades),
            manual_detected=len(manual_trade_ids),
            manual_trade_ids=manual_trade_ids,
            manual_trades=manual_trades,
        )

    def _resolve_time_window(
        self,
        lookback_minutes: int,
        provided_start: Optional[int],
        provided_end: Optional[int],
    ) -> tuple[int, int]:
        now_ts = int(datetime.utcnow().timestamp())
        end_ts = provided_end or now_ts
        start_ts = provided_start if provided_start is not None else end_ts - lookback_minutes * 60

        if start_ts >= end_ts:
            start_ts = end_ts - max(60, lookback_minutes * 60)

        return max(0, start_ts), end_ts

    async def _fetch_trade_history(self, start: int, end: int) -> List[KrakenTradeSummary]:
        raw_trades = await self._kraken.get_trade_history(start=start, end=end)
        return [self._build_trade_summary(record) for record in raw_trades]

    def _build_trade_summary(self, raw: Dict[str, Any]) -> KrakenTradeSummary:
        timestamp = raw.get("timestamp")
        if not isinstance(timestamp, datetime):
            timestamp = datetime.utcfromtimestamp(timestamp or 0)

        return KrakenTradeSummary(
            trade_id=str(raw.get("trade_id", "")),
            order_id=str(raw["order_id"]) if raw.get("order_id") else None,
            symbol=raw.get("symbol", ""),
            side=raw.get("side", "buy"),
            price=raw.get("price", Decimal("0")) or Decimal("0"),
            volume=raw.get("volume", Decimal("0")) or Decimal("0"),
            cost=raw.get("cost", Decimal("0")) or Decimal("0"),
            fee=raw.get("fee", Decimal("0")) or Decimal("0"),
            timestamp=timestamp,
        )

    def _load_system_order_ids(self) -> Set[str]:
        db = self._db_factory()
        try:
            orders = (
                db.query(Order)
                .filter(Order.exchange_order_id.isnot(None))
                .all()
            )
            return {order.exchange_order_id for order in orders if order.exchange_order_id}
        finally:
            db.close()

    def _ensure_manual_trade(self, trade_summary: KrakenTradeSummary) -> Optional[Trade]:
        db = self._db_factory()
        try:
            existing = self._find_matching_trade(db, trade_summary)
            if existing:
                updated = False
                if not existing.is_manual:
                    existing.is_manual = True
                    updated = True
                if existing.is_paper:
                    existing.is_paper = False
                    updated = True
                if updated:
                    db.commit()
                    db.refresh(existing)
                    return existing
                return None

            return self._create_manual_trade(db, trade_summary)
        except Exception as exc:
            logger.exception("Failed to persist manual trade %s: %s", trade_summary.trade_id, exc)
            db.rollback()
            return None
        finally:
            db.close()

    def _find_matching_trade(
        self, db: Session, trade_summary: KrakenTradeSummary
    ) -> Optional[Trade]:
        if not trade_summary.timestamp:
            return None

        left_bound = trade_summary.timestamp - self._match_window
        right_bound = trade_summary.timestamp + self._match_window
        candidates = (
            db.query(Trade)
            .filter(
                Trade.symbol == trade_summary.symbol,
                Trade.side == trade_summary.side,
                Trade.entry_time >= left_bound,
                Trade.entry_time <= right_bound,
            )
            .all()
        )

        for candidate in candidates:
            if candidate.entry_price is None or candidate.quantity is None:
                continue
            if not self._within_tolerance(
                float(candidate.entry_price),
                float(trade_summary.price),
                self._price_tolerance,
            ):
                continue
            if not self._within_tolerance(
                float(candidate.quantity),
                float(trade_summary.volume),
                self._quantity_tolerance,
            ):
                continue
            return candidate
        return None

    def _create_manual_trade(self, db: Session, summary: KrakenTradeSummary) -> Optional[Trade]:
        trade = Trade(
            symbol=summary.symbol,
            side=summary.side,
            entry_price=float(summary.price),
            quantity=float(summary.volume),
            entry_time=summary.timestamp,
            fees=float(summary.fee),
            is_paper=False,
            is_manual=True,
        )

        db.add(trade)
        db.commit()
        db.refresh(trade)
        return trade

    @staticmethod
    def _within_tolerance(value: float, target: float, tolerance: float) -> bool:
        return abs(value - target) <= tolerance


manual_trade_sync_service = ManualTradeSyncService()
