"""
Trade Executor agent.

Listens for validated trade signals, submits orders through the Kraken service, and tracks
execution status while logging every action.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field, ValidationError, validator

from agents.base import AgentMessage, BaseAgent
from core.exceptions import RiskException
from core.message_queue import Channels, message_queue
from core.risk import RiskService
from core.tasks import log_system_event
from db.database import AsyncSessionLocal
from services.kraken import (
    KrakenAPIError,
    OrderSide,
    OrderStatus,
    OrderType,
    kraken_service,
)

logger = logging.getLogger(__name__)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, set):
        return [_serialize_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_serialize_value(v) for v in value)
    return value


class TradeSignal(BaseModel):
    signal_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    volume: Decimal
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    client_order_id: Optional[str] = None
    time_in_force: str = "GTC"
    leverage: Optional[str] = None
    reduce_only: bool = False
    validate_only: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator("volume", "price", "stop_price", pre=True)
    def _to_decimal(cls, value: Any) -> Any:
        if value is None or isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @validator("volume")
    def _validate_volume(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("volume must be greater than zero")
        return value


@dataclass
class PendingOrder:
    signal: TradeSignal
    retries: int = 0
    order_ids: List[str] = field(default_factory=list)
    last_error: Optional[str] = None
    last_status: Optional[str] = None
    fallback_attempts: int = 0
    original_volume: Optional[Decimal] = None


class TradeExecutorAgent(BaseAgent):
    """Agent that executes trade signals via Kraken."""

    MAX_RETRIES = 3
    RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
    STATUS_POLL_INTERVAL = 5.0
    FALLBACK_VOLUME_REDUCTION = Decimal("0.5")  # Reduce to 50%
    MIN_FALLBACK_VOLUME = Decimal("0.001")  # Minimum volume
    MAX_FALLBACK_ATTEMPTS = 2

    def __init__(self) -> None:
        super().__init__(
            name="trade_executor",
            description="Executes Kraken orders for validated trade signals",
        )
        self._pending_orders: Dict[str, PendingOrder] = {}
        self._signal_tasks: Set[asyncio.Task[Any]] = set()
        self._next_status_poll: float = 0.0
        self._signal_channel = Channels.TRADE_SIGNALS
        self._consumer_task: Optional[asyncio.Task] = None

    async def on_start(self) -> None:
        try:
            await message_queue.connect()
        except Exception as exc:  # pragma: no cover - best effort setup
            self._log_system_event(
                "warning",
                "Message queue connection failed",
                {"error": str(exc)},
            )

        # Start consuming from Redis Streams with consumer group
        self._consumer_task = asyncio.create_task(self._consume_trade_signals())
        self._log_system_event(
            "info",
            "Trade Executor stream consumer started",
            {},
        )

        # Keep pub/sub subscription for backward compatibility
        try:
            subscribed = await message_queue.subscribe(
                self._signal_channel,
                self._on_trade_signal,
            )
            if subscribed:
                self._log_system_event(
                    "info",
                    "Subscribed to trade signals pub/sub",
                    {"channel": self._signal_channel},
                )
        except Exception as exc:  # pragma: no cover - wrap unexpected failures
            self._log_system_event(
                "error",
                "Pub/sub subscription exception",
                {"error": str(exc)},
            )

    async def on_stop(self) -> None:
        # Cancel stream consumer
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._log_system_event("info", "Stream consumer stopped", {})

        try:
            await message_queue.unsubscribe(self._signal_channel)
        except Exception as exc:  # pragma: no cover - best effort cleanup
            self._log_system_event("warning", "Failed to unsubscribe", {"error": str(exc)})

        for task in list(self._signal_tasks):
            task.cancel()

        if self._signal_tasks:
            await asyncio.gather(*self._signal_tasks, return_exceptions=True)
            self._signal_tasks.clear()

        self._log_system_event("info", "Trade executor agent stopped")

    async def run(self) -> None:
        await self._poll_pending_orders()
        await asyncio.sleep(0.1)

    async def process_message(self, message: AgentMessage) -> None:
        self._log_system_event(
            "debug",
            "Agent message received",
            {
                "sender": message.sender,
                "type": message.message_type,
                "payload": _serialize_value(message.payload),
            },
        )

    async def _consume_trade_signals(self) -> None:
        """Consume trade signals from Redis Streams with at-least-once delivery."""
        try:
            await message_queue.consume_reliable(
                channel=Channels.STREAM_TRADE_SIGNALS,
                group="trade_executor_group",
                consumer=f"executor_{id(self)}",
                callback=self._on_stream_trade_signal,
            )
        except asyncio.CancelledError:
            logger.info("Trade signal consumer cancelled")
        except Exception as exc:
            logger.error(f"Trade signal consumer error: {exc}", exc_info=True)
            self._log_system_event(
                "error",
                "Trade signal consumer failed",
                {"error": str(exc)},
            )

    async def _on_stream_trade_signal(self, payload: Dict[str, Any]) -> None:
        """Handle trade signal from Redis Stream."""
        # Log analysis context received for audit trail
        analysis_context = payload.get("analysis_context", {})
        if analysis_context:
            self._log_system_event(
                "info",
                "Signal received with analysis context",
                {
                    "signal_id": payload.get("signal_id"),
                    "triggering_insights_count": len(analysis_context.get("triggering_insights", [])),
                    "strategy_name": analysis_context.get("strategy_name"),
                    "decision_rationale": analysis_context.get("decision_rationale"),
                },
            )

        # Process signal same as pub/sub
        await self._on_trade_signal(payload)

    def _track_signal_task(self, task: asyncio.Task[Any]) -> None:
        self._signal_tasks.add(task)
        task.add_done_callback(self._signal_task_done)

    def _signal_task_done(self, task: asyncio.Task[Any]) -> None:
        self._signal_tasks.discard(task)
        if task.cancelled():
            logger.debug("Trade signal task cancelled")
            return
        exception = task.exception()
        if exception:
            self._log_system_event(
                "error",
                "Trade signal handler failed",
                {"error": str(exception)},
            )

    async def _on_trade_signal(self, payload: Dict[str, Any]) -> None:
        try:
            signal = TradeSignal(**payload)
        except ValidationError as exc:
            self._log_system_event(
                "warning",
                "Invalid trade signal payload",
                {"error": str(exc), "payload": _serialize_value(payload)},
            )
            return

        self._log_system_event("info", "Trade signal received", self._signal_details(signal))

        task = asyncio.create_task(self._handle_signal(signal))
        self._track_signal_task(task)

    async def _handle_signal(self, signal: TradeSignal) -> None:
        pending = PendingOrder(signal=signal)
        self._pending_orders[signal.signal_id] = pending

        if signal.validate_only:
            self._log_system_event(
                "info",
                "Dry-run trade signal acknowledged",
                self._signal_details(signal),
            )
            self._pending_orders.pop(signal.signal_id, None)
            return

        if not await self._validate_signal_risk(signal):
            self._pending_orders.pop(signal.signal_id, None)
            return

        # Try primary order placement
        order_ids = await self._place_order_with_retries(signal, pending)
        if not order_ids:
            # Primary placement failed, apply fallback strategy
            order_ids = await self._apply_fallback_strategy(signal, pending)
            if not order_ids:
                # Fallback exhausted, mark signal as failed
                self._log_system_event(
                    "error",
                    "Signal failed after fallback exhausted",
                    {
                        **self._signal_details(signal),
                        "primary_retries": pending.retries,
                        "fallback_attempts": pending.fallback_attempts,
                        "last_error": pending.last_error,
                        "original_volume": str(pending.original_volume) if pending.original_volume else None,
                    },
                )
                self._pending_orders.pop(signal.signal_id, None)
                return

        pending.order_ids = order_ids

    async def _validate_signal_risk(self, signal: TradeSignal) -> bool:
        price = signal.price
        if price is None:
            try:
                ticker = await kraken_service.get_ticker(signal.symbol)
                price = ticker.last
            except Exception as exc:
                self._log_system_event(
                    "error",
                    "Failed to resolve trade price for risk validation",
                    {**self._signal_details(signal), "error": str(exc)},
                )
                return False

        try:
            async with AsyncSessionLocal() as session:
                await RiskService.validate_trade(
                    db=session,
                    symbol=signal.symbol,
                    quantity=float(signal.volume),
                    price=float(price),
                    side=signal.side.value,
                )
            return True
        except RiskException as exc:
            details = {**self._signal_details(signal), "error": exc.message, "risk": exc.detail}
            self._log_system_event("warning", "Trade signal rejected by risk service", details)
            return False
        except Exception as exc:
            self._log_system_event(
                "error",
                "Risk validation failed unexpectedly",
                {**self._signal_details(signal), "error": str(exc)},
            )
            return False

    async def _place_order_with_retries(
        self, signal: TradeSignal, pending: PendingOrder
    ) -> List[str]:
        if not kraken_service.is_authenticated:
            self._log_system_event(
                "error",
                "Kraken credentials missing",
                self._signal_details(signal),
            )
            return []

        base_details = self._signal_details(signal)

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = await kraken_service.place_order(
                    symbol=signal.symbol,
                    side=signal.side,
                    order_type=signal.order_type,
                    volume=signal.volume,
                    price=signal.price,
                    stop_price=signal.stop_price,
                    leverage=signal.leverage,
                    reduce_only=signal.reduce_only,
                    time_in_force=signal.time_in_force,
                    client_order_id=signal.client_order_id or signal.signal_id,
                )

                order_ids = [str(order_id) for order_id in result.get("order_ids", [])]
                details = {**base_details, "attempt": attempt, "order_ids": order_ids}
                self._log_system_event("info", "Order placed via Kraken", details)
                pending.order_ids = order_ids
                return order_ids
            except KrakenAPIError as exc:
                pending.last_error = str(exc)
                pending.retries = attempt
                details = {
                    **base_details,
                    "attempt": attempt,
                    "error": str(exc),
                }
                self._log_system_event(
                    "warning",
                    "Kraken API error while placing order",
                    details,
                )
            except Exception as exc:  # pragma: no cover - guard unexpected failures
                pending.last_error = str(exc)
                pending.retries = attempt
                details = {
                    **base_details,
                    "attempt": attempt,
                    "error": str(exc),
                }
                self._log_system_event(
                    "error",
                    "Unexpected error while placing order",
                    details,
                )

            if attempt < self.MAX_RETRIES:
                backoff = self.RETRY_BACKOFF_SECONDS[min(attempt - 1, len(self.RETRY_BACKOFF_SECONDS) - 1)]
                await asyncio.sleep(backoff)

        self._log_system_event(
            "error",
            "Exceeded retry limit while placing Kraken order",
            {**base_details, "retries": self.MAX_RETRIES},
        )
        return []

    async def _apply_fallback_strategy(
        self, signal: TradeSignal, pending: PendingOrder
    ) -> List[str]:
        """Apply fallback strategy by reducing volume and retrying."""
        # Save original volume on first fallback
        if pending.original_volume is None:
            pending.original_volume = signal.volume

        # Check if fallback attempts exhausted
        if pending.fallback_attempts >= self.MAX_FALLBACK_ATTEMPTS:
            self._log_system_event(
                "error",
                "Fallback attempts exhausted for signal",
                {
                    **self._signal_details(signal),
                    "original_volume": str(pending.original_volume),
                    "fallback_attempts": pending.fallback_attempts,
                },
            )
            return []

        # Calculate reduced volume
        reduced_volume = signal.volume * self.FALLBACK_VOLUME_REDUCTION
        pending.fallback_attempts += 1

        # Check minimum volume threshold
        if reduced_volume < self.MIN_FALLBACK_VOLUME:
            self._log_system_event(
                "error",
                "Reduced volume below minimum threshold",
                {
                    **self._signal_details(signal),
                    "original_volume": str(pending.original_volume),
                    "reduced_volume": str(reduced_volume),
                    "min_volume": str(self.MIN_FALLBACK_VOLUME),
                    "fallback_attempts": pending.fallback_attempts,
                },
            )
            return []

        # Log fallback action
        self._log_system_event(
            "warning",
            "Applying fallback strategy with reduced volume",
            {
                **self._signal_details(signal),
                "original_volume": str(pending.original_volume),
                "reduced_volume": str(reduced_volume),
                "fallback_attempts": pending.fallback_attempts,
                "reduction_factor": str(self.FALLBACK_VOLUME_REDUCTION),
            },
        )

        # Create modified signal with reduced volume
        signal.volume = reduced_volume

        if not await self._validate_signal_risk(signal):
            return []

        # Retry with reduced volume
        return await self._place_order_with_retries(signal, pending)

    async def _poll_pending_orders(self) -> None:
        if not self._pending_orders:
            return

        now = asyncio.get_running_loop().time()
        if now < self._next_status_poll:
            return

        self._next_status_poll = now + self.STATUS_POLL_INTERVAL

        for signal_id, pending in list(self._pending_orders.items()):
            if not pending.order_ids:
                continue

            order_id = pending.order_ids[0]

            try:
                status = await kraken_service.get_order_status(order_id)
            except KrakenAPIError as exc:
                self._log_system_event(
                    "warning",
                    "Failed to fetch order status",
                    {"order_id": order_id, "signal_id": signal_id, "error": str(exc)},
                )
                continue
            except Exception as exc:  # pragma: no cover - keep polling resilient
                self._log_system_event(
                    "error",
                    "Unexpected error polling order status",
                    {"order_id": order_id, "signal_id": signal_id, "error": str(exc)},
                )
                continue

            pending.last_status = status.status.value

            if status.status in (OrderStatus.CLOSED, OrderStatus.CANCELED, OrderStatus.EXPIRED):
                self._log_system_event(
                    "info",
                    "Order reached terminal status",
                    {
                        "signal_id": signal_id,
                        "order_id": order_id,
                        "status": status.status.value,
                        "filled_volume": str(status.filled_volume),
                        "cost": str(status.cost),
                        "fee": str(status.fee),
                    },
                )
                self._pending_orders.pop(signal_id, None)
            else:
                logger.debug(
                    "Order %s for signal %s still %s",
                    order_id,
                    signal_id,
                    status.status.value,
                )

    def _signal_details(
        self, signal: TradeSignal, extra: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        details = {
            "signal_id": signal.signal_id,
            "symbol": signal.symbol,
            "side": signal.side.value,
            "order_type": signal.order_type.value,
            "volume": str(signal.volume),
            "price": str(signal.price) if signal.price is not None else None,
            "stop_price": str(signal.stop_price) if signal.stop_price is not None else None,
            "client_order_id": signal.client_order_id,
            "time_in_force": signal.time_in_force,
            "leverage": signal.leverage,
            "reduce_only": signal.reduce_only,
            "validate_only": signal.validate_only,
            "metadata": _serialize_value(signal.metadata),
        }

        if extra:
            details.update(extra)

        return details

    def _log_system_event(
        self, level: str, message: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        sanitized = _serialize_value(details or {})
        logger_method = getattr(logger, level, logger.info)
        logger_method("%s | %s", message, sanitized)

        try:
            log_system_event.delay(level, "trade_executor", message, sanitized)
        except Exception as exc:  # pragma: no cover - ensure best effort logging
            logger.warning("Unable to enqueue system log: %s", exc)


trade_executor_agent = TradeExecutorAgent()
