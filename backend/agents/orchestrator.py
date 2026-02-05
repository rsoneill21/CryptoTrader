"""Main orchestrator agent that coordinates other AI agents, chat, and trading decisions."""

import asyncio
import logging
import uuid
from collections import deque
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Deque, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.ai import ChatAIService, ChatRequest
from agents.base import AgentMessage, BaseAgent
from core.message_queue import Channels, message_queue
from core.tasks import log_system_event
from core.trading_control import trading_control
from services.kraken import OrderSide, OrderType, kraken_service

logger = logging.getLogger(__name__)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    return value


class MarketInsightPayload(BaseModel):
    symbol: str
    insight_type: str
    level: str
    summary: str
    score: Optional[float] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(extra="ignore")


class StrategyOptimizationPayload(BaseModel):
    strategy_id: int
    strategy_name: str
    symbol: str
    params: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(extra="ignore")


class ChatTrigger(BaseModel):
    message: str
    user_id: Optional[str] = None
    tone: Optional[str] = None
    provider: Optional[str] = None
    context_json: Optional[Dict[str, Any]] = None
    preferences_json: Optional[Dict[str, Any]] = None
    type: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class ChatResponsePayload(BaseModel):
    type: str = Field("chat_response")
    user_id: Optional[str]
    response: str
    context_snapshot: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={"format": "orchestrator_chat_response"},
        json_encoders={datetime: lambda value: value.isoformat()},
    )


class OrchestratorAgent(BaseAgent):
    """Coordinates AI insights, chat interactions, and trading decisions."""

    DECISION_COOLDOWN = 120.0
    CONTEXT_HISTORY_SIZE = 8
    BASE_CAPITAL = Decimal("100000")
    MIN_VOLUME = Decimal("0.0001")

    def __init__(self) -> None:
        super().__init__(name="orchestrator", description="Main AI orchestrator")
        self._insights: Dict[str, MarketInsightPayload] = {}
        self._strategies: Dict[str, StrategyOptimizationPayload] = {}
        self._decision_timestamps: Dict[str, float] = {}
        self._context_history: Deque[Dict[str, Any]] = deque(maxlen=self.CONTEXT_HISTORY_SIZE)
        self._chat_service = ChatAIService()
        self._decision_lock = asyncio.Lock()
        self._subscriptions: List[str] = []
        self._last_risk_alert: Optional[Dict[str, Any]] = None

    async def on_start(self) -> None:
        connected = await message_queue.connect()
        if not connected:
            self._log_event("warning", "Orchestrator could not connect to message queue", {})
            return

        await self._subscribe_channel(Channels.AI_DECISIONS, self._handle_agent_decision)
        await self._subscribe_channel(Channels.ORCHESTRATOR, self._handle_chat_channel)
        await self._subscribe_channel(Channels.RISK_ALERTS, self._handle_risk_alert)
        self._log_event("info", "Orchestrator started", {"channels": self._subscriptions})

    async def on_stop(self) -> None:
        for channel in list(self._subscriptions):
            try:
                await message_queue.unsubscribe(channel)
            except Exception as exc:
                self._log_event("warning", "Failed to unsubscribe channel", {"channel": channel, "error": str(exc)})
        self._subscriptions.clear()
        try:
            await message_queue.disconnect()
        except Exception as exc:
            self._log_event("warning", "Failed to disconnect message queue", {"error": str(exc)})
        self._log_event("info", "Orchestrator stopped", {})

    async def run(self) -> None:
        await asyncio.sleep(0.1)

    async def process_message(self, message: AgentMessage) -> None:
        self._log_event(
            "debug",
            "Orchestrator received internal message",
            {"sender": message.sender, "type": message.message_type, "payload": _serialize_value(message.payload)},
        )

    async def _subscribe_channel(self, channel: str, handler: Any) -> None:
        try:
            subscribed = await message_queue.subscribe(channel, handler)
        except Exception as exc:
            self._log_event("warning", "Subscription failed", {"channel": channel, "error": str(exc)})
            return
        if subscribed:
            self._subscriptions.append(channel)
            self._log_event("debug", "Subscribed to channel", {"channel": channel})
        else:
            self._log_event("warning", "Channel subscription rejected", {"channel": channel})

    async def _handle_agent_decision(self, payload: Dict[str, Any]) -> None:
        if payload.get("insight_type"):
            await self._handle_market_insight(payload)
            return
        if payload.get("strategy_id") is not None:
            await self._handle_strategy_update(payload)
            return
        self._log_event("debug", "Unknown AI decision payload", payload)

    async def _handle_market_insight(self, payload: Dict[str, Any]) -> None:
        try:
            insight = MarketInsightPayload(**payload)
        except ValidationError as exc:
            self._log_event("warning", "Invalid market insight payload", {"error": str(exc), "payload": payload})
            return
        self._insights[insight.symbol] = insight
        self._record_context_entry("market_insight", insight.dict())
        await self._maybe_create_trade_signal(insight.symbol)

    async def _handle_strategy_update(self, payload: Dict[str, Any]) -> None:
        try:
            strategy = StrategyOptimizationPayload(**payload)
        except ValidationError as exc:
            self._log_event("warning", "Invalid strategy payload", {"error": str(exc), "payload": payload})
            return
        self._strategies[strategy.symbol] = strategy
        self._record_context_entry("strategy_update", strategy.dict())
        await self._maybe_create_trade_signal(strategy.symbol)

    async def _handle_chat_channel(self, payload: Dict[str, Any]) -> None:
        if payload.get("type") == "chat_response":
            return
        try:
            trigger = ChatTrigger(**payload)
        except ValidationError as exc:
            self._log_event("warning", "Invalid chat trigger", {"error": str(exc), "payload": payload})
            return
        if not trigger.message.strip():
            return
        await self._respond_to_chat(trigger)

    async def _handle_risk_alert(self, payload: Dict[str, Any]) -> None:
        self._last_risk_alert = payload
        self._record_context_entry("risk_alert", payload)

    async def _respond_to_chat(self, trigger: ChatTrigger) -> None:
        context_snapshot = self._build_chat_context()
        combined_context = {"orchestrator": context_snapshot}
        if trigger.context_json:
            combined_context["user_context"] = _serialize_value(trigger.context_json)
        request = ChatRequest(
            message=trigger.message,
            tone=trigger.tone,
            context_json=combined_context,
            preferences_json=trigger.preferences_json,
            provider=trigger.provider,
        )
        response_text = ""
        try:
            response_text = await self._collect_chat_response(request)
        except Exception as exc:
            self._log_event("error", "Chat response error", {"error": str(exc)})
            response_text = "I am currently unable to respond."
        response_payload = ChatResponsePayload(
            user_id=trigger.user_id,
            response=response_text,
            context_snapshot=context_snapshot,
        )
        serialized = response_payload.model_dump()
        try:
            await message_queue.publish(Channels.ORCHESTRATOR, serialized)
            self._record_context_entry("chat_response", serialized)
        except Exception as exc:
            self._log_event("warning", "Failed to publish chat response", {"error": str(exc)})

    async def _collect_chat_response(self, request: ChatRequest) -> str:
        builder: List[str] = []
        async for chunk in self._chat_service.stream_response(request):
            builder.append(chunk)
        return "".join(builder).strip()

    async def _maybe_create_trade_signal(self, symbol: str) -> None:
        async with self._decision_lock:
            insight = self._insights.get(symbol)
            strategy = self._strategies.get(symbol)
            if not insight or not strategy:
                return
            if trading_control.is_paused():
                self._log_event("info", "Trading paused, skipping decision", {"symbol": symbol})
                return
            loop = asyncio.get_running_loop()
            now = loop.time()
            last = self._decision_timestamps.get(symbol)
            if last and (now - last) < self.DECISION_COOLDOWN:
                return
            side = self._side_from_insight(insight)
            if not side:
                return
            price = await self._fetch_latest_price(symbol)
            if price is None or price <= 0:
                return
            volume = self._calculate_volume(price, strategy.params)
            if volume <= 0:
                return
            payload = self._build_trade_signal(symbol, side, volume, insight, strategy)
            try:
                published = await message_queue.publish(Channels.TRADE_SIGNALS, payload)
            except Exception as exc:
                self._log_event("warning", "Trade signal publish failed", {"symbol": symbol, "error": str(exc)})
                return
            if not published:
                self._log_event("warning", "Trade signal rejected by queue", {"symbol": symbol})
                return
            self._decision_timestamps[symbol] = now
            self._record_context_entry("trade_decision", payload)
            self._log_event("info", "Trading decision dispatched", {"symbol": symbol, "side": side.value, "volume": str(volume)})

    def _side_from_insight(self, insight: MarketInsightPayload) -> Optional[OrderSide]:
        level = (insight.level or "").strip().lower()
        if "bull" in level:
            return OrderSide.BUY
        if "bear" in level:
            return OrderSide.SELL
        return None

    async def _fetch_latest_price(self, symbol: str) -> Optional[Decimal]:
        try:
            ticker = await kraken_service.get_ticker(symbol)
            return ticker.last
        except Exception as exc:
            self._log_event("warning", "Failed to fetch ticker", {"symbol": symbol, "error": str(exc)})
            return None

    def _calculate_volume(self, price: Decimal, params: Dict[str, Any]) -> Decimal:
        target_pct = self._extract_position_pct(params)
        allocation = (self.BASE_CAPITAL * target_pct) / Decimal("100")
        try:
            volume = allocation / price
        except (ZeroDivisionError, InvalidOperation):
            return Decimal("0")
        quantized = volume.quantize(self.MIN_VOLUME, rounding=ROUND_DOWN)
        return max(quantized, self.MIN_VOLUME)

    def _extract_position_pct(self, params: Dict[str, Any]) -> Decimal:
        raw = params.get("position_size_pct") or params.get("position_size") or 1.0
        try:
            pct = Decimal(str(raw))
        except Exception:
            pct = Decimal("1.0")
        pct = max(Decimal("0.1"), min(pct, Decimal("25")))
        return pct

    def _build_trade_signal(
        self,
        symbol: str,
        side: OrderSide,
        volume: Decimal,
        insight: MarketInsightPayload,
        strategy: StrategyOptimizationPayload,
    ) -> Dict[str, Any]:
        metadata = {
            "insight": _serialize_value(insight.dict()),
            "strategy": _serialize_value(strategy.dict()),
            "trading_status": _serialize_value(trading_control.status().__dict__),
        }
        return {
            "signal_id": f"orchestrator-{uuid.uuid4().hex[:8]}",
            "symbol": symbol,
            "side": side.value,
            "order_type": OrderType.MARKET.value,
            "volume": str(volume),
            "time_in_force": "GTC",
            "client_order_id": f"orch-{uuid.uuid4().hex[:6]}",
            "metadata": metadata,
        }

    def _build_chat_context(self) -> Dict[str, Any]:
        insights = sorted(self._insights.values(), key=lambda value: value.timestamp, reverse=True)[:3]
        strategies = sorted(self._strategies.values(), key=lambda value: value.timestamp, reverse=True)[:3]
        history = list(self._context_history)
        status = trading_control.status()
        context: Dict[str, Any] = {
            "trading": {
                "paused": status.paused,
                "reason": status.reason,
                "triggered_by": status.triggered_by,
            },
            "insights": [_serialize_value(insight.dict()) for insight in insights],
            "strategies": [_serialize_value(strategy.dict()) for strategy in strategies],
            "history": history,
        }
        if self._last_risk_alert:
            context["risk_alert"] = _serialize_value(self._last_risk_alert)
        return context

    def _record_context_entry(self, entry_type: str, payload: Dict[str, Any]) -> None:
        entry = {
            "type": entry_type,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": _serialize_value(payload),
        }
        self._context_history.append(entry)

    def _log_event(self, level: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        sanitized = _serialize_value(details or {})
        log_method = getattr(logger, level, logger.info)
        log_method("%s | %s", message, sanitized)
        try:
            log_system_event.delay(level, "orchestrator", message, sanitized)
        except Exception as exc:
            logger.warning("Unable to enqueue log event: %s", exc)


orchestrator_agent = OrchestratorAgent()
