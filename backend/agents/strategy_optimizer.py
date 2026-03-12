"""Strategy Optimizer agent that tunes strategy parameters via paper trading."""

import asyncio
import logging
import math
from datetime import datetime
from statistics import mean, stdev
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from agents.base import BaseAgent
from core.message_queue import Channels, message_queue
from core.paper_trading import (
    PaperTradeSignal,
    PaperTradingEngine,
    TradeIntent,
    TradeSide,
)
from core.tasks import log_system_event
from db.database import SessionLocal
from db.models import MarketData, Strategy

logger = logging.getLogger(__name__)


class StrategyOptimizationParameters(BaseModel):
    """Validated tuning knobs used during simulations."""

    entry_threshold: float = Field(0.002, ge=0.0)
    exit_threshold: float = Field(0.005, ge=0.0)
    stop_loss_pct: float = Field(0.01, ge=0.0)
    take_profit_pct: float = Field(0.02, ge=0.0)
    position_size_pct: float = Field(1.0, ge=0.1)
    max_duration_minutes: int = Field(60, ge=1)

    class Config:
        extra = "ignore"


class SimulationMetrics(BaseModel):
    """Performance summary produced by a paper trading run."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0


class StrategyCandidate(BaseModel):
    """Single candidate with parameters and outcome metrics."""

    params: StrategyOptimizationParameters
    metrics: SimulationMetrics


class StrategyOptimizerAgent(BaseAgent):
    """Agent responsible for tuning strategy parameters via paper trading."""

    OPTIMIZATION_INTERVAL = 300.0
    HISTORY_LIMIT = 240
    MIN_HISTORY_POINTS = 32
    MAX_STRATEGIES = 5
    DEFAULT_SYMBOL = "BTC/USD"

    PARAMETER_KEYS = {
        "entry_threshold": "entry_threshold",
        "exit_threshold": "exit_threshold",
        "stop_loss_pct": "stop_loss_pct",
        "take_profit_pct": "take_profit_pct",
        "position_size_pct": "position_size_pct",
        "position_size": "position_size_pct",
        "max_duration_minutes": "max_duration_minutes",
        "max_duration": "max_duration_minutes",
    }

    def __init__(self) -> None:
        super().__init__(
            name="strategy_optimizer",
            description="Runs paper trading simulations and tunes strategy knobs",
        )
        self._db_factory = SessionLocal
        self._next_run = 0.0
        self._start_cash = 100_000.0

    async def on_start(self) -> None:
        try:
            await message_queue.connect()
        except Exception as exc:  # pragma: no cover - best effort connect
            self._log_system_event(
                "warning",
                "Message queue connection failed",
                {"error": str(exc)},
            )

    async def on_stop(self) -> None:
        try:
            await message_queue.disconnect()
        except Exception as exc:  # pragma: no cover - best effort cleanup
            self._log_system_event(
                "warning",
                "Message queue disconnect failed",
                {"error": str(exc)},
            )

    async def run(self) -> None:
        now = asyncio.get_running_loop().time()
        if now < self._next_run:
            await asyncio.sleep(0.1)
            return

        self._next_run = now + self.OPTIMIZATION_INTERVAL
        await self._optimize_strategies()
        await asyncio.sleep(0.1)

    async def _optimize_strategies(self) -> None:
        strategies = await asyncio.to_thread(self._collect_candidates)
        if not strategies:
            return

        for strategy in strategies:
            try:
                await self._optimize_single(strategy)
            except Exception as exc:  # pragma: no cover - resilience guard
                self._log_system_event(
                    "error",
                    "Strategy optimization loop failed",
                    {"strategy_id": strategy.id, "error": str(exc)},
                )

    def _collect_candidates(self) -> List[Strategy]:
        db = self._db_factory()
        try:
            query = (
                db.query(Strategy)
                .filter(Strategy.status == "paper")
                .order_by(Strategy.updated_at.desc())
                .limit(self.MAX_STRATEGIES)
            )
            return query.all()
        finally:
            db.close()

    async def _optimize_single(self, strategy: Strategy) -> None:
        symbol = self._choose_symbol(strategy.rules_json)
        history = await self._load_price_history(symbol)
        if len(history) < self.MIN_HISTORY_POINTS:
            self._log_system_event(
                "info",
                "Insufficient history to optimize",
                {"strategy_id": strategy.id, "symbol": symbol},
            )
            return

        base_params = self._build_parameters(strategy.rules_json)
        candidates = self._build_candidate_set(base_params)

        best: Optional[StrategyCandidate] = None
        for params in candidates:
            metrics = await self._simulate_candidate(symbol, history, params, strategy.id)
            candidate = StrategyCandidate(params=params, metrics=metrics)
            if best is None or self._is_better(candidate, best):
                best = candidate

        if best:
            await self._publish_best(strategy, symbol, best)

    def _choose_symbol(self, rules: Optional[Dict[str, Any]]) -> str:
        if not rules:
            return self.DEFAULT_SYMBOL
        candidates = rules.get("symbols") or rules.get("symbol")
        if isinstance(candidates, Sequence):
            for value in candidates:
                if isinstance(value, str) and value.strip():
                    return value.strip().upper()
        if isinstance(candidates, str) and candidates.strip():
            return candidates.strip().upper()
        return self.DEFAULT_SYMBOL

    def _build_parameters(self, rules: Optional[Dict[str, Any]]) -> StrategyOptimizationParameters:
        base_values: Dict[str, Any] = {}
        if not rules:
            return StrategyOptimizationParameters()

        payload: Dict[str, Any]
        if isinstance(rules.get("parameters"), dict):
            payload = rules["parameters"]
        else:
            payload = rules

        for raw_key, value in payload.items():
            normalized = self.PARAMETER_KEYS.get(raw_key.lower())
            if not normalized:
                continue
            try:
                base_values[normalized] = float(value)
            except (TypeError, ValueError):
                continue

        try:
            return StrategyOptimizationParameters(**base_values)
        except Exception:
            return StrategyOptimizationParameters()

    def _build_candidate_set(
        self, base: StrategyOptimizationParameters
    ) -> List[StrategyOptimizationParameters]:
        factors = (0.85, 1.0, 1.15)
        candidates: List[StrategyOptimizationParameters] = []
        seen: List[Tuple] = []

        for entry_factor in factors:
            for exit_factor in factors:
                params = StrategyOptimizationParameters(
                    entry_threshold=base.entry_threshold * entry_factor,
                    exit_threshold=base.exit_threshold * exit_factor,
                    stop_loss_pct=base.stop_loss_pct,
                    take_profit_pct=base.take_profit_pct,
                    position_size_pct=base.position_size_pct,
                    max_duration_minutes=base.max_duration_minutes,
                )
                key = (
                    round(params.entry_threshold, 6),
                    round(params.exit_threshold, 6),
                    round(params.stop_loss_pct, 6),
                    round(params.take_profit_pct, 6),
                )
                if key in seen:
                    continue
                seen.append(key)
                candidates.append(params)

        candidates.append(base)
        return candidates

    async def _load_price_history(
        self, symbol: str
    ) -> List[Tuple[datetime, float]]:
        normalized = symbol.strip().upper()
        return await asyncio.to_thread(self._query_price_history, normalized)

    def _query_price_history(self, symbol: str) -> List[Tuple[datetime, float]]:
        db = self._db_factory()
        try:
            rows = (
                db.query(MarketData.timestamp, MarketData.close)
                .filter(MarketData.symbol == symbol)
                .order_by(MarketData.timestamp.desc())
                .limit(self.HISTORY_LIMIT)
                .all()
            )
            ordered = list(reversed(rows))
            return [(row.timestamp, float(row.close)) for row in ordered]
        finally:
            db.close()

    async def _simulate_candidate(
        self,
        symbol: str,
        history: List[Tuple[datetime, float]],
        params: StrategyOptimizationParameters,
        strategy_id: int,
    ) -> SimulationMetrics:
        engine = PaperTradingEngine(starting_cash=self._start_cash)
        equity_curve: List[float] = [self._start_cash]
        trades = 0
        wins = 0
        losses = 0
        total_pnl = 0.0
        prev_price: Optional[float] = None
        position_price = 0.0
        position_qty = 0.0
        position_time = datetime.utcnow()
        in_position = False

        for timestamp, price in history:
            if price <= 0:
                continue
            await engine.update_market_price(symbol, price)
            equity_curve.append(engine._cash + engine._realized_pnl + engine._unrealized_pnl)

            if prev_price is None:
                prev_price = price
                continue

            momentum = (price - prev_price) / prev_price if prev_price else 0.0
            prev_price = price

            if not in_position and momentum >= params.entry_threshold:
                position_qty = self._quantity_for_price(price, params.position_size_pct)
                position_price = price
                position_time = timestamp
                entry = PaperTradeSignal(
                    symbol=symbol,
                    intent=TradeIntent.ENTRY,
                    side=TradeSide.BUY,
                    quantity=position_qty,
                    price=price,
                    timestamp=timestamp,
                    strategy_id=strategy_id,
                )
                in_position = True
                try:
                    await engine.execute_signal(entry)
                except Exception:  # pragma: no cover - simulation guard
                    in_position = False
                continue

            if in_position:
                duration = (timestamp - position_time).total_seconds()
                change = (price - position_price) / position_price
                should_exit = False

                if change >= params.take_profit_pct:
                    should_exit = True
                elif change <= -params.stop_loss_pct:
                    should_exit = True
                elif momentum <= -params.exit_threshold:
                    should_exit = True
                elif duration >= params.max_duration_minutes * 60:
                    should_exit = True

                if should_exit:
                    exit_signal = PaperTradeSignal(
                        symbol=symbol,
                        intent=TradeIntent.EXIT,
                        quantity=position_qty,
                        price=price,
                        timestamp=timestamp,
                        strategy_id=strategy_id,
                    )
                    try:
                        results = await engine.execute_signal(exit_signal)
                        for result in results:
                            trades += 1
                            total_pnl += result.pnl
                            if result.pnl >= 0:
                                wins += 1
                            else:
                                losses += 1
                    except Exception:
                        pass
                    in_position = False

        if in_position and position_qty > 0:
            final_ts, final_price = history[-1]
            exit_signal = PaperTradeSignal(
                symbol=symbol,
                intent=TradeIntent.EXIT,
                quantity=position_qty,
                price=final_price,
                timestamp=final_ts,
                strategy_id=strategy_id,
            )
            try:
                results = await engine.execute_signal(exit_signal)
                for result in results:
                    trades += 1
                    total_pnl += result.pnl
                    if result.pnl >= 0:
                        wins += 1
                    else:
                        losses += 1
            except Exception:
                pass
            equity_curve.append(engine._cash + engine._realized_pnl + engine._unrealized_pnl)

        win_rate = (wins / trades) if trades else 0.0
        max_drawdown = self._calculate_max_drawdown(equity_curve)
        sharp = self._calculate_sharpe(equity_curve)

        return SimulationMetrics(
            total_trades=trades,
            winning_trades=wins,
            losing_trades=losses,
            total_pnl=total_pnl,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharp,
        )

    def _calculate_max_drawdown(self, equity_curve: List[float]) -> float:
        peak = equity_curve[0] if equity_curve else 0.0
        max_dd = 0.0
        for value in equity_curve:
            if value > peak:
                peak = value
            if peak > 0:
                dd = (peak - value) / peak
                if dd > max_dd:
                    max_dd = dd
        return max_dd

    def _calculate_sharpe(self, equity_curve: List[float]) -> float:
        returns = []
        for prev, curr in zip(equity_curve, equity_curve[1:]):
            if prev <= 0:
                continue
            returns.append((curr - prev) / prev)

        if len(returns) < 2:
            return 0.0
        try:
            avg_return = mean(returns)
            volatility = stdev(returns)
            if volatility == 0:
                return 0.0
            return avg_return / volatility * math.sqrt(252)
        except Exception:
            return 0.0

    def _quantity_for_price(self, price: float, pct: float) -> float:
        allocation = self._start_cash * (pct / 100.0)
        if price <= 0:
            return 0.0
        return max(1.0, allocation / price)

    def _is_better(self, candidate: StrategyCandidate, baseline: StrategyCandidate) -> bool:
        return (
            candidate.metrics.total_pnl > baseline.metrics.total_pnl
            or (
                candidate.metrics.total_pnl == baseline.metrics.total_pnl
                and candidate.metrics.win_rate > baseline.metrics.win_rate
            )
        )

    async def _publish_best(
        self,
        strategy: Strategy,
        symbol: str,
        best: StrategyCandidate,
    ) -> None:
        payload = {
            "strategy_id": strategy.id,
            "strategy_name": strategy.name,
            "symbol": symbol,
            "params": best.params.dict(),
            "metrics": best.metrics.dict(),
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            await message_queue.publish(Channels.AI_DECISIONS, payload)
            self._log_system_event(
                "info",
                "Strategy optimization published",
                payload,
            )
        except Exception as exc:
            self._log_system_event(
                "warning",
                "Failed to publish optimization result",
                {"strategy_id": strategy.id, "error": str(exc)},
            )

    def _log_system_event(self, level: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        sanitized = details or {}
        logger_method = getattr(logger, level, logger.info)
        logger_method("%s | %s", message, sanitized)
        try:
            log_system_event.delay(level, self.name, message, sanitized)
        except Exception as exc:  # pragma: no cover
            logger.warning("Unable to enqueue system log: %s", exc)


strategy_optimizer_agent = StrategyOptimizerAgent()
