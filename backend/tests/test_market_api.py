from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from api import market as market_module
from agents.sentiment_agent import SentimentSummary
from core.exceptions import ServiceUnavailableException
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


@pytest.mark.asyncio
async def test_get_market_analysis_success(monkeypatch):
    now = datetime.now(timezone.utc)
    technical_payload = {
        "data_points": 4,
        "direction": "rising",
        "last_price": Decimal("100"),
        "previous_price": Decimal("98"),
        "average": Decimal("99"),
        "high": Decimal("101"),
        "low": Decimal("97"),
        "momentum": Decimal("0.02"),
        "volatility": Decimal("0.04"),
        "price_range": Decimal("4"),
        "range_pct": Decimal("0.04"),
        "last_updated": now,
    }

    async def fake_summarize(symbol: str, lookback: int, reference=None):
        return technical_payload

    async def fake_indicator(symbol: str):
        return {
            "short_sma": Decimal("99"),
            "long_sma": Decimal("95"),
            "momentum": Decimal("0.02"),
            "volatility": Decimal("0.04"),
            "price_count": 20,
            "last_price": Decimal("100"),
            "last_timestamp": now,
        }

    async def fake_insights(symbol: str, limit: int):
        return [{"summary": "Short SMA crossed above long SMA"}]

    async def fake_sentiment(symbol: str, limit: int):
        return SentimentSummary(
            symbol=symbol,
            average_score=0.3,
            positive_mentions=2,
            negative_mentions=0,
            neutral_mentions=0,
            data_points=2,
            latest_summary="Bullish chatter",
            last_updated=now,
            sources={"twitter": 2},
        )

    monkeypatch.setattr(market_module.market_data_service, "summarize_symbol", fake_summarize)
    monkeypatch.setattr(market_module.market_analyst_agent, "get_indicator_summary", fake_indicator)
    monkeypatch.setattr(market_module.market_analyst_agent, "get_recent_insights", fake_insights)
    monkeypatch.setattr(market_module.sentiment_agent, "summarize_symbol", fake_sentiment)

    response = await market_module.get_market_analysis("btc/usd")
    assert response.symbol == "BTC/USD"
    assert response.technical.data_points == 4
    assert response.technical.last_price == Decimal("100")
    assert response.analyst_indicators.price_count == 20
    assert response.sentiment is not None
    assert response.sentiment.average_score == 0.3
    assert any("Insight" in rec for rec in response.recommendations)


@pytest.mark.asyncio
async def test_get_market_analysis_invalid_symbol():
    with pytest.raises(HTTPException) as exc:
        await market_module.get_market_analysis("not-a-pair")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dependency",
    ["indicator_summary", "insights", "sentiment"],
)
async def test_get_market_analysis_dependency_failure_raises_service_unavailable(
    dependency,
    monkeypatch,
):
    now = datetime.now(timezone.utc)

    async def fake_summarize(symbol: str, lookback: int, reference=None):
        return {
            "data_points": 4,
            "direction": "flat",
            "last_price": Decimal("100"),
            "previous_price": Decimal("99"),
            "average": Decimal("99"),
            "high": Decimal("101"),
            "low": Decimal("97"),
            "momentum": Decimal("0.01"),
            "volatility": Decimal("0.02"),
            "price_range": Decimal("4"),
            "range_pct": Decimal("0.04"),
            "last_updated": now,
        }

    async def fake_indicator(symbol: str):
        return {
            "short_sma": Decimal("99"),
            "long_sma": Decimal("95"),
            "momentum": Decimal("0.02"),
            "volatility": Decimal("0.04"),
            "price_count": 20,
            "last_price": Decimal("100"),
            "last_timestamp": now,
        }

    async def fake_insights(symbol: str, limit: int):
        return [{"summary": "Momentum waning"}]

    async def fake_sentiment(symbol: str, limit: int):
        return SentimentSummary(
            symbol=symbol,
            average_score=0.1,
            positive_mentions=1,
            negative_mentions=0,
            neutral_mentions=0,
            data_points=1,
            latest_summary="Neutral",
            last_updated=now,
            sources={"twitter": 1},
        )

    monkeypatch.setattr(market_module.market_data_service, "summarize_symbol", fake_summarize)
    monkeypatch.setattr(market_module.market_analyst_agent, "get_indicator_summary", fake_indicator)
    monkeypatch.setattr(market_module.market_analyst_agent, "get_recent_insights", fake_insights)
    monkeypatch.setattr(market_module.sentiment_agent, "summarize_symbol", fake_sentiment)

    async def boom(*_, **__):
        raise RuntimeError("boom")

    if dependency == "indicator_summary":
        monkeypatch.setattr(market_module.market_analyst_agent, "get_indicator_summary", boom)
    elif dependency == "insights":
        monkeypatch.setattr(market_module.market_analyst_agent, "get_recent_insights", boom)
    else:
        monkeypatch.setattr(market_module.sentiment_agent, "summarize_symbol", boom)

    with pytest.raises(ServiceUnavailableException) as exc:
        await market_module.get_market_analysis("btc/usd")

    payload = exc.value.detail.get("details", {})
    assert payload.get("dependency") == dependency
