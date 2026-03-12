"""Paper trading engine that simulates virtual positions and P&L."""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator, validator

from db.database import SessionLocal, AsyncSessionLocal
from db.models import RiskSettings, Trade
from services.paper_trading_state import PaperTradingStateService

from core.indicators import indicator_snapshot

_PRICE_HISTORY_MAXLEN = 200
_NEAR_MISS_THRESHOLD = 0.002

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
    stop_loss: Optional[float] = Field(default=None, gt=0)
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
    stop_loss_price: Optional[float] = None
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
    stop_loss_price: Optional[float] = None

    def snapshot(self, last_price: Optional[float], unrealized: float) -> PaperPosition:
        return PaperPosition(
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            entry_price=self.entry_price,
            entry_time=self.entry_time,
            strategy_id=self.strategy_id,
            metadata=dict(self.metadata),
            stop_loss_price=self.stop_loss_price,
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
        async_session_factory: Callable[[], Any] = AsyncSessionLocal,
        session_id: Optional[str] = None,
        state_service: Optional[PaperTradingStateService] = None,
    ) -> None:
        self._lock = asyncio.Lock()
        self._starting_cash = starting_cash
        self._cash = starting_cash
        self._realized_pnl = 0.0
        self._unrealized_pnl = 0.0
        self._positions: Dict[str, List[_MutablePosition]] = defaultdict(list)
        self._price_book: Dict[str, float] = {}
        self._price_history: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=_PRICE_HISTORY_MAXLEN)
        )
        self._strategy_metrics: Dict[int, _StrategyMetricsState] = {}
        self._db_factory = db_factory
        self._async_session_factory = async_session_factory
        self._session_id = session_id or str(uuid.uuid4())
        self._state_service = state_service or PaperTradingStateService()
        self._persistence_enabled = True
        self._last_persistence_time: Optional[datetime] = None

    async def execute_signal(self, signal: PaperTradeSignal) -> List[PaperTradeResult]:
        """Handle a paper trading signal (entry or exit) asynchronously."""

        async with self._lock:
            price = self._resolve_price(signal.symbol, signal.price)
            context = self._build_decision_context(signal, price)
            self._apply_decision_context(signal, context)
            self._record_price(signal.symbol, price)
            if signal.intent == TradeIntent.ENTRY:
                self._open_position(signal, price)
                results = []
            else:
                results = self._close_positions(signal, price, context)

        # Persist state after signal execution (outside lock to avoid blocking)
        await self.persist_state()
        return results

    async def update_market_price(self, symbol: str, price: float) -> None:
        """Refresh the last known market price for a symbol."""

        normalized_symbol = self._normalize_symbol(symbol)
        normalized_price = float(price)
        if normalized_price <= 0:
            raise ValueError("price must be greater than zero")

        stop_loss_results: List[PaperTradeResult] = []

        async with self._lock:
            self._price_book[normalized_symbol] = normalized_price
            self._record_price(normalized_symbol, normalized_price)
            self._recalculate_unrealized()

            symbol_positions = self._positions.get(normalized_symbol, [])
            if symbol_positions:
                triggered_positions = [
                    position
                    for position in list(symbol_positions)
                    if self._is_stop_loss_triggered(position, normalized_price)
                ]
                for position in triggered_positions:
                    result = self._close_position_for_stop_loss(
                        normalized_symbol,
                        position,
                        normalized_price,
                    )
                    stop_loss_results.append(result)
                if stop_loss_results:
                    if not symbol_positions:
                        self._positions.pop(normalized_symbol, None)
                    self._recalculate_unrealized()

        if stop_loss_results:
            await self.persist_closed_trades(stop_loss_results)
            await self.persist_state()
            return

        # Periodically persist state (every 10th price update to avoid excessive writes)
        # Can be optimized with time-based throttling if needed
        if len(self._price_book) % 10 == 0:
            await self.persist_state()

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

    async def get_cached_price(self, symbol: str) -> Optional[float]:
        """Return the latest cached market price for a symbol if available."""

        normalized_symbol = self._normalize_symbol(symbol)
        async with self._lock:
            return self._price_book.get(normalized_symbol)

    def _open_position(self, signal: PaperTradeSignal, price: float) -> None:
        stop_loss_price = self._resolve_stop_loss_price(signal, price)
        entry = _MutablePosition(
            symbol=signal.symbol,
            side=signal.side,  # type: ignore[arg-type]
            entry_price=price,
            entry_time=signal.timestamp,
            strategy_id=signal.strategy_id,
            metadata=dict(signal.metadata),
            quantity=signal.quantity,
            stop_loss_price=stop_loss_price,
        )
        self._positions[entry.symbol].append(entry)
        self._recalculate_unrealized()

    def _resolve_stop_loss_price(self, signal: PaperTradeSignal, entry_price: float) -> Optional[float]:
        if signal.stop_loss is not None:
            return float(signal.stop_loss)

        default_stop_loss_pct = self._load_default_stop_loss_pct()
        if default_stop_loss_pct <= 0:
            return None

        multiplier = default_stop_loss_pct / 100.0
        if signal.side == TradeSide.BUY:
            return entry_price * (1.0 - multiplier)
        return entry_price * (1.0 + multiplier)

    def _load_default_stop_loss_pct(self) -> float:
        db = self._db_factory()
        try:
            settings = (
                db.query(RiskSettings)
                .order_by(RiskSettings.updated_at.desc())
                .first()
            )
            if settings is None:
                return 0.0
            return float(settings.default_stop_loss_pct or 0.0)
        except Exception as exc:
            logger.warning("Unable to load default stop loss setting: %s", exc)
            return 0.0
        finally:
            db.close()

    def _is_stop_loss_triggered(self, position: _MutablePosition, price: float) -> bool:
        if position.stop_loss_price is None:
            return False
        if position.side == TradeSide.BUY:
            return price <= position.stop_loss_price
        return price >= position.stop_loss_price

    def _close_position_for_stop_loss(
        self,
        symbol: str,
        position: _MutablePosition,
        price: float,
    ) -> PaperTradeResult:
        pnl = self._calculate_pnl(position.side, position.entry_price, price, position.quantity)
        self._realized_pnl += pnl
        self._cash += pnl

        stop_loss_reason = {
            "summary": "Stop-Loss Triggered",
            "trigger_price": price,
            "stop_loss_price": position.stop_loss_price,
        }

        exit_metadata = dict(position.metadata)
        exit_metadata["exit_reasoning"] = stop_loss_reason
        exit_metadata["market_conditions_exit"] = {
            "trigger": "stop_loss",
            "price": price,
            "stop_loss_price": position.stop_loss_price,
        }
        exit_metadata["indicators_exit"] = None
        exit_metadata["near_miss_exit"] = {
            "flag": False,
            "threshold": None,
            "reason": "stop loss trigger",
            "change_pct": None,
        }

        result = PaperTradeResult(
            symbol=symbol,
            side=position.side,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=price,
            entry_time=position.entry_time,
            exit_time=datetime.utcnow(),
            pnl=pnl,
            strategy_id=position.strategy_id,
            metadata=exit_metadata,
        )
        self._record_strategy_metrics(result)

        symbol_positions = self._positions.get(symbol, [])
        try:
            symbol_positions.remove(position)
        except ValueError:
            pass
        return result

    def _close_positions(
        self, signal: PaperTradeSignal, price: float, context: Dict[str, Any]
    ) -> List[PaperTradeResult]:
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

            exit_metadata = dict(position.metadata)
            exit_metadata["exit_reasoning"] = context.get("reasoning", {})
            exit_metadata["market_conditions_exit"] = context.get("market_conditions")
            exit_metadata["indicators_exit"] = context.get("indicators")
            exit_metadata["near_miss_exit"] = context.get("near_miss")

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
                metadata=exit_metadata,
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

    def _build_decision_context(self, signal: PaperTradeSignal, price: float) -> Dict[str, Any]:
        symbol = self._normalize_symbol(signal.symbol)
        history = list(self._price_history.get(symbol, []))
        recent_slice = history[-10:]
        last_price = recent_slice[-1] if recent_slice else None
        momentum: Optional[float] = None
        if last_price:
            if last_price != 0:
                momentum = (price - last_price) / last_price

        volatility = self._calculate_volatility(recent_slice)
        snapshot = indicator_snapshot(history[-60:])

        direction = "flat"
        if momentum is not None:
            if momentum > 0:
                direction = "bullish"
            elif momentum < 0:
                direction = "bearish"

        recent_low = min(recent_slice) if recent_slice else None
        recent_high = max(recent_slice) if recent_slice else None
        range_pct = None
        if recent_low and recent_high and recent_low > 0:
            range_pct = (recent_high - recent_low) / recent_low

        summary = f"{signal.intent.value.capitalize()} {signal.quantity} {signal.side.value if signal.side else 'position'} @ {price:.2f}"

        near_miss_flag = momentum is not None and abs(momentum) < _NEAR_MISS_THRESHOLD
        near_miss_reason = (
            f"momentum of {momentum:.4f} was within the {int(_NEAR_MISS_THRESHOLD * 100)}% threshold"
            if near_miss_flag
            else "price movement decisively moved beyond the threshold"
        )

        reasoning = {
            "intent": signal.intent.value,
            "side": signal.side.value if signal.side else None,
            "price": price,
            "quantity": signal.quantity,
            "momentum": momentum,
            "last_price": last_price,
            "summary": summary,
            "recent_prices": recent_slice,
        }

        market_conditions = {
            "direction": direction,
            "volatility": volatility,
            "recent_price_low": recent_low,
            "recent_price_high": recent_high,
            "range_pct": range_pct,
            "history_length": len(history),
        }

        near_miss = {
            "flag": near_miss_flag,
            "threshold": _NEAR_MISS_THRESHOLD,
            "reason": near_miss_reason,
            "change_pct": momentum,
        }

        return {
            "reasoning": reasoning,
            "market_conditions": market_conditions,
            "indicators": snapshot,
            "near_miss": near_miss,
        }

    def _apply_decision_context(self, signal: PaperTradeSignal, context: Dict[str, Any]) -> None:
        metadata = signal.metadata
        if signal.intent == TradeIntent.ENTRY:
            metadata["entry_reasoning"] = context["reasoning"]
            metadata["market_conditions_entry"] = context["market_conditions"]
            metadata["indicators_entry"] = context["indicators"]
            metadata["near_miss_entry"] = context["near_miss"]
        else:
            metadata["exit_reasoning"] = context["reasoning"]
            metadata["market_conditions_exit"] = context["market_conditions"]
            metadata["indicators_exit"] = context["indicators"]
            metadata["near_miss_exit"] = context["near_miss"]
        metadata["market_conditions"] = context["market_conditions"]
        metadata["indicators"] = context["indicators"]
        metadata["near_miss"] = context["near_miss"]

    def _record_price(self, symbol: str, price: float) -> None:
        normalized = self._normalize_symbol(symbol)
        self._price_history[normalized].append(float(price))

    def _calculate_volatility(self, values: List[float]) -> Optional[float]:
        if len(values) < 2:
            return None
        average = sum(values) / len(values)
        variance = sum((value - average) ** 2 for value in values) / len(values)
        return math.sqrt(variance)

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

    async def load_state_from_db(self) -> bool:
        """
        Load paper trading state from database.

        Returns:
            True if state was loaded, False if no state found or error occurred.
        """
        if not self._persistence_enabled:
            logger.info("Persistence disabled, skipping state load")
            return False

        try:
            async with self._async_session_factory() as session:
                state_data = await self._state_service.load_active_session(session)

                if not state_data:
                    logger.info("No active session found, starting fresh")
                    return False

                # Restore state from JSON
                async with self._lock:
                    self._session_id = state_data.get("session_id", self._session_id)
                    self._cash = state_data.get("cash", self._starting_cash)
                    self._realized_pnl = state_data.get("realized_pnl", 0.0)
                    self._unrealized_pnl = state_data.get("unrealized_pnl", 0.0)
                    self._price_book = state_data.get("price_book", {})

                    # Restore positions
                    self._positions.clear()
                    for symbol, pos_list in state_data.get("positions", {}).items():
                        for pos_data in pos_list:
                            pos = _MutablePosition(
                                symbol=pos_data["symbol"],
                                side=TradeSide(pos_data["side"]),
                                entry_price=pos_data["entry_price"],
                                entry_time=datetime.fromisoformat(pos_data["entry_time"]),
                                strategy_id=pos_data.get("strategy_id"),
                                metadata=pos_data.get("metadata", {}),
                                quantity=pos_data["quantity"],
                                stop_loss_price=pos_data.get("stop_loss_price"),
                            )
                            self._positions[symbol].append(pos)

                    # Restore price history (limited to maxlen)
                    for symbol, prices in state_data.get("price_history", {}).items():
                        self._price_history[symbol] = deque(prices, maxlen=_PRICE_HISTORY_MAXLEN)

                    logger.info(
                        "Loaded paper trading session %s: cash=%.2f, positions=%d, realized_pnl=%.2f",
                        self._session_id,
                        self._cash,
                        sum(len(p) for p in self._positions.values()),
                        self._realized_pnl
                    )
                    return True

        except Exception as exc:
            logger.exception("Failed to load paper trading state: %s", exc)
            return False

    async def persist_state(self) -> bool:
        """
        Save current paper trading state to database.

        Returns:
            True if state was saved, False otherwise.
        """
        if not self._persistence_enabled:
            return False

        try:
            async with self._lock:
                # Serialize positions
                positions_data = {}
                for symbol, pos_list in self._positions.items():
                    positions_data[symbol] = [
                        {
                            "symbol": pos.symbol,
                            "side": pos.side.value,
                            "quantity": pos.quantity,
                            "entry_price": pos.entry_price,
                            "entry_time": pos.entry_time.isoformat(),
                            "strategy_id": pos.strategy_id,
                            "metadata": pos.metadata,
                            "stop_loss_price": pos.stop_loss_price,
                        }
                        for pos in pos_list
                    ]

                # Serialize price history
                price_history_data = {
                    symbol: list(prices)
                    for symbol, prices in self._price_history.items()
                }

                state_payload = {
                    "session_id": self._session_id,
                    "cash": self._cash,
                    "realized_pnl": self._realized_pnl,
                    "unrealized_pnl": self._unrealized_pnl,
                    "positions": positions_data,
                    "price_book": self._price_book,
                    "price_history": price_history_data,
                    "starting_cash": self._starting_cash,
                    "timestamp": datetime.utcnow().isoformat()
                }

            async with self._async_session_factory() as session:
                success = await self._state_service.save_state(
                    session,
                    self._session_id,
                    state_payload
                )

                if success:
                    self._last_persistence_time = datetime.utcnow()
                    logger.debug("Persisted paper trading state for session %s", self._session_id)

                return success

        except Exception as exc:
            logger.exception("Failed to persist paper trading state: %s", exc)
            return False

    async def archive_current_session(self) -> bool:
        """
        Archive the current session (mark as inactive).

        Returns:
            True if session was archived, False otherwise.
        """
        try:
            async with self._async_session_factory() as session:
                success = await self._state_service.archive_session(session, self._session_id)
                if success:
                    logger.info("Archived paper trading session %s", self._session_id)
                return success
        except Exception as exc:
            logger.exception("Failed to archive session: %s", exc)
            return False

    async def reset_to_clean_state(self, archive_current: bool = True) -> None:
        """
        Reset engine to a clean state, optionally archiving current session.

        Args:
            archive_current: If True, archive current session before reset
        """
        async with self._lock:
            if archive_current:
                await self.archive_current_session()

            # Generate new session ID
            self._session_id = str(uuid.uuid4())

            # Reset all state
            self._cash = self._starting_cash
            self._realized_pnl = 0.0
            self._unrealized_pnl = 0.0
            self._positions.clear()
            self._price_book.clear()
            self._price_history.clear()
            self._strategy_metrics.clear()
            self._last_persistence_time = None

            logger.info("Reset to clean paper trading state, new session: %s", self._session_id)

            # Persist the clean state
            await self.persist_state()

    def _persist_trades(self, trades: List[PaperTradeResult]) -> int:
        if not trades:
            return 0

        db = self._db_factory()
        persisted = 0
        try:
            for trade in trades:
                entry_market = trade.metadata.get("market_conditions_entry")
                exit_market = trade.metadata.get("market_conditions_exit")
                market_conditions_payload: Any = None
                if entry_market is not None or exit_market is not None:
                    market_conditions_payload = {}
                    if entry_market is not None:
                        market_conditions_payload["entry"] = entry_market
                    if exit_market is not None:
                        market_conditions_payload["exit"] = exit_market
                if market_conditions_payload is None:
                    market_conditions_payload = trade.metadata.get("market_conditions")

                entry_indicators = trade.metadata.get("indicators_entry")
                exit_indicators = trade.metadata.get("indicators_exit")
                indicators_payload: Any = None
                if entry_indicators is not None or exit_indicators is not None:
                    indicators_payload = {}
                    if entry_indicators is not None:
                        indicators_payload["entry"] = entry_indicators
                    if exit_indicators is not None:
                        indicators_payload["exit"] = exit_indicators
                if indicators_payload is None:
                    indicators_payload = trade.metadata.get("indicators")

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
                    market_conditions_json=market_conditions_payload,
                    indicators_json=indicators_payload,
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
