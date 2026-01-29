"""
Message queue interface for agent communication using Redis pub/sub.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional
from datetime import datetime
import os

logger = logging.getLogger(__name__)

# Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class MessageQueue:
    """
    Redis-based message queue for inter-agent communication.

    Provides pub/sub functionality for agents to communicate
    without direct coupling.
    """

    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self._redis = None
        self._pubsub = None
        self._subscriptions: Dict[str, Callable] = {}
        self._running = False
        self._listener_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """
        Connect to Redis.

        Returns:
            True if connected successfully, False otherwise
        """
        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.redis_url)
            await self._redis.ping()
            self._pubsub = self._redis.pubsub()
            logger.info("Connected to Redis message queue")
            return True
        except ImportError:
            logger.warning("redis package not installed. Install with: pip install redis")
            return False
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}. Using in-memory fallback.")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        self._running = False

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            await self._pubsub.close()

        if self._redis:
            await self._redis.close()

        logger.info("Disconnected from Redis message queue")

    async def publish(self, channel: str, message: Dict[str, Any]) -> bool:
        """
        Publish a message to a channel.

        Args:
            channel: Channel name to publish to
            message: Message data as dict

        Returns:
            True if published successfully
        """
        if not self._redis:
            logger.warning("Not connected to Redis")
            # Fallback: directly call local subscribers
            return await self._local_publish(channel, message)

        try:
            # Add metadata
            message["_timestamp"] = datetime.utcnow().isoformat()
            message["_channel"] = channel

            await self._redis.publish(channel, json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Error publishing to {channel}: {e}")
            return False

    async def subscribe(self, channel: str, callback: Callable) -> bool:
        """
        Subscribe to a channel.

        Args:
            channel: Channel name to subscribe to
            callback: Async function to call when message received

        Returns:
            True if subscribed successfully
        """
        self._subscriptions[channel] = callback

        if not self._pubsub:
            logger.warning("Not connected to Redis, using local subscription")
            return True

        try:
            await self._pubsub.subscribe(channel)

            # Start listener if not running
            if not self._running:
                self._running = True
                self._listener_task = asyncio.create_task(self._listen())

            logger.info(f"Subscribed to channel: {channel}")
            return True
        except Exception as e:
            logger.error(f"Error subscribing to {channel}: {e}")
            return False

    async def unsubscribe(self, channel: str) -> bool:
        """
        Unsubscribe from a channel.

        Args:
            channel: Channel name to unsubscribe from

        Returns:
            True if unsubscribed successfully
        """
        if channel in self._subscriptions:
            del self._subscriptions[channel]

        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(channel)
                logger.info(f"Unsubscribed from channel: {channel}")
            except Exception as e:
                logger.error(f"Error unsubscribing from {channel}: {e}")
                return False

        return True

    async def _listen(self) -> None:
        """Listen for messages on subscribed channels."""
        try:
            async for message in self._pubsub.listen():
                if not self._running:
                    break

                if message["type"] == "message":
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()

                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()

                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError:
                        payload = {"raw": data}

                    callback = self._subscriptions.get(channel)
                    if callback:
                        try:
                            await callback(payload)
                        except Exception as e:
                            logger.error(f"Error in callback for {channel}: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in message listener: {e}")

    async def _local_publish(self, channel: str, message: Dict[str, Any]) -> bool:
        """Fallback: publish locally when Redis not available."""
        callback = self._subscriptions.get(channel)
        if callback:
            try:
                await callback(message)
                return True
            except Exception as e:
                logger.error(f"Error in local callback for {channel}: {e}")
                return False
        return True


# Singleton instance
message_queue = MessageQueue()


# Channel constants for agent communication
class Channels:
    """Standard channel names for agent communication."""
    MARKET_DATA = "agent:market_data"
    TRADE_SIGNALS = "agent:trade_signals"
    RISK_ALERTS = "agent:risk_alerts"
    SENTIMENT = "agent:sentiment"
    AI_DECISIONS = "agent:ai_decisions"
    SYSTEM_EVENTS = "agent:system_events"
    ORCHESTRATOR = "agent:orchestrator"
