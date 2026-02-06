import pytest

from agents.trade_executor import TradeExecutorAgent, TradeSignal
from core.exceptions import RiskException
from services.kraken import OrderSide, OrderType


class _DummySessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_signal(signal_id: str = "sig-1") -> TradeSignal:
    return TradeSignal(
        signal_id=signal_id,
        symbol="BTC/USD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
        price=50_000,
    )


@pytest.mark.asyncio
async def test_handle_signal_blocks_order_when_risk_validation_fails(monkeypatch):
    agent = TradeExecutorAgent()
    signal = _build_signal("sig-risk-fail")
    placed = {"called": False}

    async def fake_validate_trade(**kwargs):
        raise RiskException("Liquidity slippage exceeds threshold")

    async def fake_place_order_with_retries(*args, **kwargs):
        placed["called"] = True
        return ["OID-1"]

    monkeypatch.setattr("agents.trade_executor.AsyncSessionLocal", lambda: _DummySessionContext())
    monkeypatch.setattr("agents.trade_executor.RiskService.validate_trade", fake_validate_trade)
    monkeypatch.setattr(agent, "_place_order_with_retries", fake_place_order_with_retries)
    monkeypatch.setattr(agent, "_log_system_event", lambda *args, **kwargs: None)

    await agent._handle_signal(signal)

    assert placed["called"] is False
    assert signal.signal_id not in agent._pending_orders


@pytest.mark.asyncio
async def test_handle_signal_validates_risk_before_order_placement(monkeypatch):
    agent = TradeExecutorAgent()
    signal = _build_signal("sig-risk-pass")
    events = []

    async def fake_validate_trade(**kwargs):
        events.append("validate")

    async def fake_place_order_with_retries(*args, **kwargs):
        events.append("place")
        return ["OID-1"]

    monkeypatch.setattr("agents.trade_executor.AsyncSessionLocal", lambda: _DummySessionContext())
    monkeypatch.setattr("agents.trade_executor.RiskService.validate_trade", fake_validate_trade)
    monkeypatch.setattr(agent, "_place_order_with_retries", fake_place_order_with_retries)
    monkeypatch.setattr(agent, "_log_system_event", lambda *args, **kwargs: None)

    await agent._handle_signal(signal)

    assert events == ["validate", "place"]
