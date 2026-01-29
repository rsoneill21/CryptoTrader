import os
import sys
from pathlib import Path
from decimal import Decimal

ROOT_PATH = Path(__file__).resolve().parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

import pytest

from services.kraken import (
    Balance,
    KrakenAPIError,
    KrakenService,
    OrderSide,
    OrderStatus,
    OrderType,
)


@pytest.mark.asyncio
async def test_get_ticker_parses_data(monkeypatch):
    service = KrakenService()

    async def fake_query_public(method, params=None):
        assert method == "Ticker"
        assert params["pair"] == "XXBTZUSD"
        return {
            "XXBTZUSD": {
                "a": ["50000.00", "1", "1"],
                "b": ["49900.00", "1", "1"],
                "c": ["49950.00", "1"],
                "v": ["100.0", "200.0"],
                "p": ["49800.00", "49850.00"],
                "h": ["50500.00", "50500.00"],
                "l": ["49500.00", "49000.00"],
                "o": "49500.00",
                "t": ["150", "300"],
            }
        }

    monkeypatch.setattr(service, "_query_public", fake_query_public)

    ticker = await service.get_ticker("BTC/USD")

    assert ticker.symbol == "BTC/USD"
    assert ticker.ask == Decimal("50000.00")
    assert ticker.bid == Decimal("49900.00")
    assert ticker.last == Decimal("49950.00")
    assert ticker.volume_24h == Decimal("200.0")
    assert ticker.trades_24h == 300


@pytest.mark.asyncio
async def test_get_ohlc_returns_candles(monkeypatch):
    service = KrakenService()

    async def fake_query_public(method, params=None):
        assert method == "OHLC"
        assert params["pair"] == "XXBTZUSD"
        assert params["interval"] == 60
        return {
            "XXBTZUSD": [
                [1700000000, "50000", "50100", "49900", "50050", "50050", "10", 5],
                [1700000060, "50050", "50200", "50000", "50150", "50090", "12", 6],
            ],
            "last": 1700000120,
        }

    monkeypatch.setattr(service, "_query_public", fake_query_public)

    candles, last = await service.get_ohlc("BTC/USD", interval="1h")

    assert last == 1700000120
    assert len(candles) == 2
    assert candles[0].open == Decimal("50000")
    assert candles[1].volume == Decimal("12")


@pytest.mark.asyncio
async def test_get_balance_aggregates_assets(monkeypatch):
    service = KrakenService()

    async def fake_query_private(method, params=None):
        if method == "Balance":
            return {"XXBT": "1.50", "ZUSD": "200.00"}
        if method == "TradeBalance":
            return {"equity": "1.50"}
        raise KrakenAPIError("unexpected")

    monkeypatch.setattr(service, "_query_private", fake_query_private)

    balances = await service.get_balance()

    assert isinstance(balances["XBT"], Balance)
    assert balances["XBT"].total == Decimal("1.50")
    assert balances["USD"].total == Decimal("200.00")


@pytest.mark.asyncio
async def test_place_order_sends_correct_payload(monkeypatch):
    service = KrakenService()
    captured = {}

    async def fake_query_private(method, params=None):
        captured["method"] = method
        captured["params"] = params
        return {"txid": ["TX1"], "descr": {"order": "limit order"}}

    monkeypatch.setattr(service, "_query_private", fake_query_private)

    result = await service.place_order(
        "BTC/USD",
        OrderSide.BUY,
        OrderType.LIMIT,
        Decimal("0.1"),
        price=Decimal("50000"),
        stop_price=Decimal("49900"),
        time_in_force="IOC",
        client_order_id="client-123",
    )

    assert captured["method"] == "AddOrder"
    params = captured["params"]
    assert params["pair"] == "XXBTZUSD"
    assert params["price"] == "50000"
    assert params["price2"] == "49900"
    assert params["timeinforce"] == "IOC"
    assert params["userref"] == "client-123"
    assert result["order_ids"] == ["TX1"]


@pytest.mark.asyncio
async def test_cancel_order_returns_counts(monkeypatch):
    service = KrakenService()

    async def fake_query_private(method, params=None):
        assert method == "CancelOrder"
        assert params["txid"] == "ORDER1"
        return {"count": 1, "pending": False}

    monkeypatch.setattr(service, "_query_private", fake_query_private)

    response = await service.cancel_order("ORDER1")

    assert response["count"] == 1
    assert response["pending"] is False


@pytest.mark.asyncio
async def test_get_order_status_parses_details(monkeypatch):
    service = KrakenService()

    async def fake_query_private(method, params=None):
        assert method == "QueryOrders"
        return {
            "ORDER1": {
                "descr": {"pair": "XXBTZUSD", "type": "sell", "ordertype": "limit", "price": "50500"},
                "vol": "0.2",
                "vol_exec": "0.1",
                "status": "closed",
                "opentm": 1700000000,
                "closetm": 1700000050,
                "fee": "0.01",
                "cost": "5050",
            }
        }

    monkeypatch.setattr(service, "_query_private", fake_query_private)

    order = await service.get_order_status("ORDER1")

    assert order.order_id == "ORDER1"
    assert order.side == OrderSide("sell")
    assert order.status == OrderStatus.CLOSED
    assert order.price == Decimal("50500")
