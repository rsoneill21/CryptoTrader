"""Regression tests for trades order lifecycle endpoints."""

import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_trades_order_lifecycle_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from api import trades as trades_module
from core.exceptions import ServiceUnavailableException
from db.database import AsyncSessionLocal, Base, async_engine
from db.models import Order, Trade, User
from services.kraken import KrakenAPIError


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


async def _seed_trade_with_order(
    db_session,
    *,
    exchange_order_id: str,
    status: str = "pending",
    quantity: float = 1.0,
    filled_quantity: float = 0.0,
):
    trade = Trade(
        symbol="ETH/USD",
        side="buy",
        quantity=quantity,
        entry_price=2000.0,
        entry_time=datetime.utcnow(),
        is_manual=True,
        is_paper=True,
    )
    db_session.add(trade)
    await db_session.flush()

    order = Order(
        trade_id=trade.id,
        exchange_order_id=exchange_order_id,
        status=status,
        order_type="limit",
        side="buy",
        price=1999.0,
        quantity=quantity,
        filled_quantity=filled_quantity,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return trade, order


@pytest.mark.asyncio
async def test_pending_endpoint_excludes_terminal_orders_and_includes_partials(db_session, monkeypatch):
    _, pending_order = await _seed_trade_with_order(db_session, exchange_order_id="ex-pending")
    _, filled_order = await _seed_trade_with_order(db_session, exchange_order_id="ex-filled")
    _, local_partial = await _seed_trade_with_order(
        db_session,
        exchange_order_id="",
        status="partially_filled",
        quantity=2.0,
        filled_quantity=0.5,
    )

    async def fake_get_order_status(exchange_order_id: str):
        payloads = {
            "ex-pending": SimpleNamespace(status=SimpleNamespace(value="open"), filled_volume=0.25),
            "ex-filled": SimpleNamespace(status=SimpleNamespace(value="closed"), filled_volume=1.0),
        }
        return payloads[exchange_order_id]

    monkeypatch.setattr(trades_module.kraken_service, "get_order_status", fake_get_order_status)

    response = await trades_module.list_pending_orders(current_user=_user(), db=db_session)
    returned_ids = {item.id for item in response}

    assert pending_order.id in returned_ids
    assert local_partial.id in returned_ids
    assert filled_order.id not in returned_ids

    refreshed_pending = await db_session.get(Order, pending_order.id)
    assert refreshed_pending.status == "partially_filled"
    assert float(refreshed_pending.filled_quantity) == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_status_refresh_is_idempotent_and_does_not_regress_filled_quantity(db_session, monkeypatch):
    _, order = await _seed_trade_with_order(
        db_session,
        exchange_order_id="ex-idempotent",
        status="partially_filled",
        quantity=1.0,
        filled_quantity=0.6,
    )

    snapshots = iter(
        [
            SimpleNamespace(status=SimpleNamespace(value="open"), filled_volume=0.5),
            SimpleNamespace(status=SimpleNamespace(value="open"), filled_volume=0.4),
        ]
    )

    async def fake_get_order_status(exchange_order_id: str):
        return next(snapshots)

    monkeypatch.setattr(trades_module.kraken_service, "get_order_status", fake_get_order_status)

    first = await trades_module.get_order_status(order.id, current_user=_user(), db=db_session)
    second = await trades_module.get_order_status(order.id, current_user=_user(), db=db_session)

    assert first.filled_quantity == pytest.approx(0.6)
    assert second.filled_quantity == pytest.approx(0.6)
    assert second.status == "partially_filled"


@pytest.mark.asyncio
async def test_rejection_status_returns_reason_code_and_message(db_session, monkeypatch):
    _, order = await _seed_trade_with_order(db_session, exchange_order_id="ex-rejected")

    async def fake_get_order_status(exchange_order_id: str):
        return SimpleNamespace(status=SimpleNamespace(value="rejected"), filled_volume=0.0)

    monkeypatch.setattr(trades_module.kraken_service, "get_order_status", fake_get_order_status)

    response = await trades_module.get_order_status(order.id, current_user=_user(), db=db_session)

    assert response.status == "rejected"
    assert response.reason_code == "order_rejected"
    assert response.reason_message == "Order was rejected by exchange"


@pytest.mark.asyncio
async def test_exchange_failure_raises_service_unavailable_and_keeps_persisted_state(db_session, monkeypatch):
    _, order = await _seed_trade_with_order(
        db_session,
        exchange_order_id="ex-failure",
        status="partially_filled",
        quantity=1.0,
        filled_quantity=0.7,
    )

    async def failing_get_order_status(exchange_order_id: str):
        raise KrakenAPIError("kraken down")

    monkeypatch.setattr(trades_module.kraken_service, "get_order_status", failing_get_order_status)

    with pytest.raises(ServiceUnavailableException) as exc:
        await trades_module.get_order_status(order.id, current_user=_user(), db=db_session)

    assert exc.value.detail["code"] == "service_unavailable"

    preserved = await db_session.get(Order, order.id)
    assert preserved.status == "partially_filled"
    assert float(preserved.filled_quantity) == pytest.approx(0.7)
