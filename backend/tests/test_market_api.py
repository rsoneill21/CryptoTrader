from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from api import market as market_module
from services.kraken import KrakenAPIError, OHLC, Ticker


def make_ticker(symbol: str = "BTC/USD") -> Ticker:
    return Ticker(
        symbol=symbol,
        ask=Decimal("50000"),
        bid=Decimal("49950"),
        last=Decimal("49980"),
        volume_24h=Decimal("123.45"),
        vwap_24h=Decimal("49800"),
        high_24h=Decimal("50500"),
        low_24h=Decimal("49000"),
        open_24h=Decimal("49500"),
        trades_24h=1000,
        timestamp=datetime.now(timezone.utc),
    )


def make_ohlc() -> OHLC:
    return OHLC(
        timestamp=datetime.now(timezone.utc),
        open=Decimal("50000"),
        high=Decimal("50500"),
        low=Decimal("49500"),
        close=Decimal("50200"),
        volume=Decimal("42.0"),
        vwap=Decimal("50100"),
        trades=120,
    )


@pytest.mark.asyncio
async def test_get_ticker_success(monkeypatch):
    async def fake_get_ticker(symbol: str):
        return make_ticker(symbol)

    monkeypatch.setattr(market_module.kraken_service, "get_ticker", fake_get_ticker)
    response = await market_module.get_ticker("BTC/USD")
    assert response.symbol == "BTC/USD"
    assert response.ask == Decimal("50000")


@pytest.mark.asyncio
async def test_get_ohlc_success(monkeypatch):
    async def fake_get_ohlc(symbol: str, interval: str, since):
        return [make_ohlc()], 999999

    monkeypatch.setattr(market_module.kraken_service, "get_ohlc", fake_get_ohlc)
    response = await market_module.get_ohlc("BTC/USD", interval="1h", limit=1)
    assert response.pair == "BTC/USD"
    assert response.interval == "1h"
    assert response.last == 999999
    assert len(response.candles) == 1


@pytest.mark.asyncio
async def test_list_pairs_success(monkeypatch):
    async def fake_get_pairs():
        return {
            "BTC/USD": {
                "kraken_name": "XXBTZUSD",
                "base": "XXBT",
                "quote": "ZUSD",
                "lot_decimals": 8,
                "pair_decimals": 5,
                "ordermin": "0.0001",
            }
        }

    monkeypatch.setattr(market_module.kraken_service, "get_asset_pairs", fake_get_pairs)
    response = await market_module.list_pairs()
    assert response.pairs[0].symbol == "BTC/USD"


@pytest.mark.asyncio
async def test_get_ticker_kraken_error(monkeypatch):
    async def fake_get_ticker(symbol: str):
        raise KrakenAPIError("limit exceeded")

    monkeypatch.setattr(market_module.kraken_service, "get_ticker", fake_get_ticker)
    with pytest.raises(HTTPException) as exc:
        await market_module.get_ticker("BTC/USD")

    assert exc.value.status_code == 502
    assert "limit exceeded" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_ticker_invalid_pair():
    with pytest.raises(HTTPException) as exc:
        await market_module.get_ticker("not-a-pair")

    assert exc.value.status_code == 400
    assert "BASE/QUOTE" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_market_prices_invalid_symbol():
    with pytest.raises(HTTPException) as exc:
        await market_module.get_market_prices(symbols=["BTC/USD", "invalid"])

    assert exc.value.status_code == 400
    assert "BASE/QUOTE" in str(exc.value.detail)
