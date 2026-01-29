"""
Base agent class and registry for the multi-agent architecture.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional, Callable, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """Message passed between agents."""
    sender: str
    recipient: str
    message_type: str
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None
    priority: int = 0  # Higher = more priority


class AgentRegistry:
    """
    Registry for managing agent instances.

    Provides centralized access to all agents and their status.
    """
    _instance = None
    _agents: Dict[str, "BaseAgent"] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._agents = {}
        return cls._instance

    @classmethod
    def register(cls, agent: "BaseAgent") -> None:
        """Register an agent."""
        cls._agents[agent.name] = agent
        logger.info(f"Agent registered: {agent.name}")

    @classmethod
    def unregister(cls, name: str) -> None:
        """Unregister an agent."""
        if name in cls._agents:
            del cls._agents[name]
            logger.info(f"Agent unregistered: {name}")

    @classmethod
    def get(cls, name: str) -> Optional["BaseAgent"]:
        """Get an agent by name."""
        return cls._agents.get(name)

    @classmethod
    def get_all(cls) -> Dict[str, "BaseAgent"]:
        """Get all registered agents."""
        return cls._agents.copy()

    @classmethod
    def get_status(cls) -> Dict[str, Dict[str, Any]]:
        """Get status of all agents."""
        return {
            name: agent.get_status()
            for name, agent in cls._agents.items()
        }


class BaseAgent(ABC):
    """
    Abstract base class for all AI agents.

    Provides common functionality for:
    - Lifecycle management (start, stop, pause)
    - Message handling
    - Status reporting
    - Error handling
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._running = False
        self._paused = False
        self._started_at: Optional[datetime] = None
        self._message_handlers: Dict[str, Callable] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

        # Register with global registry
        AgentRegistry.register(self)

    @property
    def is_running(self) -> bool:
        """Check if agent is running."""
        return self._running and not self._paused

    async def start(self) -> None:
        """Start the agent."""
        if self._running:
            logger.warning(f"Agent {self.name} already running")
            return

        logger.info(f"Starting agent: {self.name}")
        self._running = True
        self._paused = False
        self._started_at = datetime.utcnow()

        # Start the main run loop
        self._task = asyncio.create_task(self._run_loop())

        await self.on_start()

    async def stop(self) -> None:
        """Stop the agent."""
        if not self._running:
            return

        logger.info(f"Stopping agent: {self.name}")
        self._running = False

        # Cancel the task
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        await self.on_stop()

    def pause(self) -> None:
        """Pause the agent (stops processing but stays running)."""
        if self._running and not self._paused:
            logger.info(f"Pausing agent: {self.name}")
            self._paused = True

    def resume(self) -> None:
        """Resume a paused agent."""
        if self._running and self._paused:
            logger.info(f"Resuming agent: {self.name}")
            self._paused = False

    async def _run_loop(self) -> None:
        """Main run loop for the agent."""
        while self._running:
            try:
                if self._paused:
                    await asyncio.sleep(0.1)
                    continue

                # Process messages
                try:
                    message = self._message_queue.get_nowait()
                    await self._handle_message(message)
                except asyncio.QueueEmpty:
                    pass

                # Run agent-specific logic
                await self.run()

                # Small delay to prevent tight loop
                await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in agent {self.name}: {e}", exc_info=True)
                await self.on_error(e)
                await asyncio.sleep(1)  # Back off on error

    async def _handle_message(self, message: AgentMessage) -> None:
        """Handle an incoming message."""
        handler = self._message_handlers.get(message.message_type)
        if handler:
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"Error handling message {message.message_type}: {e}")
        else:
            await self.process_message(message)

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        self._message_handlers[message_type] = handler

    async def send_message(
        self,
        recipient: str,
        message_type: str,
        payload: Dict[str, Any],
        priority: int = 0
    ) -> None:
        """
        Send a message to another agent.

        Args:
            recipient: Name of the recipient agent
            message_type: Type of message
            payload: Message data
            priority: Message priority (higher = more important)
        """
        message = AgentMessage(
            sender=self.name,
            recipient=recipient,
            message_type=message_type,
            payload=payload,
            priority=priority,
        )

        target = AgentRegistry.get(recipient)
        if target:
            await target.receive_message(message)
        else:
            logger.warning(f"Agent {recipient} not found")

    async def receive_message(self, message: AgentMessage) -> None:
        """Receive a message from another agent."""
        await self._message_queue.put(message)

    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        return {
            "name": self.name,
            "description": self.description,
            "running": self._running,
            "paused": self._paused,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "queue_size": self._message_queue.qsize(),
        }

    # Abstract methods to be implemented by subclasses

    @abstractmethod
    async def run(self) -> None:
        """
        Main agent logic. Called repeatedly while running.

        Implement this method with the agent's specific behavior.
        """
        pass

    @abstractmethod
    async def process_message(self, message: AgentMessage) -> None:
        """
        Process a message that doesn't have a specific handler.

        Args:
            message: The message to process
        """
        pass

    # Optional lifecycle hooks

    async def on_start(self) -> None:
        """Called when the agent starts. Override for custom startup logic."""
        pass

    async def on_stop(self) -> None:
        """Called when the agent stops. Override for custom shutdown logic."""
        pass

    async def on_error(self, error: Exception) -> None:
        """Called when an error occurs. Override for custom error handling."""
        pass
