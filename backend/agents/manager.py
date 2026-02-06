"""
Agent Manager for lifecycle management and supervision.

Handles staggered startup, health checks, crash recovery, and graceful shutdown
for all autonomous agents.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from agents.base import BaseAgent
from agents.market_analyst import MarketAnalystAgent
from agents.orchestrator import OrchestratorAgent
from agents.trade_executor import TradeExecutorAgent
from core.message_queue import message_queue, Channels
from core.settings import get_app_settings
from core.tasks import log_system_event

logger = logging.getLogger(__name__)

HEARTBEAT_CHECK_INTERVAL = 10.0  # Check every 10 seconds
STALE_THRESHOLD = 30.0  # 30 seconds (allows 6 missed beats)



@dataclass
class PipelineEvent:
    """Represents a message flowing through the agent pipeline."""
    timestamp: datetime
    source_agent: str
    target_agent: str
    event_type: str  # e.g., "insight", "signal", "order"
    channel: str
    priority: int
    summary: str
    metadata: Dict[str, Any] = field(default_factory=dict)

class AgentManager:
    """
    Manages the lifecycle of all autonomous agents.

    Responsibilities:
    - Staggered startup with health checks
    - Supervision with immediate restart on failure
    - Crash-loop detection and backoff
    - Graceful shutdown
    - Status reporting
    - Queue metrics and pipeline event tracking
    """

    HEALTH_CHECK_TIMEOUT = 5.0
    CRASH_LOOP_WINDOW = 5.0  # seconds
    CRASH_LOOP_THRESHOLD = 3  # restarts within window
    CRASH_LOOP_BACKOFF = 10.0  # seconds

    def __init__(self) -> None:
        """Initialize the agent manager with configured replicas and intervals."""
        self._agents: Dict[str, BaseAgent] = {}
        self._supervisor_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._restart_counts: Dict[str, List[float]] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Pipeline event tracking
        self._pipeline_events: Deque[PipelineEvent] = deque(maxlen=100)
        self._message_counts: Dict[str, int] = {}  # channel -> count for throughput
        self._last_throughput_reset: float = 0.0

        # Load configuration
        settings = get_app_settings()

        # Create Market Analyst replicas
        analyst_count = settings.agent_market_analyst_instances
        analyst_interval = settings.agent_market_analyst_interval_seconds

        for i in range(1, analyst_count + 1):
            agent_name = f"market_analyst_{i}" if analyst_count > 1 else "market_analyst"
            agent = MarketAnalystAgent()
            agent.name = agent_name  # Override name for uniqueness
            agent._run_interval = analyst_interval
            self._agents[agent_name] = agent
            self._restart_counts[agent_name] = []

        # Create singleton Orchestrator
        orchestrator = OrchestratorAgent()
        orchestrator._run_interval = settings.agent_orchestrator_interval_seconds
        self._agents["orchestrator"] = orchestrator
        self._restart_counts["orchestrator"] = []

        # Create singleton Trade Executor
        executor = TradeExecutorAgent()
        executor._run_interval = settings.agent_trade_executor_interval_seconds
        self._agents["trade_executor"] = executor
        self._restart_counts["trade_executor"] = []

        logger.info(
            "AgentManager initialized with %d agents (%d market analysts)",
            len(self._agents),
            analyst_count,
        )

    async def start_all(self) -> None:
        """
        Start all agents in staggered sequence with health checks.

        Order: Market Analyst(s) -> Orchestrator -> Trade Executor
        """
        if self._running:
            logger.warning("AgentManager already running")
            return

        self._running = True
        logger.info("Starting all agents in staggered sequence")

        try:
            # Start all Market Analyst replicas
            analyst_names = [name for name in self._agents if name.startswith("market_analyst")]
            for agent_name in sorted(analyst_names):
                agent = self._agents[agent_name]
                await self._start_agent_with_health_check(agent)

            # Start Orchestrator
            orchestrator = self._agents["orchestrator"]
            await self._start_agent_with_health_check(orchestrator)

            # Start Trade Executor
            executor = self._agents["trade_executor"]
            await self._start_agent_with_health_check(executor)

            # Start heartbeat monitor
            self._heartbeat_task = asyncio.create_task(self._check_heartbeats())
            logger.info("Heartbeat monitor started")

            logger.info("All agents started successfully")
            self._log_system_event(
                "info",
                "Agent manager started all agents",
                {"agent_count": len(self._agents)},
            )

        except Exception as exc:
            logger.error("Failed to start agents: %s", exc, exc_info=True)
            self._log_system_event(
                "error",
                "Agent manager startup failed",
                {"error": str(exc)},
            )
            await self.stop_all()
            raise

    async def _start_agent_with_health_check(self, agent: BaseAgent) -> None:
        """Start an agent and wait for it to become healthy."""
        logger.info("Starting agent: %s", agent.name)

        # Launch supervisor task
        supervisor = asyncio.create_task(self._supervise_agent(agent))
        self._supervisor_tasks[agent.name] = supervisor

        # Wait for health check
        try:
            await self._wait_for_agent_health(agent, timeout=self.HEALTH_CHECK_TIMEOUT)
            logger.info("Agent %s is healthy", agent.name)
        except Exception as exc:
            logger.error("Agent %s failed health check: %s", agent.name, exc)
            raise

    async def _wait_for_agent_health(self, agent: BaseAgent, timeout: float) -> None:
        """
        Wait for agent to report healthy status.

        Health criteria:
        - agent.is_running is True
        - agent.get_status()["queue_size"] >= 0
        """
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            try:
                if agent.is_running:
                    status = agent.get_status()
                    if status.get("queue_size", -1) >= 0:
                        return
            except Exception as exc:
                logger.debug("Health check exception for %s: %s", agent.name, exc)

            await asyncio.sleep(0.1)

        raise TimeoutError(f"Agent {agent.name} did not become healthy within {timeout}s")

    async def _supervise_agent(self, agent: BaseAgent) -> None:
        """
        Supervise an agent with immediate restart on failure.

        Implements crash-loop detection:
        - If 3+ restarts within 5 seconds, back off for 10 seconds
        """
        while self._running:
            try:
                await agent.start()
                # If start() returns normally, agent stopped gracefully
                logger.info("Agent %s stopped normally", agent.name)
                break

            except asyncio.CancelledError:
                # Clean shutdown requested
                logger.info("Agent %s supervisor cancelled", agent.name)
                break

            except Exception as exc:
                # Agent crashed - restart immediately
                self._record_restart(agent.name)
                restart_count = len(self._restart_counts[agent.name])

                logger.exception("Agent %s crashed: %s", agent.name, exc)
                self._log_system_event(
                    "error",
                    f"Agent {agent.name} crashed",
                    {
                        "error": str(exc),
                        "restart_count": restart_count,
                    },
                )

                # Check for crash loop
                if self._is_crash_looping(agent.name):
                    logger.warning(
                        "Agent %s crash-looping (%d restarts in %ds), backing off for %ds",
                        agent.name,
                        self.CRASH_LOOP_THRESHOLD,
                        self.CRASH_LOOP_WINDOW,
                        self.CRASH_LOOP_BACKOFF,
                    )
                    self._log_system_event(
                        "warning",
                        f"Agent {agent.name} crash-looping",
                        {
                            "restart_count": restart_count,
                            "backoff_seconds": self.CRASH_LOOP_BACKOFF,
                        },
                    )
                    await asyncio.sleep(self.CRASH_LOOP_BACKOFF)
                else:
                    # Brief delay before restart
                    await asyncio.sleep(1.0)

    async def _check_heartbeats(self) -> None:
        """Monitor loop that checks agent heartbeats and restarts stale agents."""
        while self._running:
            for name, agent in self._agents.items():
                if not agent._running or agent._paused:
                    continue

                try:
                    loop_time = asyncio.get_running_loop().time()
                    age = loop_time - agent._last_heartbeat
                except RuntimeError:
                    continue

                if agent._last_heartbeat > 0 and age > STALE_THRESHOLD:
                    logger.error(
                        f"Agent {name} heartbeat stale ({age:.1f}s > {STALE_THRESHOLD}s), forcing restart"
                    )

                    # Cancel the supervisor task to trigger restart
                    supervisor_task = self._supervisor_tasks.get(name)
                    if supervisor_task and not supervisor_task.done():
                        # Stop the agent first to reset state
                        await agent.stop()
                        # Supervisor will catch the stop and restart

            await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL)

    def _record_restart(self, agent_name: str) -> None:
        """Record a restart timestamp for crash-loop detection."""
        now = asyncio.get_running_loop().time()
        self._restart_counts[agent_name].append(now)

        # Keep only recent restarts
        cutoff = now - self.CRASH_LOOP_WINDOW
        self._restart_counts[agent_name] = [
            ts for ts in self._restart_counts[agent_name] if ts > cutoff
        ]

    def _is_crash_looping(self, agent_name: str) -> bool:
        """Check if agent is crash-looping (3+ restarts in 5 seconds)."""
        return len(self._restart_counts[agent_name]) >= self.CRASH_LOOP_THRESHOLD

    async def get_queue_metrics(self) -> Dict[str, Any]:
        """
        Get queue metrics for dashboard display.

        Returns depth, throughput, and latency estimates.
        """
        metrics = {
            "channels": {},
            "total_depth": 0,
            "throughput_per_minute": {},
        }

        # Get depth for each stream channel
        for channel_name in [Channels.STREAM_TRADE_SIGNALS, Channels.STREAM_RISK_ALERTS]:
            try:
                depths = await message_queue.get_queue_depth(channel_name)
                metrics["channels"][channel_name] = depths
                metrics["total_depth"] += depths.get("total", 0)
            except Exception as e:
                logger.warning(f"Failed to get queue depth for {channel_name}: {e}")
                metrics["channels"][channel_name] = {"error": str(e)}

        # Calculate throughput (messages per minute since last reset)
        try:
            loop_time = asyncio.get_running_loop().time()
            elapsed = loop_time - self._last_throughput_reset
            if elapsed > 0:
                for channel, count in self._message_counts.items():
                    metrics["throughput_per_minute"][channel] = round(count * 60 / elapsed, 2)
        except RuntimeError:
            pass

        return metrics

    def get_recent_pipeline_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent pipeline events for timeline display.

        Per user decision: "pipeline timeline illustrating recent messages
        flowing through the loop."
        """
        events = list(self._pipeline_events)[-limit:]
        return [
            {
                "timestamp": event.timestamp.isoformat(),
                "source_agent": event.source_agent,
                "target_agent": event.target_agent,
                "event_type": event.event_type,
                "channel": event.channel,
                "priority": event.priority,
                "summary": event.summary,
                "metadata": event.metadata,
            }
            for event in reversed(events)  # Most recent first
        ]

    def record_pipeline_event(
        self,
        source_agent: str,
        target_agent: str,
        event_type: str,
        channel: str,
        priority: int = 2,
        summary: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a pipeline event for timeline tracking."""
        event = PipelineEvent(
            timestamp=datetime.utcnow(),
            source_agent=source_agent,
            target_agent=target_agent,
            event_type=event_type,
            channel=channel,
            priority=priority,
            summary=summary,
            metadata=metadata or {},
        )
        self._pipeline_events.append(event)

        # Update throughput counter
        self._message_counts[channel] = self._message_counts.get(channel, 0) + 1

    def reset_throughput_counters(self) -> None:
        """Reset throughput counters (call periodically, e.g., every minute)."""
        self._message_counts.clear()
        try:
            self._last_throughput_reset = asyncio.get_running_loop().time()
        except RuntimeError:
            self._last_throughput_reset = 0.0

    async def stop_all(self) -> None:
        """Stop all agents gracefully."""
        if not self._running:
            logger.warning("AgentManager not running")
            return

        logger.info("Stopping all agents")
        self._running = False

        # Stop heartbeat monitor
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Stop all agents
        for agent in self._agents.values():
            try:
                await agent.stop()
            except Exception as exc:
                logger.error("Error stopping agent %s: %s", agent.name, exc)

        # Cancel all supervisor tasks
        for task in self._supervisor_tasks.values():
            task.cancel()

        # Wait for all supervisors to finish
        if self._supervisor_tasks:
            await asyncio.gather(*self._supervisor_tasks.values(), return_exceptions=True)

        self._supervisor_tasks.clear()
        logger.info("All agents stopped")
        self._log_system_event(
            "info",
            "Agent manager stopped all agents",
            {"agent_count": len(self._agents)},
        )

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """Get an agent by name."""
        return self._agents.get(name)

    def get_all_status(self) -> Dict[str, dict]:
        """Get status of all agents."""
        return {name: agent.get_status() for name, agent in self._agents.items()}

    def _log_system_event(
        self, level: str, message: str, details: Optional[dict] = None
    ) -> None:
        """Log a system event via Celery task."""
        try:
            log_system_event.delay(level, "agent_manager", message, details or {})
        except Exception as exc:
            logger.warning("Failed to log system event: %s", exc)
