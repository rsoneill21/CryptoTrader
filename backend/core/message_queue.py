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

    # Redis Streams configuration
    MAX_QUEUE_DEPTH = 100  # Per user decision: drop oldest when backed up
    PRIORITY_LEVELS = 3    # 0=critical, 1=high, 2=normal

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

    async def publish_reliable(self, channel: str, message: dict, priority: int = 2) -> bool:
        """
        Publish message to Redis Stream with priority support.

        Priority levels (per user decision):
        - 0: Critical (halt signals, emergency stops)
        - 1: High (rebalance recommendations, risk alerts)
        - 2: Normal (routine insights, research ideas)

        Args:
            channel: Channel name (e.g., "trade_signals")
            message: Message data as dict
            priority: Priority level (0=critical, 1=high, 2=normal)

        Returns:
            True if published successfully
        """
        if not self._redis:
            logger.warning("Not connected to Redis for stream publish")
            return await self._local_publish(channel, message)

        try:
            # Validate priority
            if priority < 0 or priority >= self.PRIORITY_LEVELS:
                logger.warning(f"Invalid priority {priority}, using 2 (normal)")
                priority = 2

            # Add metadata
            message_with_meta = message.copy()
            message_with_meta["_timestamp"] = datetime.utcnow().isoformat()
            message_with_meta["_channel"] = channel
            message_with_meta["_priority"] = priority

            # Stream key with priority
            stream_key = f"stream:{channel}:p{priority}"

            # Check queue depth before adding
            current_depth = await self._redis.xlen(stream_key)

            # Add to stream
            await self._redis.xadd(stream_key, message_with_meta)

            # Trim if exceeds max depth
            if current_depth >= self.MAX_QUEUE_DEPTH:
                dropped = current_depth - self.MAX_QUEUE_DEPTH + 1
                await self._redis.xtrim(stream_key, maxlen=self.MAX_QUEUE_DEPTH, approximate=False)
                logger.warning(
                    f"Queue {stream_key} exceeded depth limit. "
                    f"Trimmed {dropped} oldest messages for audit."
                )

            return True

        except Exception as e:
            logger.error(f"Error publishing to stream {channel}:p{priority}: {e}", exc_info=True)
            # Fallback to local
            return await self._local_publish(channel, message)

    async def consume_reliable(self, channel: str, group: str, consumer: str, callback: Callable) -> None:
        """
        Consume from Redis Stream with consumer group.

        Provides at-least-once delivery via message acknowledgment.

        Args:
            channel: Channel name (e.g., "trade_signals")
            group: Consumer group name
            consumer: Consumer name within group
            callback: Async function to call for each message
        """
        if not self._redis:
            logger.warning("Not connected to Redis for stream consume")
            return

        try:
            # Create consumer groups for all priority levels if they don't exist
            for priority in range(self.PRIORITY_LEVELS):
                stream_key = f"stream:{channel}:p{priority}"
                try:
                    await self._redis.xgroup_create(stream_key, group, id='0', mkstream=True)
                    logger.info(f"Created consumer group {group} for {stream_key}")
                except Exception as e:
                    # BUSYGROUP error means group already exists
                    if "BUSYGROUP" not in str(e):
                        logger.error(f"Error creating consumer group for {stream_key}: {e}")

            # Consume loop - check all priority streams in order
            while self._running:
                try:
                    # Read from all priority streams (p0 first, then p1, then p2)
                    for priority in range(self.PRIORITY_LEVELS):
                        stream_key = f"stream:{channel}:p{priority}"

                        # Read from stream with consumer group
                        messages = await self._redis.xreadgroup(
                            group,
                            consumer,
                            {stream_key: '>'},  # '>' means new messages
                            count=10,
                            block=1000  # 1 second block
                        )

                        # Process messages
                        for stream, msg_list in messages:
                            for msg_id, msg_data in msg_list:
                                try:
                                    # Decode message
                                    decoded_msg = {
                                        k.decode() if isinstance(k, bytes) else k:
                                        v.decode() if isinstance(v, bytes) else v
                                        for k, v in msg_data.items()
                                    }

                                    # Call callback
                                    await callback(decoded_msg)

                                    # Acknowledge successful processing
                                    await self._redis.xack(stream_key, group, msg_id)

                                except Exception as e:
                                    logger.error(
                                        f"Error processing message {msg_id} from {stream_key}: {e}",
                                        exc_info=True
                                    )
                                    # Message stays unacked for redelivery

                    # Small delay between priority checks
                    await asyncio.sleep(0.1)

                except asyncio.CancelledError:
                    logger.info(f"Consumer {consumer} cancelled for channel {channel}")
                    break
                except Exception as e:
                    logger.error(f"Error in consume loop for {channel}: {e}", exc_info=True)
                    await asyncio.sleep(1)  # Backoff on error

        except Exception as e:
            logger.error(f"Fatal error in consume_reliable for {channel}: {e}", exc_info=True)

    async def stop_consumers(self) -> None:
        """Signal consumers to stop gracefully."""
        self._running = False
        logger.info("Stopping message queue consumers")

    async def get_queue_depth(self, channel: str) -> Dict[str, int]:
        """
        Get queue depths for all priority levels of a channel.

        Args:
            channel: Channel name

        Returns:
            Dict with p0, p1, p2, and total counts
        """
        if not self._redis:
            return {"p0": 0, "p1": 0, "p2": 0, "total": 0}

        try:
            depths = {}
            total = 0

            for priority in range(self.PRIORITY_LEVELS):
                stream_key = f"stream:{channel}:p{priority}"
                depth = await self._redis.xlen(stream_key)
                depths[f"p{priority}"] = depth
                total += depth

            depths["total"] = total
            return depths

        except Exception as e:
            logger.error(f"Error getting queue depth for {channel}: {e}", exc_info=True)
            return {"p0": 0, "p1": 0, "p2": 0, "total": 0}

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
