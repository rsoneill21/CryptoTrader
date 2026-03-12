"""Regression tests for order lifecycle reconciliation service."""

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

TEST_DB_PATH = Path("/tmp/cryptotrader_order_lifecycle_sync_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from db.database import AsyncSessionLocal, Base, async_engine
from db.models import Order, Trade
from services import trade_sync as trade_sync_module


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


async def _seed_order(db_session, *, status="pending", quantity=2.0, filled=0.0, exchange_order_id="ex-1"):
    trade = Trade(
        symbol="BTC/USD",
        side="buy",
        quantity=quantity,
        entry_price=100.0,
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
        price=100.0,
        quantity=quantity,
        filled_quantity=filled,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest.mark.asyncio
async def test_reconcile_progresses_pending_to_partial_to_filled_without_regression(db_session, monkeypatch):
    order = await _seed_order(db_session)

    snapshots = iter(
        [
            SimpleNamespace(status=SimpleNamespace(value="open"), filled_volume=0.0),
            SimpleNamespace(status=SimpleNamespace(value="open"), filled_volume=0.8),
            SimpleNamespace(status=SimpleNamespace(value="closed"), filled_volume=2.0),
            SimpleNamespace(status=SimpleNamespace(value="open"), filled_volume=1.5),
        ]
    )

    async def fake_get_order_status(exchange_order_id: str):
        return next(snapshots)

    monkeypatch.setattr(trade_sync_module.kraken_service, "get_order_status", fake_get_order_status)

    first = await trade_sync_module.order_lifecycle_sync_service.reconcile_order(db_session, order)
    await db_session.commit()
    assert first.status == "pending"
    assert first.filled_quantity == pytest.approx(0.0)

    second = await trade_sync_module.order_lifecycle_sync_service.reconcile_order(db_session, order)
    await db_session.commit()
    assert second.status == "partially_filled"
    assert second.filled_quantity == pytest.approx(0.8)

    third = await trade_sync_module.order_lifecycle_sync_service.reconcile_order(db_session, order)
    await db_session.commit()
    assert third.status == "filled"
    assert third.filled_quantity == pytest.approx(2.0)

    fourth = await trade_sync_module.order_lifecycle_sync_service.reconcile_order(db_session, order)
    await db_session.commit()
    assert fourth.status == "filled"
    assert fourth.filled_quantity == pytest.approx(2.0)
    assert fourth.changed is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exchange_status", "expected_status", "expected_code"),
    [
        ("rejected", "rejected", "order_rejected"),
        ("canceled", "canceled", "order_canceled"),
    ],
)
async def test_reconcile_terminal_failures_capture_reason_metadata(
    db_session,
    monkeypatch,
    exchange_status,
    expected_status,
    expected_code,
):
    order = await _seed_order(db_session)

    async def fake_get_order_status(exchange_order_id: str):
        return SimpleNamespace(status=SimpleNamespace(value=exchange_status), filled_volume=0.0)

    monkeypatch.setattr(trade_sync_module.kraken_service, "get_order_status", fake_get_order_status)

    result = await trade_sync_module.order_lifecycle_sync_service.reconcile_order(db_session, order)
    await db_session.commit()
    await db_session.refresh(order)

    assert result.status == expected_status
    assert result.reason_code == expected_code
    assert result.reason_message
    assert order.error_message.startswith(f"[{expected_code}]")
