"""Market Analyst agent packed with indicator tracking and pattern detection."""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

from pydantic import BaseModel, Field

from agents.base import AgentMessage, BaseAgent
from core.message_queue import Channels, message_queue
from core.tasks import log_system_event
from services.kraken_ws import KrakenWSFeed, TickerUpdate, kraken_ws

logger = logging.getLogger(__name__)

MAX_HISTORY = 128
INSIGHT_HISTORY_SIZE = 24


def _price_history() -> Deque[Decimal]:
    return deque(maxlen=MAX_HISTORY)


def _timestamp_history() -> Deque[datetime]:
    return deque(maxlen=MAX_HISTORY)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_normalize_value(v) for v in value)
    return value


class MarketInsightLevel(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class MarketInsight(BaseModel):
    symbol: str
    insight_type: str
    level: MarketInsightLevel
    summary: str
    score: Optional[float] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow())


@dataclass
class SymbolState:
    prices: Deque[Decimal] = field(default_factory=_price_history)
    timestamps: Deque[datetime] = field(default_factory=_timestamp_history)
    short_above_long: Optional[bool] = None
    last_insight_times: Dict[str, datetime] = field(default_factory=dict)


class MarketAnalystAgent(BaseAgent):
    """Agent that watches market ticks, calculates indicators, and emits insights."""

    DEFAULT_SYMBOLS: List[str] = ["BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD"]
    SHORT_WINDOW = 5
    LONG_WINDOW = 20
    MOMENTUM_WINDOW = 6
    VOLATILITY_WINDOW = 12

    MOMENTUM_THRESHOLD = Decimal("0.005")
    VOLATILITY_THRESHOLD = Decimal("0.008")
    INSIGHT_COOLDOWN = timedelta(seconds=30)

    def __init__(self, symbols: Optional[List[str]] = None) -> None:
        super().__init__(
            name="market_analyst",
            description="Analyzes live tick data and publishes indicator driven insights",
        )
        self._symbols = symbols or list(self.DEFAULT_SYMBOLS)
        self._symbol_states: Dict[str, SymbolState] = {}
        self._insight_channel = Channels.AI_DECISIONS
        self._insight_history: Dict[str, Deque[Dict[str, Any]]] = {}
        self._insight_lock = asyncio.Lock()

    async def on_start(self) -> None:
        try:
            await message_queue.connect()
        except Exception as exc:  # pragma: no cover - best effort connect
            self._log_system_event(
                "warning",
                "Message queue connection failed",
                {"error": str(exc)},
            )

        try:
            await kraken_ws.subscribe_ticker(self._symbols, self._handle_ticker_update)
            self._log_system_event(
                "info",
                "Subscribed to Kraken ticker feed",
                {"symbols": self._symbols},
            )
        except Exception as exc:  # pragma: no cover - ensure agent can still start
            self._log_system_event(
                "error",
                "Failed to subscribe to Kraken ticker",
                {"error": str(exc)},
            )

    async def on_stop(self) -> None:
        try:
            await kraken_ws.unsubscribe(KrakenWSFeed.TICKER, self._symbols)
            self._log_system_event(
                "info",
                "Unsubscribed from Kraken ticker feed",
                {"symbols": self._symbols},
            )
        except Exception as exc:  # pragma: no cover - best effort cleanup
            self._log_system_event(
                "warning",
                "Ticker unsubscribe failed",
                {"error": str(exc)},
            )

    async def run(self) -> None:
        await asyncio.sleep(0.1)

    async def process_message(self, message: AgentMessage) -> None:
        self._log_system_event(
            "debug",
            "Market analyst ignored message",
            {"sender": message.sender, "message_type": message.message_type},
        )

    async def _handle_ticker_update(self, update: TickerUpdate) -> None:
        try:
            state = self._symbol_state(update.symbol)
            state.prices.append(update.last)
            state.timestamps.append(update.timestamp)
            await self._evaluate_patterns(update.symbol, state, update)
        except Exception as exc:  # pragma: no cover - resilience
            logger.error("Market Analyst ticker handler failed: %s", exc)
            self._log_system_event(
                "error",
                "Ticker handler error",
                {"symbol": update.symbol, "error": str(exc)},
            )

    def _symbol_state(self, symbol: str) -> SymbolState:
        if symbol not in self._symbol_states:
            self._symbol_states[symbol] = SymbolState()
        return self._symbol_states[symbol]

    async def _evaluate_patterns(
        self, symbol: str, state: SymbolState, update: TickerUpdate
    ) -> None:
        short_sma = self._calculate_sma(state.prices, self.SHORT_WINDOW)
        long_sma = self._calculate_sma(state.prices, self.LONG_WINDOW)
        momentum = self._calculate_momentum(state.prices, self.MOMENTUM_WINDOW)
        volatility = self._calculate_volatility(state.prices, self.VOLATILITY_WINDOW)

        indicators = {
            "price": str(update.last),
            "short_sma": _normalize_value(short_sma),
            "long_sma": _normalize_value(long_sma),
            "momentum": _normalize_value(momentum),
            "volatility": _normalize_value(volatility),
            "timestamp": update.timestamp.isoformat(),
        }

        if short_sma is not None and long_sma is not None:
            await self._detect_sma_cross(symbol, state, short_sma, long_sma, indicators)

        if momentum is not None:
            await self._detect_momentum(symbol, state, momentum, indicators)

        if volatility is not None:
            await self._detect_volatility(symbol, state, volatility, indicators)

    async def _detect_sma_cross(
        self,
        symbol: str,
        state: SymbolState,
        short_sma: Decimal,
        long_sma: Decimal,
        context: Dict[str, Any],
    ) -> None:
        short_above = short_sma > long_sma
        previous = state.short_above_long
        state.short_above_long = short_above

        if previous is None or short_above == previous:
            return

        if not self._can_emit_insight(state, "sma_cross"):
            return

        level = MarketInsightLevel.BULLISH if short_above else MarketInsightLevel.BEARISH
        score = float(abs(short_sma - long_sma) / (long_sma or Decimal("1")))
        insight = MarketInsight(
            symbol=symbol,
            insight_type="sma_cross",
            level=level,
            summary="Short-term SMA crossed {} the long-term SMA".format(
                "above" if short_above else "below"
            ),
            score=score,
            details=context,
        )
        await self._publish_insight(insight)

    async def _detect_momentum(
        self,
        symbol: str,
        state: SymbolState,
        momentum: Decimal,
        context: Dict[str, Any],
    ) -> None:
        if abs(momentum) < self.MOMENTUM_THRESHOLD:
            return

        if not self._can_emit_insight(state, "momentum"):
            return

        level = MarketInsightLevel.BULLISH if momentum > 0 else MarketInsightLevel.BEARISH
        score = float(abs(momentum))
        insight = MarketInsight(
            symbol=symbol,
            insight_type="momentum",
            level=level,
            summary="Price momentum {}".format("accelerating" if momentum > 0 else "decelerating"),
            score=score,
            details=context,
        )
        await self._publish_insight(insight)

    async def _detect_volatility(
        self,
        symbol: str,
        state: SymbolState,
        volatility: Decimal,
        context: Dict[str, Any],
    ) -> None:
        if volatility < self.VOLATILITY_THRESHOLD:
            return

        if not self._can_emit_insight(state, "volatility"):
            return

        level = MarketInsightLevel.NEUTRAL
        score = float(volatility)
        insight = MarketInsight(
            symbol=symbol,
            insight_type="volatility_expansion",
            level=level,
            summary="Volatility expanded beyond baseline",
            score=score,
            details=context,
        )
        await self._publish_insight(insight)

    def _can_emit_insight(self, state: SymbolState, key: str) -> bool:
        now = datetime.utcnow()
        last = state.last_insight_times.get(key)
        if last and (now - last) < self.INSIGHT_COOLDOWN:
            return False
        state.last_insight_times[key] = now
        return True

    async def _publish_insight(self, insight: MarketInsight) -> None:
        sanitized = _normalize_value(insight.details)
        insight_dict = insight.dict()
        insight_dict["details"] = sanitized

        # Extract raw indicator values from details for analysis bundle
        raw_indicators = {
            "short_sma": insight_dict["details"].get("short_sma"),
            "long_sma": insight_dict["details"].get("long_sma"),
            "momentum": insight_dict["details"].get("momentum"),
            "volatility": insight_dict["details"].get("volatility"),
        }

        price_data = {
            "price": insight_dict["details"].get("price"),
            "timestamp": insight_dict["details"].get("timestamp"),
        }

        # Build full analysis bundle for downstream audit
        insight_payload = {
            # Core insight fields
            "symbol": insight.symbol,
            "insight_type": insight.insight_type,
            "level": insight.level.value,
            "summary": insight.summary,
            "score": insight.score,
            "timestamp": insight.timestamp.isoformat(),
            "details": sanitized,

            # Full analysis bundle (user decision: include raw data for audit)
            "analysis_bundle": {
                "raw_indicators": raw_indicators,
                "price_data": price_data,
                "pattern_detected": insight.insight_type,
                "source": "market_analyst",
                "analysis_timestamp": datetime.utcnow().isoformat(),
            },
        }

        # Map insight level to priority (per user decision)
        priority_map = {
            MarketInsightLevel.BULLISH: 1,   # High priority for actionable signals
            MarketInsightLevel.BEARISH: 1,   # High priority for actionable signals
            MarketInsightLevel.NEUTRAL: 2,   # Normal priority for informational
        }
        priority = priority_map.get(insight.level, 2)

        # Publish via Redis Streams for reliable delivery
        published_reliable = False
        try:
            published_reliable = await message_queue.publish_reliable(
                Channels.STREAM_TRADE_SIGNALS,
                insight_payload,
                priority=priority,
            )
        except Exception as exc:  # pragma: no cover - best effort publish
            logger.warning("Failed to publish market insight via streams: %s", exc)
            self._log_system_event(
                "warning",
                "Insight stream publish failed",
                {"symbol": insight.symbol, "error": str(exc)},
            )

        # Keep backward compatibility for pub/sub (AI chat, etc.)
        published_pubsub = False
        try:
            published_pubsub = await message_queue.publish(self._insight_channel, insight_dict)
        except Exception as exc:  # pragma: no cover - best effort publish
            logger.warning("Failed to publish market insight via pub/sub: %s", exc)

        if not published_reliable and not published_pubsub:
            logger.debug("Insight publish returned false: %s", insight_dict)
            return

        self._log_system_event(
            "info",
            "Market insight published",
            {
                "symbol": insight.symbol,
                "type": insight.insight_type,
                "level": insight.level.value,
                "score": insight.score,
                "priority": priority,
                "stream_published": published_reliable,
                "pubsub_published": published_pubsub,
            },
        )
        await self._archive_insight(insight.symbol, insight_dict)

    def _calculate_sma(self, prices: Deque[Decimal], window: int) -> Optional[Decimal]:
        if len(prices) < window:
            return None
        window_values = list(prices)[-window:]
        total = sum(window_values, Decimal("0"))
        return total / Decimal(window)

    async def _archive_insight(self, symbol: str, insight: Dict[str, Any]) -> None:
        if not symbol:
            return
        async with self._insight_lock:
            storage = self._insight_history.setdefault(symbol, deque(maxlen=INSIGHT_HISTORY_SIZE))
            storage.append(insight.copy())

    async def get_recent_insights(self, symbol: str, limit: int = 3) -> List[Dict[str, Any]]:
        if limit <= 0:
            limit = INSIGHT_HISTORY_SIZE
        async with self._insight_lock:
            history = list(self._insight_history.get(symbol, []))
        if not history:
            return []
        window = history[-limit:]
        return [entry.copy() for entry in window]

    async def get_indicator_summary(self, symbol: str) -> Dict[str, Any]:
        """
        Return the most recent indicator values computed for a symbol.
        """
        state = self._symbol_state(symbol)
        short_sma = self._calculate_sma(state.prices, self.SHORT_WINDOW)
        long_sma = self._calculate_sma(state.prices, self.LONG_WINDOW)
        momentum = self._calculate_momentum(state.prices, self.MOMENTUM_WINDOW)
        volatility = self._calculate_volatility(state.prices, self.VOLATILITY_WINDOW)
        last_price = state.prices[-1] if state.prices else None
        last_timestamp = state.timestamps[-1] if state.timestamps else None
        return {
            "short_sma": short_sma,
            "long_sma": long_sma,
            "momentum": momentum,
            "volatility": volatility,
            "price_count": len(state.prices),
            "last_price": last_price,
            "last_timestamp": last_timestamp,
        }

    def _calculate_momentum(self, prices: Deque[Decimal], lookback: int) -> Optional[Decimal]:
        if len(prices) < lookback + 1:
            return None
        latest = prices[-1]
        previous = prices[-(lookback + 1)]
        if previous == 0:
            return None
        return (latest - previous) / previous

    def _calculate_volatility(self, prices: Deque[Decimal], window: int) -> Optional[Decimal]:
        if len(prices) < window:
            return None
        window_values = list(prices)[-window:]
        high = max(window_values)
        low = min(window_values)
        mean = sum(window_values, Decimal("0")) / Decimal(len(window_values))
        if mean == 0:
            return Decimal("0")
        return (high - low) / mean

    def _log_system_event(
        self, level: str, message: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        sanitized = _normalize_value(details or {})
        logger_method = getattr(logger, level, logger.info)
        logger_method("%s | %s", message, sanitized)
        try:
            log_system_event.delay(level, self.name, message, sanitized)
        except Exception as exc:  # pragma: no cover - best effort log
            logger.warning("Unable to enqueue log event: %s", exc)


market_analyst_agent = MarketAnalystAgent()
