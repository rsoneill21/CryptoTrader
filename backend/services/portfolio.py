"""Cached balance snapshot service backed by Kraken."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from decimal import Decimal
from pydantic import BaseModel

from services.kraken import Balance, KrakenAPIError, kraken_service

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(seconds=60)


class PortfolioHolding(BaseModel):
    """Single asset holding details."""

    asset: str
    total: Decimal
    available: Decimal
    reserved: Decimal


class PortfolioSnapshot(BaseModel):
    """Snapshot of the current portfolio holdings."""

    holdings: list[PortfolioHolding]
    fetched_at: datetime
    expires_at: Optional[datetime]
    ttl_seconds: int
    source: str = "kraken"


class PortfolioService:
    """Fetches Kraken balances and keeps a cached snapshot."""

    def __init__(self, cache_ttl: timedelta = CACHE_TTL):
        self._cache_ttl = cache_ttl
        self._snapshot: Optional[PortfolioSnapshot] = None
        self._lock = asyncio.Lock()

    @property
    def _ttl_seconds(self) -> int:
        return int(self._cache_ttl.total_seconds())

    def _build_snapshot(self, balances: Dict[str, Balance], fetched_at: datetime) -> PortfolioSnapshot:
        holdings = [
            PortfolioHolding(
                asset=balance.asset,
                total=balance.total,
                available=balance.available,
                reserved=balance.reserved,
            )
            for balance in sorted(balances.values(), key=lambda b: b.asset)
        ]
        expires_at = fetched_at + self._cache_ttl
        return PortfolioSnapshot(
            holdings=holdings,
            fetched_at=fetched_at,
            expires_at=expires_at,
            ttl_seconds=self._ttl_seconds,
        )

    async def _fetch_snapshot(self) -> PortfolioSnapshot:
        fetched_at = datetime.utcnow()
        balances = await kraken_service.get_balance()
        return self._build_snapshot(balances, fetched_at)

    async def get_snapshot(self, force_refresh: bool = False) -> PortfolioSnapshot:
        """Return a cached snapshot, refreshing from Kraken when needed."""

        async with self._lock:
            now = datetime.utcnow()
            should_refresh = (
                force_refresh
                or self._snapshot is None
                or (self._snapshot.expires_at is not None and now >= self._snapshot.expires_at)
            )
            if should_refresh:
                try:
                    self._snapshot = await self._fetch_snapshot()
                except KrakenAPIError as exc:
                    if self._snapshot:
                        logger.warning("Kraken balance fetch failed, returning cached snapshot: %s", exc)
                        return self._snapshot
                    raise
            return self._snapshot


portfolio_service = PortfolioService()
