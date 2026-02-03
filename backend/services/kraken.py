"""
Kraken API service wrapper for cryptocurrency trading.

Provides async interface for:
- Market data (ticker, OHLC, orderbook)
- Account data (balance)
- Trading (place/cancel orders, order status)
"""

import asyncio
import logging
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Tuple

import krakenex
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

try:
    from requests.exceptions import RequestException as _RequestException
except ImportError:  # pragma: no cover - best effort when requests missing
    _RequestException = ConnectionError

_CONNECTION_ERRORS = (
    _RequestException,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


class OrderType(str, Enum):
    """Kraken order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop-loss"
    TAKE_PROFIT = "take-profit"
    STOP_LOSS_LIMIT = "stop-loss-limit"
    TAKE_PROFIT_LIMIT = "take-profit-limit"


class OrderSide(str, Enum):
    """Order side (buy/sell)."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELED = "canceled"
    EXPIRED = "expired"


class Ticker(BaseModel):
    """Ticker data."""
    symbol: str
    ask: Decimal
    bid: Decimal
    last: Decimal
    volume_24h: Decimal
    vwap_24h: Decimal
    high_24h: Decimal
    low_24h: Decimal
    open_24h: Decimal
    trades_24h: int
    timestamp: datetime

    model_config = ConfigDict(arbitrary_types_allowed=True)


class OHLC(BaseModel):
    """OHLC candle data."""
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    vwap: Decimal
    trades: int

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Balance(BaseModel):
    """Account balance for an asset."""
    asset: str
    total: Decimal
    available: Decimal
    reserved: Decimal

    model_config = ConfigDict(arbitrary_types_allowed=True)


class OrderInfo(BaseModel):
    """Order information."""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: Optional[Decimal]
    volume: Decimal
    filled_volume: Decimal
    status: OrderStatus
    created_at: datetime
    closed_at: Optional[datetime]
    fee: Decimal
    cost: Decimal

    model_config = ConfigDict(arbitrary_types_allowed=True)


class KrakenAPIError(Exception):
    """Custom exception for Kraken API errors."""

    def __init__(self, message: str, errors: List[str] = None):
        self.message = message
        self.errors = errors or []
        super().__init__(self.message)


@dataclass
class _QueuedRequest:
    method: str
    params: Dict[str, Any]
    private: bool
    future: asyncio.Future[Any]


ErrorCallback = Any  # Callable[[str, str, Dict[str, Any]], None]


class KrakenService:
    """
    Async wrapper for Kraken exchange API.

    Provides methods for:
    - get_ticker(): Current price data
    - get_ohlc(): Historical OHLC candles
    - get_balance(): Account balances
    - place_order(): Submit new orders
    - cancel_order(): Cancel open orders
    - get_order_status(): Check order status
    """

    # Standard Kraken trading pair mappings
    PAIR_MAPPINGS = {
        "BTC/USD": "XXBTZUSD",
        "ETH/USD": "XETHZUSD",
        "XRP/USD": "XXRPZUSD",
        "SOL/USD": "SOLUSD",
        "DOGE/USD": "XDGZUSD",
        "ADA/USD": "ADAUSD",
        "DOT/USD": "DOTUSD",
        "MATIC/USD": "MATICUSD",
        "LTC/USD": "XLTCZUSD",
        "LINK/USD": "LINKUSD",
        "BTC/EUR": "XXBTZEUR",
        "ETH/EUR": "XETHZEUR",
    }

    # Reverse mapping for response parsing
    REVERSE_PAIR_MAPPINGS = {v: k for k, v in PAIR_MAPPINGS.items()}

    # OHLC interval mappings (minutes)
    INTERVAL_MAP = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
        "1w": 10080,
        "2w": 21600,
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ):
        """
        Initialize Kraken service.

        Args:
            api_key: Kraken API key (or from KRAKEN_API_KEY env var)
            api_secret: Kraken API secret (or from KRAKEN_API_SECRET env var)
        """
        self._api = krakenex.API()

        # Load credentials
        self._api_key = api_key or os.getenv("KRAKEN_API_KEY")
        self._api_secret = api_secret or os.getenv("KRAKEN_API_SECRET")

        if self._api_key and self._api_secret:
            self._api.key = self._api_key
            self._api.secret = self._api_secret
            self._authenticated = True
            logger.info("Kraken service initialized with API credentials")
        else:
            self._authenticated = False
            logger.warning("Kraken service initialized without API credentials (public endpoints only)")

        # Rate limiting
        self._last_request_time: float = 0
        self._min_request_interval: float = 0.5  # 500ms between requests
        self._request_queue: Deque[_QueuedRequest] = deque()
        self._queue_task: Optional[asyncio.Task[Any]] = None
        self._queue_lock = asyncio.Lock()
        self._queue_delay = 2.0
        self._max_queue_delay = 30.0
        self._connection_healthy = True

        # Error callbacks for alert integration
        self._error_callbacks: List[Any] = []

    def on_error(self, callback: Any) -> None:
        """Register a callback invoked on API errors: callback(severity, title, details)."""
        self._error_callbacks.append(callback)

    def _notify_error(self, severity: str, title: str, details: Dict[str, Any]) -> None:
        """Notify all registered error callbacks."""
        for cb in self._error_callbacks:
            try:
                cb(severity, title, details)
            except Exception as exc:
                logger.warning("Error callback failed: %s", exc)

    @property
    def is_authenticated(self) -> bool:
        """Check if service has API credentials."""
        return self._authenticated

    def _normalize_pair(self, symbol: str) -> str:
        """Convert friendly symbol to Kraken pair format."""
        return self.PAIR_MAPPINGS.get(symbol, symbol)

    def _denormalize_pair(self, kraken_pair: str) -> str:
        """Convert Kraken pair to friendly symbol format."""
        return self.REVERSE_PAIR_MAPPINGS.get(kraken_pair, kraken_pair)

    async def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time

        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)

        self._last_request_time = asyncio.get_event_loop().time()

    async def _request_once(
        self,
        method_name: str,
        data: Dict[str, Any],
        private: bool,
    ) -> Dict[str, Any]:
        """Make a single Kraken API request without recovery handling."""
        await self._rate_limit()
        payload = dict(data or {})

        loop = asyncio.get_event_loop()
        executor = self._api.query_private if private else self._api.query_public

        response = await loop.run_in_executor(
            None,
            lambda: executor(method_name, payload),
        )

        if response.get("error"):
            raise KrakenAPIError(
                f"Kraken API error: {response['error']}",
                response["error"],
            )

        return response.get("result", {})

    async def _execute_with_recovery(
        self,
        method_name: str,
        data: Dict[str, Any],
        private: bool,
    ) -> Dict[str, Any]:
        """Execute the Kraken request and queue it on connection failure."""
        params = dict(data or {})

        try:
            return await self._request_once(method_name, params, private)
        except KrakenAPIError as exc:
            self._notify_error(
                "warning",
                f"Kraken API error: {method_name}",
                {"method": method_name, "errors": exc.errors, "message": exc.message},
            )
            raise
        except _CONNECTION_ERRORS as exc:
            self._notify_error(
                "critical",
                f"Kraken connection failure: {method_name}",
                {"method": method_name, "error": str(exc)},
            )
            return await self._handle_connection_failure(method_name, params, private, exc)
        except Exception as exc:
            logger.error(f"Error querying Kraken API: {exc}")
            self._notify_error(
                "critical",
                f"Kraken unexpected error: {method_name}",
                {"method": method_name, "error": str(exc)},
            )
            raise KrakenAPIError(f"Request failed: {str(exc)}")

    async def _handle_connection_failure(
        self,
        method_name: str,
        data: Dict[str, Any],
        private: bool,
        exc: Exception,
    ) -> Dict[str, Any]:
        """Queue the request and ensure the recovery task is running."""
        logger.warning(
            "Kraken connection unavailable while calling %s (private=%s): %s",
            method_name,
            private,
            exc,
        )
        self._connection_healthy = False
        return await self._enqueue_request(method_name, data, private)

    async def _enqueue_request(
        self,
        method_name: str,
        data: Dict[str, Any],
        private: bool,
    ) -> Dict[str, Any]:
        """Add the request to the queue and wait for it to be processed."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        queued = _QueuedRequest(
            method=method_name,
            params=dict(data),
            private=private,
            future=future,
        )

        async with self._queue_lock:
            self._request_queue.append(queued)

        self._start_queue_processor()
        return await future

    def _start_queue_processor(self) -> None:
        """Ensure the queue processor task is running."""
        if self._queue_task and not self._queue_task.done():
            return

        self._queue_task = asyncio.create_task(self._drain_queue())

    async def _drain_queue(self) -> None:
        """Process queued requests when the connection is restored."""
        delay = self._queue_delay

        while True:
            async with self._queue_lock:
                if not self._request_queue:
                    break
                queued = self._request_queue[0]

            try:
                result = await self._request_once(queued.method, queued.params, queued.private)
            except _CONNECTION_ERRORS as exc:
                logger.warning(
                    "Still unable to reach Kraken while draining queue (method=%s): %s",
                    queued.method,
                    exc,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._max_queue_delay)
                continue
            except KrakenAPIError as exc:
                queued.future.set_exception(exc)
            except Exception as exc:
                logger.error("Error flushing queued Kraken request: %s", exc)
                queued.future.set_exception(KrakenAPIError(f"Request failed during recovery: {exc}"))
            else:
                queued.future.set_result(result)

            async with self._queue_lock:
                if self._request_queue and self._request_queue[0] is queued:
                    self._request_queue.popleft()

            delay = self._queue_delay

        self._connection_healthy = True

    async def _query_public(self, method: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Query public Kraken API endpoint.

        Args:
            method: API method name
            data: Request parameters

        Returns:
            API response data

        Raises:
            KrakenAPIError: If API returns an error
        """
        params: Dict[str, Any] = data or {}
        return await self._execute_with_recovery(method, params, private=False)

    async def _query_private(self, method: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Query private (authenticated) Kraken API endpoint.

        Args:
            method: API method name
            data: Request parameters

        Returns:
            API response data

        Raises:
            KrakenAPIError: If API returns an error or not authenticated
        """
        if not self._authenticated:
            raise KrakenAPIError("API credentials required for private endpoints")

        params: Dict[str, Any] = data or {}
        return await self._execute_with_recovery(method, params, private=True)

    async def get_ticker(self, symbol: str) -> Ticker:
        """
        Get current ticker data for a trading pair.

        Args:
            symbol: Trading pair (e.g., "BTC/USD")

        Returns:
            Ticker data with current prices and volume
        """
        pair = self._normalize_pair(symbol)

        result = await self._query_public("Ticker", {"pair": pair})

        # Find the pair data in response (Kraken uses different key formats)
        pair_data = None
        for key, value in result.items():
            pair_data = value
            break

        if not pair_data:
            raise KrakenAPIError(f"No ticker data found for {symbol}")

        return Ticker(
            symbol=symbol,
            ask=Decimal(pair_data["a"][0]),  # Ask price
            bid=Decimal(pair_data["b"][0]),  # Bid price
            last=Decimal(pair_data["c"][0]),  # Last trade price
            volume_24h=Decimal(pair_data["v"][1]),  # 24h volume
            vwap_24h=Decimal(pair_data["p"][1]),  # 24h VWAP
            high_24h=Decimal(pair_data["h"][1]),  # 24h high
            low_24h=Decimal(pair_data["l"][1]),  # 24h low
            open_24h=Decimal(pair_data["o"]),  # 24h open
            trades_24h=int(pair_data["t"][1]),  # 24h trade count
            timestamp=datetime.now(timezone.utc),
        )

    async def get_ohlc(
        self,
        symbol: str,
        interval: str = "1h",
        since: Optional[int] = None,
    ) -> Tuple[List[OHLC], int]:
        """
        Get OHLC (candlestick) data for a trading pair.

        Args:
            symbol: Trading pair (e.g., "BTC/USD")
            interval: Timeframe ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "2w")
            since: Unix timestamp to get data from (optional)

        Returns:
            Tuple of (list of OHLC candles, last timestamp for pagination)
        """
        pair = self._normalize_pair(symbol)
        interval_minutes = self.INTERVAL_MAP.get(interval, 60)

        params = {"pair": pair, "interval": interval_minutes}
        if since:
            params["since"] = since

        result = await self._query_public("OHLC", params)

        # Find the pair data in response
        candles = []
        last_timestamp = 0

        for key, value in result.items():
            if key == "last":
                last_timestamp = value
                continue

            for item in value:
                candles.append(OHLC(
                    timestamp=datetime.fromtimestamp(item[0], timezone.utc),
                    open=Decimal(str(item[1])),
                    high=Decimal(str(item[2])),
                    low=Decimal(str(item[3])),
                    close=Decimal(str(item[4])),
                    vwap=Decimal(str(item[5])),
                    volume=Decimal(str(item[6])),
                    trades=int(item[7]),
                ))

        return candles, last_timestamp

    async def get_orderbook(
        self,
        symbol: str,
        count: int = 25,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get order book for a trading pair.

        Args:
            symbol: Trading pair (e.g., "BTC/USD")
            count: Number of bids/asks to return (default 25, max 500)

        Returns:
            Dict with "asks" and "bids" lists
        """
        pair = self._normalize_pair(symbol)

        result = await self._query_public("Depth", {"pair": pair, "count": count})

        # Find the pair data in response
        orderbook = {"asks": [], "bids": []}

        for key, value in result.items():
            for ask in value.get("asks", []):
                orderbook["asks"].append({
                    "price": Decimal(str(ask[0])),
                    "volume": Decimal(str(ask[1])),
                    "timestamp": ask[2],
                })

            for bid in value.get("bids", []):
                orderbook["bids"].append({
                    "price": Decimal(str(bid[0])),
                    "volume": Decimal(str(bid[1])),
                    "timestamp": bid[2],
                })

        return orderbook

    async def get_balance(self) -> Dict[str, Balance]:
        """
        Get account balances for all assets.

        Returns:
            Dict mapping asset symbols to Balance objects

        Note:
            Requires API authentication.
        """
        result = await self._query_private("Balance")

        balances = {}
        for asset, amount in result.items():
            # Normalize asset name (remove X/Z prefixes)
            normalized = asset
            if len(asset) > 3 and asset[0] in ("X", "Z"):
                normalized = asset[1:]

            balances[normalized] = Balance(
                asset=normalized,
                total=Decimal(str(amount)),
                available=Decimal(str(amount)),  # Need TradeBalance for reserved
                reserved=Decimal("0"),
            )

        # Get extended balance info for reserved amounts
        try:
            trade_balance = await self._query_private("TradeBalance")
            # This gives us margin/trade balance info
        except KrakenAPIError:
            pass  # Non-fatal, reserved stays at 0

        return balances

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        volume: Decimal,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        leverage: Optional[str] = None,
        reduce_only: bool = False,
        time_in_force: str = "GTC",
        client_order_id: Optional[str] = None,
        validate_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Place a new order.

        Args:
            symbol: Trading pair (e.g., "BTC/USD")
            side: Buy or sell
            order_type: Order type (market, limit, etc.)
            volume: Order volume
            price: Limit price (required for limit orders)
            stop_price: Stop/trigger price (for stop orders)
            leverage: Leverage amount (e.g., "2:1")
            reduce_only: Only reduce existing position
            time_in_force: GTC, IOC, or GTD
            client_order_id: Custom order ID for tracking
            validate_only: Validate order without submitting

        Returns:
            Order result with order ID(s) and description

        Note:
            Requires API authentication.
        """
        pair = self._normalize_pair(symbol)

        params = {
            "pair": pair,
            "type": side.value,
            "ordertype": order_type.value,
            "volume": str(volume),
        }

        if price is not None:
            params["price"] = str(price)

        if stop_price is not None:
            params["price2"] = str(stop_price)

        if leverage:
            params["leverage"] = leverage

        if reduce_only:
            params["reduce_only"] = True

        if time_in_force != "GTC":
            params["timeinforce"] = time_in_force

        if client_order_id:
            params["userref"] = client_order_id

        if validate_only:
            params["validate"] = True

        result = await self._query_private("AddOrder", params)

        logger.info(f"Order placed: {side.value} {volume} {symbol} @ {price or 'market'}")

        return {
            "order_ids": result.get("txid", []),
            "description": result.get("descr", {}),
        }

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an open order.

        Args:
            order_id: Kraken order ID (txid)

        Returns:
            Cancellation result with count and pending status

        Note:
            Requires API authentication.
        """
        result = await self._query_private("CancelOrder", {"txid": order_id})

        logger.info(f"Order cancelled: {order_id}")

        return {
            "count": result.get("count", 0),
            "pending": result.get("pending", False),
        }

    async def cancel_all_orders(self) -> Dict[str, Any]:
        """
        Cancel all open orders.

        Returns:
            Cancellation result with count

        Note:
            Requires API authentication.
        """
        result = await self._query_private("CancelAll")

        logger.info(f"All orders cancelled: {result.get('count', 0)} orders")

        return {
            "count": result.get("count", 0),
        }

    async def get_order_status(self, order_id: str) -> OrderInfo:
        """
        Get status of a specific order.

        Args:
            order_id: Kraken order ID (txid)

        Returns:
            OrderInfo with full order details

        Note:
            Requires API authentication.
        """
        result = await self._query_private("QueryOrders", {"txid": order_id})

        if not result or order_id not in result:
            raise KrakenAPIError(f"Order not found: {order_id}")

        order = result[order_id]
        descr = order.get("descr", {})

        # Map Kraken status to our status enum
        status_map = {
            "pending": OrderStatus.PENDING,
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.CLOSED,
            "canceled": OrderStatus.CANCELED,
            "expired": OrderStatus.EXPIRED,
        }

        return OrderInfo(
            order_id=order_id,
            symbol=self._denormalize_pair(descr.get("pair", "")),
            side=OrderSide(descr.get("type", "buy")),
            order_type=OrderType(descr.get("ordertype", "market")),
            price=Decimal(str(descr.get("price", 0))) if descr.get("price") else None,
            volume=Decimal(str(order.get("vol", 0))),
            filled_volume=Decimal(str(order.get("vol_exec", 0))),
            status=status_map.get(order.get("status", ""), OrderStatus.PENDING),
            created_at=datetime.fromtimestamp(order.get("opentm", 0), timezone.utc),
            closed_at=datetime.fromtimestamp(order.get("closetm"), timezone.utc) if order.get("closetm") else None,
            fee=Decimal(str(order.get("fee", 0))),
            cost=Decimal(str(order.get("cost", 0))),
        )

    async def get_open_orders(self) -> List[OrderInfo]:
        """
        Get all open orders.

        Returns:
            List of OrderInfo for all open orders

        Note:
            Requires API authentication.
        """
        result = await self._query_private("OpenOrders")

        orders = []
        open_orders = result.get("open", {})

        for order_id, order in open_orders.items():
            descr = order.get("descr", {})

            orders.append(OrderInfo(
                order_id=order_id,
                symbol=self._denormalize_pair(descr.get("pair", "")),
                side=OrderSide(descr.get("type", "buy")),
                order_type=OrderType(descr.get("ordertype", "market")),
                price=Decimal(str(descr.get("price", 0))) if descr.get("price") else None,
                volume=Decimal(str(order.get("vol", 0))),
                filled_volume=Decimal(str(order.get("vol_exec", 0))),
                status=OrderStatus.OPEN,
                created_at=datetime.fromtimestamp(order.get("opentm", 0), timezone.utc),
                closed_at=None,
                fee=Decimal(str(order.get("fee", 0))),
                cost=Decimal(str(order.get("cost", 0))),
            ))

        return orders

    async def get_trade_history(
        self,
        start: Optional[int] = None,
        end: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Get trade history.

        Args:
            start: Start timestamp (optional)
            end: End timestamp (optional)
            offset: Result offset for pagination

        Returns:
            List of trade records

        Note:
            Requires API authentication.
        """
        params = {"ofs": offset}

        if start:
            params["start"] = start
        if end:
            params["end"] = end

        result = await self._query_private("TradesHistory", params)

        trades = []
        for trade_id, trade in result.get("trades", {}).items():
            trades.append({
                "trade_id": trade_id,
                "order_id": trade.get("ordertxid"),
                "symbol": self._denormalize_pair(trade.get("pair", "")),
                "side": trade.get("type"),
                "price": Decimal(str(trade.get("price", 0))),
                "volume": Decimal(str(trade.get("vol", 0))),
                "cost": Decimal(str(trade.get("cost", 0))),
                "fee": Decimal(str(trade.get("fee", 0))),
                "timestamp": datetime.fromtimestamp(trade.get("time", 0), timezone.utc),
            })

        return trades

    async def get_server_time(self) -> datetime:
        """
        Get Kraken server time.

        Returns:
            Server timestamp as datetime
        """
        result = await self._query_public("Time")
        return datetime.fromtimestamp(result.get("unixtime", 0), timezone.utc)

    async def get_asset_pairs(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all available trading pairs.

        Returns:
            Dict mapping pair names to pair info
        """
        result = await self._query_public("AssetPairs")

        pairs = {}
        for pair_name, pair_info in result.items():
            friendly_name = self._denormalize_pair(pair_name)
            pairs[friendly_name] = {
                "kraken_name": pair_name,
                "base": pair_info.get("base"),
                "quote": pair_info.get("quote"),
                "lot_decimals": pair_info.get("lot_decimals"),
                "pair_decimals": pair_info.get("pair_decimals"),
                "ordermin": pair_info.get("ordermin"),
            }

        return pairs


# Singleton instance
kraken_service = KrakenService()
