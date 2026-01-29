"""Risk Monitor agent that tracks exposures and raises alerts when limits are crossed."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from backend.agents.base import AgentMessage, BaseAgent
from backend.core.message_queue import Channels, message_queue
from backend.core.tasks import log_system_event
from db.database import SessionLocal
from db.models import MarketData, RiskSettings, Trade

logger = logging.getLogger(__name__)


class RiskScoreBreakdown(BaseModel):
    """Detailed breakdown of the contributions to the overall risk score."""

    model_config = ConfigDict(extra="forbid")
    position_score: float
    concurrent_score: float
    daily_loss_score: float
    drawdown_score: float
    position_ratio: float
    concurrent_ratio: float
    daily_loss_ratio: float
    drawdown_pct: float
    largest_position_value: float
    max_position_limit_value: float
    open_positions: int
    daily_loss_value: float
    drawdown_limit: float
    equity_estimate: float


class RiskAlertPayload(BaseModel):
    """Payload published when the risk monitor raises an alert."""

    model_config = ConfigDict(extra="forbid")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    score: float
    threshold: float
    breakdown: RiskScoreBreakdown
    reasons: List[str]


@dataclass
class RiskSnapshot:
    """Snapshot of the current risk posture used for scoring."""

    settings_id: int
    max_position_size_pct: float
    max_concurrent_positions: int
    daily_loss_limit: float
    max_drawdown_pct: float
    max_risk_score: float
    equity_estimate: float
    realized_pnl: float
    drawdown_pct: float
    daily_loss_value: float
    open_trades: List[Trade]
    closed_trades: List[Trade]
    latest_prices: Dict[str, float]


def _normalize_symbol(symbol: Optional[str]) -> Optional[str]:
    if not symbol:
        return None
    return symbol.strip().upper()


def _serialize_for_log(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize_for_log(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_for_log(item) for item in value]
    return value


class RiskMonitorAgent(BaseAgent):
    """Agent responsible for computing the system risk score and sending alerts."""

    CHECK_INTERVAL = 5.0
    ALERT_COOLDOWN = 60.0
    BASE_CAPITAL = 100_000.0
    POSITION_WEIGHT = 30.0
    CONCURRENT_WEIGHT = 20.0
    DAILY_LOSS_WEIGHT = 30.0
    DRAWDOWN_WEIGHT = 20.0
    MAX_RATIO = 3.0
    ALERT_CHANNEL = Channels.RISK_ALERTS

    def __init__(self) -> None:
        super().__init__(
            name="risk_monitor",
            description="Continuously evaluates portfolio risk and raises alerts when thresholds are breached",
        )
        self._db_factory = SessionLocal
        self._next_check = 0.0
        self._last_alert_time: Optional[datetime] = None
        self._current_score = 0.0

    async def on_start(self) -> None:
        connected = await message_queue.connect()
        if not connected:
            self._log_system_event(
                "warning",
                "Risk monitor could not connect to the message queue",
                {},
            )

    async def on_stop(self) -> None:
        try:
            await message_queue.disconnect()
        except Exception as exc:
            self._log_system_event(
                "warning",
                "Risk monitor failed to disconnect from the message queue",
                {"error": str(exc)},
            )

    async def run(self) -> None:
        now = asyncio.get_running_loop().time()
        if now < self._next_check:
            await asyncio.sleep(0.1)
            return

        self._next_check = now + self.CHECK_INTERVAL
        try:
            snapshot = await asyncio.to_thread(self._build_snapshot)
            score, breakdown = self._score_snapshot(snapshot)
            self._current_score = score
            await asyncio.to_thread(self._persist_score, snapshot.settings_id, score)
            await self._maybe_alert(snapshot, score, breakdown)
        except Exception as exc:
            logger.error("Risk monitor run failed: %s", exc, exc_info=True)
            self._log_system_event(
                "error",
                "Risk evaluation loop failed",
                {"error": str(exc)},
            )
        finally:
            await asyncio.sleep(0.01)

    async def process_message(self, message: AgentMessage) -> None:
        self._log_system_event(
            "debug",
            "Risk monitor received a message",
            {
                "sender": message.sender,
                "type": message.message_type,
            },
        )

    def _build_snapshot(self) -> RiskSnapshot:
        db = self._db_factory()
        try:
            settings = self._get_or_create_settings(db)
            open_trades = (
                db.query(Trade)
                .filter(Trade.exit_time.is_(None))
                .all()
            )
            closed_trades = (
                db.query(Trade)
                .filter(Trade.exit_time.isnot(None))
                .order_by(Trade.exit_time.asc())
                .all()
            )
            closed_today = self._filter_today(closed_trades)
            realized_pnl = sum(float(trade.pnl or 0.0) for trade in closed_trades)
            daily_loss_value = sum(
                -float(trade.pnl or 0.0)
                for trade in closed_today
                if trade.pnl is not None and float(trade.pnl) < 0
            )
            drawdown_pct = self._calculate_drawdown(closed_trades)
            symbols = [
                normalized
                for trade in open_trades
                if (normalized := _normalize_symbol(trade.symbol))
            ]
            latest_prices = self._load_latest_prices(db, symbols)
            equity_estimate = max(self.BASE_CAPITAL + realized_pnl, 0.0)
            return RiskSnapshot(
                settings_id=settings.id,
                max_position_size_pct=float(settings.max_position_size_pct or 0.0),
                max_concurrent_positions=int(settings.max_concurrent_positions or 0),
                daily_loss_limit=float(settings.daily_loss_limit or 0.0),
                max_drawdown_pct=float(settings.max_drawdown_pct or 0.0),
                max_risk_score=float(settings.max_risk_score or 100.0),
                equity_estimate=equity_estimate,
                realized_pnl=realized_pnl,
                drawdown_pct=drawdown_pct,
                daily_loss_value=daily_loss_value,
                open_trades=open_trades,
                closed_trades=closed_trades,
                latest_prices=latest_prices,
            )
        finally:
            db.close()

    def _get_or_create_settings(self, db):
        settings = (
            db.query(RiskSettings)
            .order_by(RiskSettings.updated_at.desc())
            .first()
        )
        if settings:
            return settings

        settings = RiskSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
        return settings

    def _filter_today(self, trades: List[Trade]) -> List[Trade]:
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        return [
            trade
            for trade in trades
            if trade.exit_time
            and today <= trade.exit_time < tomorrow
        ]

    def _load_latest_prices(self, db, symbols: List[str]) -> Dict[str, float]:
        prices: Dict[str, float] = {}
        for symbol in {symbol for symbol in symbols if symbol}:
            row = (
                db.query(MarketData)
                .filter(MarketData.symbol == symbol)
                .order_by(MarketData.timestamp.desc())
                .first()
            )
            if row and row.close is not None:
                prices[symbol] = float(row.close)
        return prices

    def _calculate_drawdown(self, trades: List[Trade]) -> float:
        closed = [trade for trade in trades if trade.exit_time]
        if not closed:
            return 0.0
        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0
        sorted_trades = sorted(
            closed,
            key=lambda trade: trade.exit_time or datetime.min,
        )
        for trade in sorted_trades:
            pnl = float(trade.pnl or 0.0)
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            denominator = abs(peak) if abs(peak) >= 1.0 else 1.0
            drawdown = (peak - cumulative) / denominator
            max_drawdown = max(max_drawdown, drawdown)
        return max_drawdown * 100.0

    def _score_snapshot(
        self, snapshot: RiskSnapshot
    ) -> Tuple[float, RiskScoreBreakdown]:
        largest_position_value = self._largest_position_value(
            snapshot.open_trades, snapshot.latest_prices
        )
        position_limit_value = (
            snapshot.equity_estimate
            * (snapshot.max_position_size_pct / 100.0)
            if snapshot.max_position_size_pct > 0
            else 0.0
        )
        position_ratio = self._ratio(largest_position_value, position_limit_value)
        concurrent_ratio = self._ratio(
            len(snapshot.open_trades), snapshot.max_concurrent_positions
        )
        daily_loss_ratio = self._ratio(
            snapshot.daily_loss_value, snapshot.daily_loss_limit
        )
        drawdown_ratio = self._ratio(
            snapshot.drawdown_pct, snapshot.max_drawdown_pct
        )
        position_score = self._scale_ratio(position_ratio, self.POSITION_WEIGHT)
        concurrent_score = self._scale_ratio(concurrent_ratio, self.CONCURRENT_WEIGHT)
        daily_loss_score = self._scale_ratio(
            daily_loss_ratio, self.DAILY_LOSS_WEIGHT
        )
        drawdown_score = self._scale_ratio(drawdown_ratio, self.DRAWDOWN_WEIGHT)
        total_score = min(
            position_score + concurrent_score + daily_loss_score + drawdown_score,
            100.0,
        )
        breakdown = RiskScoreBreakdown(
            position_score=round(position_score, 2),
            concurrent_score=round(concurrent_score, 2),
            daily_loss_score=round(daily_loss_score, 2),
            drawdown_score=round(drawdown_score, 2),
            position_ratio=position_ratio,
            concurrent_ratio=concurrent_ratio,
            daily_loss_ratio=daily_loss_ratio,
            drawdown_pct=snapshot.drawdown_pct,
            largest_position_value=largest_position_value,
            max_position_limit_value=position_limit_value,
            open_positions=len(snapshot.open_trades),
            daily_loss_value=snapshot.daily_loss_value,
            drawdown_limit=snapshot.max_drawdown_pct,
            equity_estimate=snapshot.equity_estimate,
        )
        return total_score, breakdown

    def _largest_position_value(
        self, trades: List[Trade], prices: Dict[str, float]
    ) -> float:
        max_value = 0.0
        for trade in trades:
            symbol = _normalize_symbol(trade.symbol) or ""
            price = prices.get(symbol) or float(trade.entry_price or 0.0)
            value = abs(float(trade.quantity or 0.0)) * price
            max_value = max(max_value, value)
        return max_value

    def _ratio(self, numerator: float, denominator: float) -> float:
        if numerator <= 0:
            return 0.0
        if denominator <= 0:
            return self.MAX_RATIO + 1.0
        return numerator / denominator

    def _scale_ratio(self, ratio: float, weight: float) -> float:
        normalized = min(ratio, self.MAX_RATIO) / self.MAX_RATIO
        return normalized * weight

    async def _maybe_alert(
        self,
        snapshot: RiskSnapshot,
        score: float,
        breakdown: RiskScoreBreakdown,
    ) -> None:
        threshold = max(snapshot.max_risk_score, 0.0)
        reasons = self._alert_reasons(score, threshold, breakdown, snapshot)
        if not reasons:
            return
        now = datetime.utcnow()
        if (
            self._last_alert_time
            and (now - self._last_alert_time).total_seconds() < self.ALERT_COOLDOWN
        ):
            return
        payload = RiskAlertPayload(
            score=round(score, 2),
            threshold=threshold,
            breakdown=breakdown,
            reasons=reasons,
        )
        await self._publish_alert(payload)
        self._last_alert_time = now

    def _alert_reasons(
        self,
        score: float,
        threshold: float,
        breakdown: RiskScoreBreakdown,
        snapshot: RiskSnapshot,
    ) -> List[str]:
        reasons: List[str] = []
        if threshold > 0 and score >= threshold:
            reasons.append(
                f"Risk score {score:.1f} >= configured threshold {threshold:.1f}."
            )
        if breakdown.position_ratio >= 1.0:
            reasons.append(
                "Largest open position exceeds the configured position size limit."
            )
        if breakdown.concurrent_ratio >= 1.0:
            reasons.append(
                "Concurrent positions exceed the configured limit."
            )
        if breakdown.daily_loss_ratio >= 1.0:
            reasons.append(
                "Daily loss limit breached "
                f"(loss ${breakdown.daily_loss_value:.2f} / limit ${snapshot.daily_loss_limit:.2f})."
            )
        if (
            snapshot.max_drawdown_pct > 0
            and breakdown.drawdown_pct >= snapshot.max_drawdown_pct
        ):
            reasons.append(
                "Drawdown threshold breached "
                f"({breakdown.drawdown_pct:.1f}% >= {snapshot.max_drawdown_pct:.1f}%)."
            )
        return reasons

    async def _publish_alert(self, payload: RiskAlertPayload) -> bool:
        payload_dict = payload.model_dump()
        self._log_system_event(
            "warning",
            "Risk alert triggered",
            {
                "score": payload.score,
                "threshold": payload.threshold,
                "reasons": payload.reasons,
            },
        )
        try:
            published = await message_queue.publish(self.ALERT_CHANNEL, payload_dict)
        except Exception as exc:
            self._log_system_event(
                "error",
                "Risk alert publish failed",
                {"error": str(exc)},
            )
            return False
        if not published:
            self._log_system_event(
                "warning",
                "Risk alert publish returned False",
                {"channel": self.ALERT_CHANNEL},
            )
        else:
            self._log_system_event(
                "info",
                "Risk alert published",
                {"channel": self.ALERT_CHANNEL},
            )
        return published

    def _persist_score(self, settings_id: int, score: float) -> None:
        db = self._db_factory()
        try:
            record = db.get(RiskSettings, settings_id)
            if not record:
                return
            record.current_risk_score = score
            db.add(record)
            db.commit()
        except Exception as exc:
            logger.warning("Failed to persist risk score: %s", exc)
        finally:
            db.close()

    def _log_system_event(
        self, level: str, message: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        sanitized = _serialize_for_log(details or {})
        log_method = getattr(logger, level, logger.info)
        log_method("%s | %s", message, sanitized)
        try:
            log_system_event.delay(level, self.name, message, sanitized)
        except Exception as exc:
            logger.warning("Unable to enqueue system log: %s", exc)


risk_monitor_agent = RiskMonitorAgent()
