"""Health monitoring helpers for the CryptoTrader backend."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from statistics import mean
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Type

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.base import AgentRegistry
from db.database import SessionLocal
from services.kraken import kraken_service
from services.kraken_ws import kraken_ws

logger = logging.getLogger(__name__)

ComponentStatusType = Literal[
    "healthy",
    "degraded",
    "offline",
    "initializing",
    "unknown",
    "not_configured",
]


class ComponentHealth(BaseModel):
    """Describes the health state of a single infrastructure component."""

    name: str
    status: ComponentStatusType
    healthy: bool
    details: Optional[str] = None
    latency_ms: Optional[float] = Field(None, ge=0)
    last_checked: datetime = Field(default_factory=datetime.utcnow)


class AgentHealth(BaseModel):
    """Highlights the latest runtime details for a registered agent."""

    name: str
    running: bool
    paused: bool
    queue_size: int
    description: Optional[str] = None
    last_seen: datetime = Field(default_factory=datetime.utcnow)


class SystemHealthReport(BaseModel):
    """Aggregated system health report exposed via the health endpoint."""

    overall_status: Literal["healthy", "degraded"]
    version: str
    checked_at: datetime
    components: List[ComponentHealth]
    agents: List[AgentHealth]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HealthMonitorService:
    """Gathers live status information about the core backend services."""

    def __init__(
        self,
        version: str = "0.1.0",
        session_factory: Callable[[], Session] = SessionLocal,
        agent_registry: Type[AgentRegistry] = AgentRegistry,
        kraken_ws_client=kraken_ws,
        kraken_rest=kraken_service,
    ) -> None:
        self._version = version
        self._session_factory = session_factory
        self._agent_registry = agent_registry
        self._kraken_ws = kraken_ws_client
        self._kraken_rest = kraken_rest

    async def _check_database(self) -> ComponentHealth:
        start = datetime.utcnow()
        try:
            await asyncio.to_thread(self._database_probe)
        except Exception as exc:  # pragma: no cover - best effort
            latency = (datetime.utcnow() - start).total_seconds() * 1000
            logger.exception("Database health probe failed")
            return ComponentHealth(
                name="database",
                status="degraded",
                healthy=False,
                details=f"Database probe error: {exc}",
                latency_ms=latency,
                last_checked=datetime.utcnow(),
            )

        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return ComponentHealth(
            name="database",
            status="healthy",
            healthy=True,
            details="Database connection ok",
            latency_ms=latency,
            last_checked=datetime.utcnow(),
        )

    @staticmethod
    def _database_probe() -> None:
        session = SessionLocal()
        try:
            session.execute(text("SELECT 1"))
        finally:
            session.close()

    async def _check_agents(self) -> Tuple[ComponentHealth, List[AgentHealth]]:
        timestamp = datetime.utcnow()
        raw_status = self._agent_registry.get_status()
        agent_states: List[AgentHealth] = []
        any_running = False

        for agent_info in raw_status.values():
            running = bool(agent_info.get("running"))
            paused = bool(agent_info.get("paused"))
            agent_states.append(
                AgentHealth(
                    name=agent_info.get("name", "<unknown>"),
                    description=agent_info.get("description"),
                    running=running,
                    paused=paused,
                    queue_size=int(agent_info.get("queue_size", 0)),
                    last_seen=timestamp,
                )
            )
            if running:
                any_running = True

        if not agent_states:
            status = "initializing"
            healthy_flag = True
            details = "Agents starting up"
        else:
            status = "healthy" if any_running else "degraded"
            healthy_flag = any_running
            details = f"{len(agent_states)} agent(s) registered"

        component = ComponentHealth(
            name="agents",
            status=status,
            healthy=healthy_flag,
            details=details,
            last_checked=timestamp,
        )

        return component, agent_states

    async def _check_kraken_api(self) -> ComponentHealth:
        timestamp = datetime.utcnow()
        authenticated = self._kraken_rest.is_authenticated

        if authenticated:
            status = "healthy"
            healthy = True
            details = "Kraken REST API authenticated"
        else:
            status = "not_configured"
            healthy = True
            details = "Kraken API keys missing (only public endpoints available)"

        return ComponentHealth(
            name="kraken",
            status=status,
            healthy=healthy,
            details=details,
            last_checked=timestamp,
        )

    async def _check_kraken_ws(self) -> ComponentHealth:
        timestamp = datetime.utcnow()
        connected = self._kraken_ws.is_connected
        status = "healthy" if connected else "degraded"

        return ComponentHealth(
            name="kraken_ws",
            status=status,
            healthy=connected,
            details="Connected to Kraken WebSocket" if connected else "Kraken WebSocket disconnected",
            last_checked=timestamp,
        )

    def _redis_placeholder(self) -> ComponentHealth:
        timestamp = datetime.utcnow()
        return ComponentHealth(
            name="redis",
            status="not_configured",
            healthy=True,
            details="Redis not configured; optional for pub/sub",
            last_checked=timestamp,
        )

    async def get_health_report(self) -> SystemHealthReport:
        checked_at = datetime.utcnow()
        db_task = self._check_database()
        kraken_api_task = self._check_kraken_api()
        kraken_ws_task = self._check_kraken_ws()
        db_component, kraken_api_component, kraken_ws_component = await asyncio.gather(
            db_task, kraken_api_task, kraken_ws_task
        )

        agents_component, agents = await self._check_agents()
        components = [
            db_component,
            kraken_api_component,
            kraken_ws_component,
            agents_component,
            self._redis_placeholder(),
        ]

        critical_failures = [
            component
            for component in components
            if (
                not component.healthy
                and component.status not in {"not_configured", "initializing", "unknown"}
            )
        ]

        overall_status = "healthy" if not critical_failures else "degraded"

        latencies = [c.latency_ms for c in components if c.latency_ms is not None]
        metadata = {
            "component_count": len(components),
            "agent_count": len(agents),
            "running_agents": sum(1 for agent in agents if agent.running),
            "paused_agents": sum(1 for agent in agents if agent.paused),
            "healthy_components": sum(1 for component in components if component.healthy),
            "degraded_components": sum(1 for component in components if not component.healthy),
            "avg_latency_ms": float(mean(latencies)) if latencies else None,
        }

        return SystemHealthReport(
            overall_status=overall_status,
            version=self._version,
            checked_at=checked_at,
            components=components,
            agents=agents,
            metadata=metadata,
        )


health_monitor_service = HealthMonitorService()
