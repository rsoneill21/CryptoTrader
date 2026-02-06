"""Regression tests for manual trade order entry and close contracts."""

import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_trades_order_entry_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from api import trades as trades_module
from core.exceptions import RiskException
from db.database import AsyncSessionLocal, Base, async_engine
from db.models import Order, Trade, User


def _user() -> User:
    return User(id=1, email="tester@example.com", password_hash="hash")


@pytest_asyncio.fixture
async def db_session():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        yield session

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db_file():
    yield
    for candidate in (
        TEST_DB_PATH,
        TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
        TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
    ):
        if candidate.exists():
            candidate.unlink()


@pytest.mark.asyncio
@pytest.mark.parametrize("side", ["buy", "sell"])
async def test_market_order_submission_passes_risk_gate_and_returns_lifecycle_fields(
    db_session,
    monkeypatch,
    side,
):
    risk_calls = []

    async def fake_validate_trade(**kwargs):
        risk_calls.append(kwargs)

    async def fake_get_ticker(symbol: str):
        return SimpleNamespace(last=101.5)

    async def fake_execute_signal(signal):
        return []

    monkeypatch.setattr(trades_module.RiskService, "validate_trade", fake_validate_trade)
    monkeypatch.setattr(trades_module.kraken_service, "get_ticker", fake_get_ticker)
    monkeypatch.setattr(trades_module.paper_trading_engine, "execute_signal", fake_execute_signal)

    payload = trades_module.ManualOrderSubmitRequest(
        symbol="btc/usd",
        side=side,
        order_type="market",
        quantity=0.75,
    )

    response = await trades_module.submit_manual_order(payload, current_user=_user(), db=db_session)

    assert response.status == "filled"
    assert response.reason_code is None
    assert response.requested_quantity == pytest.approx(0.75)
    assert response.filled_quantity == pytest.approx(0.75)
    assert response.order_type == "market"
    assert response.symbol == "BTC/USD"
    assert risk_calls and risk_calls[0]["symbol"] == "BTC/USD"


@pytest.mark.asyncio
async def test_limit_order_requires_limit_price():
    with pytest.raises(Exception):
        trades_module.ManualOrderSubmitRequest(
            symbol="ETH/USD",
            side="buy",
            order_type="limit",
            quantity=0.2,
        )


@pytest.mark.asyncio
async def test_limit_order_submission_is_stored_pending_without_immediate_fill(
    db_session,
    monkeypatch,
):
    async def fake_validate_trade(**kwargs):
        return None

    monkeypatch.setattr(trades_module.RiskService, "validate_trade", fake_validate_trade)

    payload = trades_module.ManualOrderSubmitRequest(
        symbol="ETH/USD",
        side="buy",
        order_type="limit",
        quantity=1.25,
        limit_price=2500.0,
    )

    response = await trades_module.submit_manual_order(payload, current_user=_user(), db=db_session)

    assert response.status == "pending"
    assert response.filled_quantity == 0.0

    order = await db_session.get(Order, response.order_id)
    assert order is not None
    assert order.status == "pending"
    assert float(order.filled_quantity) == 0.0

    trade = await db_session.get(Trade, response.trade_id)
    assert trade is not None
    assert trade.entry_time is None


@pytest.mark.asyncio
async def test_risk_percent_sizing_uses_mocked_equity_and_reference_price(
    db_session,
    monkeypatch,
):
    async def fake_get_ticker(symbol: str):
        return SimpleNamespace(last=1000.0)

    async def fake_account_equity(db):
        return 20_000.0

    async def fake_validate_trade(**kwargs):
        return None

    async def fake_execute_signal(signal):
        return []

    monkeypatch.setattr(trades_module.kraken_service, "get_ticker", fake_get_ticker)
    monkeypatch.setattr(trades_module.RiskService, "account_equity", fake_account_equity)
    monkeypatch.setattr(trades_module.RiskService, "validate_trade", fake_validate_trade)
    monkeypatch.setattr(trades_module.paper_trading_engine, "execute_signal", fake_execute_signal)

    payload = trades_module.ManualOrderSubmitRequest(
        symbol="BTC/USD",
        side="buy",
        order_type="market",
        risk_percent=5.0,
    )

    response = await trades_module.submit_manual_order(payload, current_user=_user(), db=db_session)

    assert response.requested_quantity == pytest.approx(1.0)
    assert response.filled_quantity == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_risk_gate_rejection_returns_typed_payload_and_persists_nothing(
    db_session,
    monkeypatch,
):
    async def fake_get_ticker(symbol: str):
        return SimpleNamespace(last=100.0)

    async def fake_validate_trade(**kwargs):
        raise RiskException("Trade exceeds limit", details={"reason": "position_size"})

    monkeypatch.setattr(trades_module.kraken_service, "get_ticker", fake_get_ticker)
    monkeypatch.setattr(trades_module.RiskService, "validate_trade", fake_validate_trade)

    payload = trades_module.ManualOrderSubmitRequest(
        symbol="SOL/USD",
        side="buy",
        order_type="market",
        quantity=2.0,
    )

    with pytest.raises(RiskException) as exc:
        await trades_module.submit_manual_order(payload, current_user=_user(), db=db_session)

    assert exc.value.detail["code"] == "risk_limit_exceeded"

    trades_result = await db_session.execute(trades_module.select(Trade))
    orders_result = await db_session.execute(trades_module.select(Order))
    assert trades_result.scalars().all() == []
    assert orders_result.scalars().all() == []


@pytest.mark.asyncio
async def test_partial_close_reduces_remaining_quantity(db_session, monkeypatch):
    trade = Trade(
        symbol="BTC/USD",
        side="buy",
        quantity=2.0,
        entry_price=100.0,
        entry_time=datetime.utcnow(),
        is_manual=True,
        is_paper=True,
    )
    db_session.add(trade)
    await db_session.commit()
    await db_session.refresh(trade)

    async def fake_get_cached_price(symbol: str):
        return 110.0

    async def fake_validate_close(**kwargs):
        return None

    async def fake_execute_signal(signal):
        return []

    monkeypatch.setattr(trades_module.paper_trading_engine, "get_cached_price", fake_get_cached_price)
    monkeypatch.setattr(trades_module.paper_trading_engine, "execute_signal", fake_execute_signal)
    monkeypatch.setattr(trades_module.RiskService, "validate_close", fake_validate_close)

    response = await trades_module.close_trade(
        trade.id,
        trades_module.CloseTradeRequest(quantity=0.75, close_reason="trim"),
        current_user=_user(),
        db=db_session,
    )

    assert response.filled_quantity == pytest.approx(0.75)
    assert response.remaining_quantity == pytest.approx(1.25)

    await db_session.refresh(trade)
    assert trade.exit_time is None
    assert trade.quantity == pytest.approx(1.25)


@pytest.mark.asyncio
async def test_close_without_quantity_performs_full_close(db_session, monkeypatch):
    trade = Trade(
        symbol="ETH/USD",
        side="buy",
        quantity=1.5,
        entry_price=200.0,
        entry_time=datetime.utcnow(),
        is_manual=True,
        is_paper=True,
    )
    db_session.add(trade)
    await db_session.commit()
    await db_session.refresh(trade)

    async def fake_get_cached_price(symbol: str):
        return 210.0

    async def fake_validate_close(**kwargs):
        return None

    async def fake_execute_signal(signal):
        return []

    monkeypatch.setattr(trades_module.paper_trading_engine, "get_cached_price", fake_get_cached_price)
    monkeypatch.setattr(trades_module.paper_trading_engine, "execute_signal", fake_execute_signal)
    monkeypatch.setattr(trades_module.RiskService, "validate_close", fake_validate_close)

    response = await trades_module.close_trade(
        trade.id,
        trades_module.CloseTradeRequest(close_reason="take_profit"),
        current_user=_user(),
        db=db_session,
    )

    assert response.remaining_quantity == 0.0
    assert response.status == "filled"
    assert response.executed_price == pytest.approx(210.0)

    await db_session.refresh(trade)
    assert trade.exit_time is not None


@pytest.mark.asyncio
async def test_close_rejects_quantity_greater_than_open_position(db_session):
    trade = Trade(
        symbol="ADA/USD",
        side="buy",
        quantity=1.0,
        entry_price=1.0,
        entry_time=datetime.utcnow(),
        is_manual=True,
        is_paper=True,
    )
    db_session.add(trade)
    await db_session.commit()
    await db_session.refresh(trade)

    with pytest.raises(HTTPException) as exc:
        await trades_module.close_trade(
            trade.id,
            trades_module.CloseTradeRequest(quantity=2.0),
            current_user=_user(),
            db=db_session,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "insufficient_position_quantity"
