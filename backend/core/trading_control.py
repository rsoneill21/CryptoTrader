"""Trading pause control utilities and risk-driven hooks."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Any, Dict, Optional

from backend.core.message_queue import Channels, message_queue
from backend.core.tasks import log_system_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TradingPauseStatus:
    """Snapshot of the current trading pause state."""

    paused: bool
    reason: Optional[str]
    triggered_by: Optional[str]
    timestamp: Optional[datetime]


class TradingControl:
    """Manages the global trading pause state and listens for risk alerts."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._status = TradingPauseStatus(
            paused=False,
            reason=None,
            triggered_by=None,
            timestamp=None,
        )
        self._listener_lock = asyncio.Lock()
        self._listener_started = False

    def pause_trading(self, reason: Optional[str] = None, triggered_by: str = "manual") -> bool:
        """Pause trading if it is not already paused."""

        normalized_reason = (reason or "").strip() or f"{triggered_by} requested trading pause"

        with self._lock:
            if self._status.paused:
                logger.debug("Trading already paused; ignoring request from %s", triggered_by)
                return False
            self._status = TradingPauseStatus(
                paused=True,
                reason=normalized_reason,
                triggered_by=triggered_by,
                timestamp=datetime.utcnow(),
            )

        self._log_system_event("warning", "Trading paused", self._status)
        return True

    def resume_trading(self, reason: Optional[str] = None, triggered_by: str = "manual") -> bool:
        """Resume trading if currently paused."""

        resume_reason = (reason or "").strip() or f"{triggered_by} resumed trading"

        with self._lock:
            if not self._status.paused:
                logger.debug("Trading already active; ignoring resume request from %s", triggered_by)
                return False
            self._status = TradingPauseStatus(
                paused=False,
                reason=resume_reason,
                triggered_by=triggered_by,
                timestamp=datetime.utcnow(),
            )

        self._log_system_event("info", "Trading resumed", self._status)
        return True

    def is_paused(self) -> bool:
        """Return True when trading is currently paused."""

        with self._lock:
            return self._status.paused

    def status(self) -> TradingPauseStatus:
        """Return the current trading pause status snapshot."""

        with self._lock:
            return self._status

    async def start(self) -> None:
        """Connect to the message queue and subscribe to risk alerts."""

        async with self._listener_lock:
            if self._listener_started:
                return

            connected = await self._ensure_connection()
            if not connected:
                self._log_system_event(
                    "warning",
                    "Trading control could not connect to the message queue",
                    {"channel": Channels.RISK_ALERTS},
                )
                return

            subscribed = await message_queue.subscribe(
                Channels.RISK_ALERTS, self._handle_risk_alert
            )
            if not subscribed:
                self._log_system_event(
                    "warning",
                    "Trading control failed to subscribe to risk alerts",
                    {"channel": Channels.RISK_ALERTS},
                )
                return

            self._listener_started = True
            self._log_system_event(
                "debug",
                "Trading control listening for risk alerts",
                {"channel": Channels.RISK_ALERTS},
            )

    async def _ensure_connection(self) -> bool:
        """Make sure the shared message queue is connected."""

        if getattr(message_queue, "_redis", None) is not None:
            return True
        return await message_queue.connect()

    async def _handle_risk_alert(self, payload: Dict[str, Any]) -> None:
        """Pause trading when a risk alert payload arrives."""

        try:
            reason = self._build_reason(payload)
            paused = self.pause_trading(reason=reason, triggered_by="risk_monitor")
            if not paused:
                logger.debug("Risk alert received but trading already paused: %s", reason)
        except Exception as exc:  # pragma: no cover - best effort handling
            logger.warning("Error handling risk alert payload: %s", exc)

    def _build_reason(self, payload: Dict[str, Any]) -> str:
        """Create a concise reason message from the alert payload."""

        parts: list[str] = []
        score = self._safe_float(payload.get("score"))
        threshold = self._safe_float(payload.get("threshold"))
        if score is not None and threshold is not None:
            parts.append(f"risk score {score:.1f} >= threshold {threshold:.1f}")
        elif score is not None:
            parts.append(f"risk score {score:.1f}")
        elif threshold is not None:
            parts.append(f"threshold {threshold:.1f}")

        reasons = payload.get("reasons")
        if isinstance(reasons, list):
            parts.extend(str(item) for item in reasons if item)
        elif reasons:
            parts.append(str(reasons))

        if not parts:
            parts.append("Risk alert triggered")
        return " | ".join(parts)

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _log_system_event(self, level: str, message: str, details: Dict[str, Any]) -> None:
        """Log and persist trading control events."""

        sanitized = _serialize_value(details)
        log_method = getattr(logger, level, logger.info)
        log_method("%s | %s", message, sanitized)
        try:
            log_system_event.delay(level, "trading_control", message, sanitized)
        except Exception as exc:
            logger.warning("Unable to enqueue trading control log: %s", exc)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return value


trading_control = TradingControl()


def _schedule_start() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("Trading control risk listener deferred until event loop is running")
        return
    loop.create_task(trading_control.start())


_schedule_start()

