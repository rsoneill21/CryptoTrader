"""
Kraken WebSocket service for real-time price data.

Connects to Kraken WebSocket API and broadcasts price updates
to connected clients via FastAPI WebSocket endpoints.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from enum import Enum

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from services.kraken import KrakenService

logger = logging.getLogger(__name__)


class KrakenWSFeed(str, Enum):
    """Kraken WebSocket feed types."""
    TICKER = "ticker"
    OHLC = "ohlc"
    TRADE = "trade"
    SPREAD = "spread"
    BOOK = "book"


@dataclass
class TickerUpdate:
    """Real-time ticker update."""
    symbol: str
    ask: Decimal
    bid: Decimal
    last: Decimal
    volume: Decimal
    vwap: Decimal
    high: Decimal
    low: Decimal
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "symbol": self.symbol,
            "ask": str(self.ask),
            "bid": str(self.bid),
            "last": str(self.last),
            "volume": str(self.volume),
            "vwap": str(self.vwap),
            "high": str(self.high),
            "low": str(self.low),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class TradeUpdate:
    """Real-time trade update."""
    symbol: str
    price: Decimal
    volume: Decimal
    side: str  # "buy" or "sell"
    order_type: str  # "market" or "limit"
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "symbol": self.symbol,
            "price": str(self.price),
            "volume": str(self.volume),
            "side": self.side,
            "order_type": self.order_type,
            "timestamp": self.timestamp.isoformat(),
        }


class KrakenWebSocket:
    """
    Kraken WebSocket client for real-time market data.

    Features:
    - Auto-reconnection on connection loss
    - Multiple subscription support
    - Callback-based message handling
    - Thread-safe client management
    """

    WS_PUBLIC_URL = "wss://ws.kraken.com"
    WS_PRIVATE_URL = "wss://ws-auth.kraken.com"

    # Kraken pair mappings for WebSocket (different from REST API)
    PAIR_MAPPINGS = {
        "BTC/USD": "XBT/USD",
        "ETH/USD": "ETH/USD",
        "XRP/USD": "XRP/USD",
        "SOL/USD": "SOL/USD",
        "DOGE/USD": "DOGE/USD",
        "ADA/USD": "ADA/USD",
        "DOT/USD": "DOT/USD",
        "MATIC/USD": "MATIC/USD",
        "LTC/USD": "LTC/USD",
        "LINK/USD": "LINK/USD",
        "BTC/EUR": "XBT/EUR",
        "ETH/EUR": "ETH/EUR",
    }

    REVERSE_PAIR_MAPPINGS = {v: k for k, v in PAIR_MAPPINGS.items()}

    def __init__(self):
        """Initialize WebSocket client."""
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._connected = False
        self._reconnecting = False
        self._task: Optional[asyncio.Task] = None

        # Subscriptions
        self._subscriptions: Dict[str, Set[str]] = {}  # feed -> set of pairs
        self._callbacks: Dict[str, List[Callable]] = {}  # feed -> list of callbacks

        # Client connections (for broadcasting)
        self._clients: Set[Any] = set()
        self._client_feeds: Dict[Any, Set[str]] = {}

        # Heartbeat
        self._last_heartbeat: datetime = datetime.now(timezone.utc)
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Reconnection settings
        self._max_reconnect_attempts = 10
        self._reconnect_delay = 1.0
        self._reconnect_delay_max = 60.0

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._connected and self._ws is not None

    def _normalize_pair(self, symbol: str) -> str:
        """Convert friendly symbol to Kraken WS pair format."""
        return self.PAIR_MAPPINGS.get(symbol, symbol)

    def _denormalize_pair(self, kraken_pair: str) -> str:
        """Convert Kraken WS pair to friendly symbol format."""
        return self.REVERSE_PAIR_MAPPINGS.get(kraken_pair, kraken_pair)

    async def connect(self) -> bool:
        """
        Connect to Kraken WebSocket.

        Returns:
            True if connected successfully
        """
        if self._connected:
            return True

        try:
            logger.info("Connecting to Kraken WebSocket...")
            self._ws = await websockets.connect(
                self.WS_PUBLIC_URL,
                ping_interval=20,
                ping_timeout=10,
            )
            self._connected = True
            self._running = True

            # Start message handler
            self._task = asyncio.create_task(self._message_loop())

            # Start heartbeat checker
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            logger.info("Connected to Kraken WebSocket")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Kraken WebSocket: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from Kraken WebSocket."""
        self._running = False
        self._connected = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self._ws.close()
            self._ws = None

        logger.info("Disconnected from Kraken WebSocket")

    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        if self._reconnecting:
            return

        self._reconnecting = True
        self._connected = False
        delay = self._reconnect_delay

        for attempt in range(1, self._max_reconnect_attempts + 1):
            logger.info(f"Reconnection attempt {attempt}/{self._max_reconnect_attempts}")

            if await self.connect():
                # Resubscribe to all feeds
                await self._resubscribe()
                self._reconnecting = False
                return

            await asyncio.sleep(delay)
            delay = min(delay * 2, self._reconnect_delay_max)

        logger.error("Max reconnection attempts reached")
        self._reconnecting = False

    async def _resubscribe(self) -> None:
        """Resubscribe to all feeds after reconnection."""
        for feed, pairs in self._subscriptions.items():
            if pairs:
                await self._send_subscribe(feed, list(pairs))

    async def _message_loop(self) -> None:
        """Main loop for receiving WebSocket messages."""
        while self._running:
            try:
                if not self._ws:
                    await asyncio.sleep(0.1)
                    continue

                message = await self._ws.recv()
                await self._handle_message(message)

            except ConnectionClosedError as e:
                logger.warning(f"WebSocket connection closed: {e}")
                if self._running:
                    await self._reconnect()

            except ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
                if self._running:
                    await self._reconnect()

            except asyncio.CancelledError:
                break

            except Exception as e:
                logger.error(f"Error in WebSocket message loop: {e}")
                await asyncio.sleep(1)

    async def _heartbeat_loop(self) -> None:
        """Monitor heartbeat and reconnect if needed."""
        while self._running:
            try:
                await asyncio.sleep(30)

                # Check if we've received a heartbeat recently
                elapsed = (datetime.now(timezone.utc) - self._last_heartbeat).total_seconds()
                if elapsed > 60 and self._connected:
                    logger.warning(f"No heartbeat for {elapsed}s, reconnecting...")
                    await self._reconnect()

            except asyncio.CancelledError:
                break

            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")

    async def _handle_message(self, message: str) -> None:
        """
        Handle incoming WebSocket message.

        Args:
            message: Raw message string
        """
        try:
            data = json.loads(message)

            # Handle different message types
            if isinstance(data, dict):
                event = data.get("event")

                if event == "heartbeat":
                    self._last_heartbeat = datetime.now(timezone.utc)
                    return

                if event == "systemStatus":
                    logger.info(f"Kraken system status: {data.get('status')}")
                    return

                if event == "subscriptionStatus":
                    status = data.get("status")
                    pair = data.get("pair")
                    feed = data.get("subscription", {}).get("name")
                    logger.info(f"Subscription {status}: {feed} {pair}")
                    return

                if event == "error":
                    logger.error(f"Kraken WS error: {data.get('errorMessage')}")
                    return

            # Handle data messages (arrays)
            if isinstance(data, list) and len(data) >= 4:
                await self._handle_data_message(data)

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON: {message[:100]}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def _handle_data_message(self, data: List[Any]) -> None:
        """
        Handle data message from Kraken.

        Args:
            data: Parsed message array [channel_id, data, channel_name, pair]
        """
        # Format: [channelID, data, channelName, pair]
        if len(data) < 4:
            return

        channel_name = data[-2]
        pair = data[-1]
        payload = data[1]

        symbol = self._denormalize_pair(pair)

        if channel_name == "ticker":
            await self._handle_ticker(symbol, payload)
        elif channel_name == "trade":
            await self._handle_trade(symbol, payload)
        elif channel_name.startswith("ohlc"):
            await self._handle_ohlc(symbol, payload)

    async def _handle_ticker(self, symbol: str, data: Dict[str, Any]) -> None:
        """Handle ticker update."""
        try:
            update = TickerUpdate(
                symbol=symbol,
                ask=Decimal(str(data["a"][0])),
                bid=Decimal(str(data["b"][0])),
                last=Decimal(str(data["c"][0])),
                volume=Decimal(str(data["v"][1])),
                vwap=Decimal(str(data["p"][1])),
                high=Decimal(str(data["h"][1])),
                low=Decimal(str(data["l"][1])),
                timestamp=datetime.now(timezone.utc),
            )

            # Call registered callbacks
            for callback in self._callbacks.get(KrakenWSFeed.TICKER, []):
                try:
                    await callback(update)
                except Exception as e:
                    logger.error(f"Error in ticker callback: {e}")

            # Broadcast to clients
            await self._broadcast("ticker", update.to_dict())

            # Update paper trading engine with latest price
            from services.paper_trading_service import paper_trading_engine
            asyncio.create_task(paper_trading_engine.update_market_price(symbol, float(update.last)))

        except Exception as e:
            logger.error(f"Error handling ticker: {e}")

    async def _handle_trade(self, symbol: str, data: List[List[Any]]) -> None:
        """Handle trade update."""
        try:
            for trade in data:
                update = TradeUpdate(
                    symbol=symbol,
                    price=Decimal(str(trade[0])),
                    volume=Decimal(str(trade[1])),
                    timestamp=datetime.fromtimestamp(float(trade[2]), timezone.utc),
                    side="buy" if trade[3] == "b" else "sell",
                    order_type="market" if trade[4] == "m" else "limit",
                )

                # Call registered callbacks
                for callback in self._callbacks.get(KrakenWSFeed.TRADE, []):
                    try:
                        await callback(update)
                    except Exception as e:
                        logger.error(f"Error in trade callback: {e}")

                # Broadcast to clients
                await self._broadcast("trade", update.to_dict())

        except Exception as e:
            logger.error(f"Error handling trade: {e}")

    async def _handle_ohlc(self, symbol: str, data: List[Any]) -> None:
        """Handle OHLC update."""
        try:
            ohlc_data = {
                "symbol": symbol,
                "timestamp": datetime.fromtimestamp(float(data[0]), timezone.utc).isoformat(),
                "end_timestamp": datetime.fromtimestamp(float(data[1]), timezone.utc).isoformat(),
                "open": str(data[2]),
                "high": str(data[3]),
                "low": str(data[4]),
                "close": str(data[5]),
                "vwap": str(data[6]),
                "volume": str(data[7]),
                "count": int(data[8]),
            }

            # Call registered callbacks
            for callback in self._callbacks.get(KrakenWSFeed.OHLC, []):
                try:
                    await callback(ohlc_data)
                except Exception as e:
                    logger.error(f"Error in OHLC callback: {e}")

            # Broadcast to clients
            await self._broadcast("ohlc", ohlc_data)

        except Exception as e:
            logger.error(f"Error handling OHLC: {e}")

    async def _send_subscribe(self, feed: str, pairs: List[str]) -> None:
        """
        Send subscription message.

        Args:
            feed: Feed name (ticker, trade, ohlc, etc.)
            pairs: List of trading pairs
        """
        if not self._ws:
            return

        # Convert to Kraken pair format
        kraken_pairs = [self._normalize_pair(p) for p in pairs]

        message = {
            "event": "subscribe",
            "pair": kraken_pairs,
            "subscription": {"name": feed}
        }

        # Add interval for OHLC
        if feed == "ohlc":
            message["subscription"]["interval"] = 1  # 1 minute

        try:
            await self._ws.send(json.dumps(message))
            logger.info(f"Subscribed to {feed} for {pairs}")
        except Exception as e:
            logger.error(f"Error sending subscribe: {e}")

    async def _send_unsubscribe(self, feed: str, pairs: List[str]) -> None:
        """
        Send unsubscribe message.

        Args:
            feed: Feed name
            pairs: List of trading pairs
        """
        if not self._ws:
            return

        kraken_pairs = [self._normalize_pair(p) for p in pairs]

        message = {
            "event": "unsubscribe",
            "pair": kraken_pairs,
            "subscription": {"name": feed}
        }

        try:
            await self._ws.send(json.dumps(message))
            logger.info(f"Unsubscribed from {feed} for {pairs}")
        except Exception as e:
            logger.error(f"Error sending unsubscribe: {e}")

    async def subscribe_ticker(
        self,
        pairs: List[str],
        callback: Optional[Callable] = None,
    ) -> None:
        """
        Subscribe to ticker updates.

        Args:
            pairs: List of trading pairs (e.g., ["BTC/USD", "ETH/USD"])
            callback: Optional callback for updates
        """
        feed = KrakenWSFeed.TICKER

        # Track subscriptions
        if feed not in self._subscriptions:
            self._subscriptions[feed] = set()
        self._subscriptions[feed].update(pairs)

        # Track callbacks
        if callback:
            if feed not in self._callbacks:
                self._callbacks[feed] = []
            self._callbacks[feed].append(callback)

        # Subscribe if connected
        if self.is_connected:
            await self._send_subscribe(feed, pairs)

    async def subscribe_trades(
        self,
        pairs: List[str],
        callback: Optional[Callable] = None,
    ) -> None:
        """
        Subscribe to trade updates.

        Args:
            pairs: List of trading pairs
            callback: Optional callback for updates
        """
        feed = KrakenWSFeed.TRADE

        if feed not in self._subscriptions:
            self._subscriptions[feed] = set()
        self._subscriptions[feed].update(pairs)

        if callback:
            if feed not in self._callbacks:
                self._callbacks[feed] = []
            self._callbacks[feed].append(callback)

        if self.is_connected:
            await self._send_subscribe(feed, pairs)

    async def subscribe_ohlc(
        self,
        pairs: List[str],
        callback: Optional[Callable] = None,
    ) -> None:
        """
        Subscribe to OHLC (candlestick) updates.

        Args:
            pairs: List of trading pairs
            callback: Optional callback for updates
        """
        feed = KrakenWSFeed.OHLC

        if feed not in self._subscriptions:
            self._subscriptions[feed] = set()
        self._subscriptions[feed].update(pairs)

        if callback:
            if feed not in self._callbacks:
                self._callbacks[feed] = []
            self._callbacks[feed].append(callback)

        if self.is_connected:
            await self._send_subscribe("ohlc", pairs)

    async def unsubscribe(self, feed: KrakenWSFeed, pairs: List[str]) -> None:
        """
        Unsubscribe from a feed.

        Args:
            feed: Feed to unsubscribe from
            pairs: List of trading pairs
        """
        if feed in self._subscriptions:
            self._subscriptions[feed] -= set(pairs)

        if self.is_connected:
            await self._send_unsubscribe(feed, pairs)

    # Client management for broadcasting

    def add_client(self, client: Any, feeds: Optional[Set[str]] = None) -> None:
        """
        Add a client connection for broadcasting.

        Args:
            client: WebSocket client connection
        """
        self._clients.add(client)
        feed_set = set(feeds) if feeds else set()
        self._client_feeds[client] = feed_set
        logger.info(f"Client added. Total clients: {len(self._clients)}")

    def remove_client(self, client: Any) -> None:
        """
        Remove a client connection.

        Args:
            client: WebSocket client connection
        """
        self._clients.discard(client)
        self._client_feeds.pop(client, None)
        logger.info(f"Client removed. Total clients: {len(self._clients)}")

    async def _broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Broadcast message to all connected clients.

        Args:
            event_type: Type of event (ticker, trade, ohlc)
            data: Event data
        """
        if not self._clients:
            return

        message = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        disconnected = set()

        for client in self._clients:
            feeds = self._client_feeds.get(client)
            if feeds and event_type not in feeds:
                continue
            try:
                await client.send_text(message)
            except Exception:
                disconnected.add(client)

        # Clean up disconnected clients
        for client in disconnected:
            self.remove_client(client)


# Singleton instance
kraken_ws = KrakenWebSocket()

DEFAULT_TICKER_PAIRS = sorted(KrakenService.PAIR_MAPPINGS.keys())


async def start_kraken_ws() -> None:
    """Start the Kraken WebSocket service."""
    try:
        # Give it 10 seconds to connect
        await asyncio.wait_for(kraken_ws.connect(), timeout=10.0)
        if DEFAULT_TICKER_PAIRS:
            await kraken_ws.subscribe_ticker(DEFAULT_TICKER_PAIRS)
        logger.info("Kraken WebSocket background service started")
    except asyncio.TimeoutError:
        logger.error("Timeout connecting to Kraken WebSocket. Continuing without real-time data.")
    except Exception as e:
        logger.error(f"Failed to start Kraken WebSocket: {e}")


async def stop_kraken_ws() -> None:
    """Stop the Kraken WebSocket service."""
    await kraken_ws.disconnect()
