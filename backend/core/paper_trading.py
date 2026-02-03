"""Paper trading engine that simulates virtual positions and P&L."""

from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator, validator

from db.database import SessionLocal
from db.models import Trade

logger = logging.getLogger(__name__)


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TradeIntent(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"


class PaperTradeSignal(BaseModel):
    """Signal that tells the engine when to open or close a virtual position."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str = Field(..., min_length=1)
    intent: TradeIntent = TradeIntent.ENTRY
    side: Optional[TradeSide] = None
    quantity: float = Field(gt=0)
    price: Optional[float] = Field(default=None, gt=0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    strategy_id: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator("symbol")
    def _normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    # Pydantic v2 migration: replaced @root_validator with @model_validator(mode='after')
    @model_validator(mode="after")
    def _require_side_for_entry(self) -> "PaperTradeSignal":
        if self.intent == TradeIntent.ENTRY and self.side is None:
            raise ValueError("side is required when intent is entry")
        return self


class PaperPosition(BaseModel):
    """Snapshot of an open position in the paper portfolio."""

    symbol: str
    side: TradeSide
    quantity: float
    entry_price: float
    entry_time: datetime
    strategy_id: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    last_price: Optional[float] = None
    unrealized_pnl: float = 0.0


class PaperTradeResult(BaseModel):
    """Completed trade information for recording performance."""

    symbol: str
    side: TradeSide
    quantity: float
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    fees: float = 0.0
    strategy_id: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PaperPortfolioSnapshot(BaseModel):
    """Portfolio-level summary that can be surfaced to the UI or other agents."""

    cash: float
    realized_pnl: float
    unrealized_pnl: float
    equity: float
    open_positions: List[PaperPosition]
    price_book: Dict[str, float]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaperStrategyPerformanceSummary(BaseModel):
    """Aggregated paper trading performance for a single strategy."""

    strategy_id: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: Optional[float]
    latest_trade_time: Optional[datetime]
    current_equity: float
    recent_pnl_samples: List[float] = Field(default_factory=list)


@dataclass
class _MutablePosition:
    symbol: str
    side: TradeSide
    entry_price: float
    entry_time: datetime
    strategy_id: Optional[int]
    metadata: Dict[str, Any]
    quantity: float

    def snapshot(self, last_price: Optional[float], unrealized: float) -> PaperPosition:
        return PaperPosition(
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            entry_price=self.entry_price,
            entry_time=self.entry_time,
            strategy_id=self.strategy_id,
            metadata=dict(self.metadata),
            last_price=last_price,
            unrealized_pnl=unrealized,
        )


@dataclass
class _StrategyMetricsState:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    equity: float = 0.0
    peak_equity: float = 0.0
    max_drawdown: float = 0.0
    last_trade_at: Optional[datetime] = None
    pnl_sum_of_squares: float = 0.0
    recent_trade_pnls: Deque[float] = field(default_factory=lambda: deque(maxlen=20))


class PaperTradingEngine:
    """Simulates trade execution and tracks virtual positions + P&L."""

    def __init__(
        self,
        starting_cash: float = 100_000.0,
        db_factory: Callable[[], Any] = SessionLocal,
    ) -> None:
        self._lock = asyncio.Lock()
        self._starting_cash = starting_cash
        self._cash = starting_cash
        self._realized_pnl = 0.0
        self._unrealized_pnl = 0.0
        self._positions: Dict[str, List[_MutablePosition]] = defaultdict(list)
        self._price_book: Dict[str, float] = {}
        self._strategy_metrics: Dict[int, _StrategyMetricsState] = {}
        self._db_factory = db_factory

    async def execute_signal(self, signal: PaperTradeSignal) -> List[PaperTradeResult]:
        """Handle a paper trading signal (entry or exit) asynchronously."""

        async with self._lock:
            price = self._resolve_price(signal.symbol, signal.price)
            if signal.intent == TradeIntent.ENTRY:
                self._open_position(signal, price)
                return []
            return self._close_positions(signal, price)

    async def update_market_price(self, symbol: str, price: float) -> None:
        """Refresh the last known market price for a symbol."""

        normalized_symbol = self._normalize_symbol(symbol)
        normalized_price = float(price)
        if normalized_price <= 0:
            raise ValueError("price must be greater than zero")

        async with self._lock:
            self._price_book[normalized_symbol] = normalized_price
            self._recalculate_unrealized()

    async def persist_closed_trades(self, trades: Iterable[PaperTradeResult]) -> int:
        """Save completed paper trades to the database in a background thread."""

        persisted = await asyncio.to_thread(self._persist_trades, list(trades))
        return persisted

    async def snapshot(self) -> PaperPortfolioSnapshot:
        """Return a snapshot of the virtual portfolio state."""

        async with self._lock:
            position_snapshots: List[PaperPosition] = []
            for symbol, positions in self._positions.items():
                last_price = self._price_book.get(symbol)
                for pos in positions:
                    unrealized = 0.0
                    if last_price is not None:
                        unrealized = self._calculate_pnl(pos.side, pos.entry_price, last_price, pos.quantity)
                    position_snapshots.append(pos.snapshot(last_price, unrealized))

            equity = self._cash + self._realized_pnl + self._unrealized_pnl
            return PaperPortfolioSnapshot(
                cash=self._cash,
                realized_pnl=self._realized_pnl,
                unrealized_pnl=self._unrealized_pnl,
                equity=equity,
                open_positions=position_snapshots,
                price_book=dict(self._price_book),
            )

    def _open_position(self, signal: PaperTradeSignal, price: float) -> None:
        entry = _MutablePosition(
            symbol=signal.symbol,
            side=signal.side,  # type: ignore[arg-type]
            entry_price=price,
            entry_time=signal.timestamp,
            strategy_id=signal.strategy_id,
            metadata=dict(signal.metadata),
            quantity=signal.quantity,
        )
        self._positions[entry.symbol].append(entry)
        self._recalculate_unrealized()

    def _close_positions(self, signal: PaperTradeSignal, price: float) -> List[PaperTradeResult]:
        symbol_positions = self._positions.get(signal.symbol)
        if not symbol_positions:
            raise ValueError("no open positions to close for %s" % signal.symbol)

        remaining = signal.quantity
        results: List[PaperTradeResult] = []
        now = signal.timestamp

        while remaining > 0 and symbol_positions:
            position = symbol_positions[0]
            closing_qty = min(position.quantity, remaining)
            pnl = self._calculate_pnl(position.side, position.entry_price, price, closing_qty)
            self._realized_pnl += pnl
            self._cash += pnl

            result = PaperTradeResult(
                symbol=signal.symbol,
                side=position.side,
                quantity=closing_qty,
                entry_price=position.entry_price,
                exit_price=price,
                entry_time=position.entry_time,
                exit_time=now,
                pnl=pnl,
                strategy_id=position.strategy_id,
                metadata=dict(position.metadata),
            )
            results.append(result)
            self._record_strategy_metrics(result)

            position.quantity -= closing_qty
            remaining -= closing_qty

            if position.quantity <= 0:
                symbol_positions.pop(0)

        if remaining > 0:
            raise ValueError("requested quantity exceeds open position quantity")

        if not symbol_positions:
            self._positions.pop(signal.symbol, None)

        self._recalculate_unrealized()
        return results

    def _record_strategy_metrics(self, result: PaperTradeResult) -> None:
        if result.strategy_id is None:
            return

        metrics = self._strategy_metrics.setdefault(result.strategy_id, _StrategyMetricsState())
        metrics.total_trades += 1
        if result.pnl > 0:
            metrics.winning_trades += 1
        elif result.pnl < 0:
            metrics.losing_trades += 1
        metrics.total_pnl += result.pnl
        metrics.equity += result.pnl
        metrics.peak_equity = max(metrics.peak_equity, metrics.equity)
        drawdown = metrics.peak_equity - metrics.equity
        metrics.max_drawdown = max(metrics.max_drawdown, drawdown)
        metrics.last_trade_at = result.exit_time
        metrics.pnl_sum_of_squares += result.pnl * result.pnl
        metrics.recent_trade_pnls.append(result.pnl)

    def _calculate_pnl(
        self, side: TradeSide, entry_price: float, exit_price: float, quantity: float
    ) -> float:
        if side == TradeSide.BUY:
            return (exit_price - entry_price) * quantity
        return (entry_price - exit_price) * quantity

    def _recalculate_unrealized(self) -> None:
        total = 0.0
        for symbol, positions in self._positions.items():
            price = self._price_book.get(symbol)
            if price is None:
                continue
            for position in positions:
                total += self._calculate_pnl(position.side, position.entry_price, price, position.quantity)
        self._unrealized_pnl = total

    def _resolve_price(self, symbol: str, candidate_price: Optional[float]) -> float:
        if candidate_price is not None:
            return float(candidate_price)
        known_price = self._price_book.get(symbol)
        if known_price is None:
            raise ValueError("price is required when no market price is cached for %s" % symbol)
        return known_price

    async def strategy_performance_summary(self, strategy_id: int) -> Optional[PaperStrategyPerformanceSummary]:
        """Return the calculated metrics for a specific strategy."""

        async with self._lock:
            metrics = self._strategy_metrics.get(strategy_id)
            if not metrics or metrics.total_trades == 0:
                return None
            return self._build_performance_summary(strategy_id, metrics)

    def _build_performance_summary(
        self, strategy_id: int, metrics: _StrategyMetricsState
    ) -> PaperStrategyPerformanceSummary:
        win_rate = metrics.winning_trades / metrics.total_trades
        return PaperStrategyPerformanceSummary(
            strategy_id=strategy_id,
            total_trades=metrics.total_trades,
            winning_trades=metrics.winning_trades,
            losing_trades=metrics.losing_trades,
            win_rate=win_rate,
            total_pnl=metrics.total_pnl,
            max_drawdown=metrics.max_drawdown,
            sharpe_ratio=self._calculate_sharpe_ratio(metrics),
            latest_trade_time=metrics.last_trade_at,
            current_equity=metrics.equity,
            recent_pnl_samples=list(metrics.recent_trade_pnls),
        )

    def _calculate_sharpe_ratio(self, metrics: _StrategyMetricsState) -> Optional[float]:
        if metrics.total_trades < 2:
            return None
        mean = metrics.total_pnl / metrics.total_trades
        variance = (metrics.pnl_sum_of_squares / metrics.total_trades) - (mean * mean)
        if variance <= 0:
            return None
        stddev = math.sqrt(variance)
        if stddev <= 0:
            return None
        return mean / stddev

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.strip().upper()

    def _persist_trades(self, trades: List[PaperTradeResult]) -> int:
        if not trades:
            return 0

        db = self._db_factory()
        persisted = 0
        try:
            for trade in trades:
                db_trade = Trade(
                    strategy_id=trade.strategy_id,
                    is_paper=True,
                    symbol=trade.symbol,
                    side=trade.side.value,
                    entry_price=trade.entry_price,
                    exit_price=trade.exit_price,
                    quantity=trade.quantity,
                    pnl=trade.pnl,
                    fees=trade.fees,
                    entry_time=trade.entry_time,
                    exit_time=trade.exit_time,
                    entry_reasoning_json=trade.metadata.get("entry_reasoning"),
                    exit_reasoning_json=trade.metadata.get("exit_reasoning"),
                    market_conditions_json=trade.metadata.get("market_conditions"),
                    indicators_json=trade.metadata.get("indicators"),
                )
                db.add(db_trade)
                persisted += 1
            if persisted > 0:
                db.commit()
            return persisted
        except Exception as exc:
            db.rollback()
            logger.exception("Failed to persist paper trades: %s", exc)
            return 0
        finally:
            db.close()


__all__ = [
    "PaperTradingEngine",
    "PaperTradeSignal",
    "PaperPosition",
    "PaperTradeResult",
    "PaperPortfolioSnapshot",
    "PaperStrategyPerformanceSummary",
    "TradeSide",
    "TradeIntent",
]
