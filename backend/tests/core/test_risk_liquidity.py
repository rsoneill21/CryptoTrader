"""Liquidity-focused tests for RiskService."""

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_risk_liquidity_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from core.exceptions import RiskException
from core.risk import RiskService
from db.database import AsyncSessionLocal, Base, async_engine
from db.models import RiskSettings


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


async def _seed_settings(session, *, min_liquidity_threshold: float = 1.0):
    settings = RiskSettings(
        max_position_size_pct=100.0,
        max_concurrent_positions=50,
        max_trades_per_hour=500,
        max_trades_per_day=1000,
        max_asset_exposure=1_000_000_000.0,
        min_liquidity_threshold=min_liquidity_threshold,
    )
    session.add(settings)
    await session.commit()


@pytest.mark.asyncio
async def test_validate_trade_rejects_missing_orderbook(monkeypatch, db_session):
    await _seed_settings(db_session, min_liquidity_threshold=1.0)

    async def fake_orderbook(symbol, count=100):
        return {"asks": [], "bids": []}

    monkeypatch.setattr("core.risk.kraken_service.get_orderbook", fake_orderbook)

    with pytest.raises(RiskException) as exc:
        await RiskService.validate_trade(db_session, "BTC/USD", 0.2, 50_000.0, "buy")

    assert "order book liquidity" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_validate_trade_rejects_thin_orderbook_depth(monkeypatch, db_session):
    await _seed_settings(db_session, min_liquidity_threshold=5.0)

    async def fake_orderbook(symbol, count=100):
        return {
            "asks": [
                {"price": 100.0, "volume": 0.2},
                {"price": 101.0, "volume": 0.1},
            ],
            "bids": [
                {"price": 99.0, "volume": 0.2},
            ],
        }

    monkeypatch.setattr("core.risk.kraken_service.get_orderbook", fake_orderbook)

    with pytest.raises(RiskException) as exc:
        await RiskService.validate_trade(db_session, "ETH/USD", 1.0, 100.0, "buy")

    assert "insufficient order book depth" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_validate_trade_rejects_slippage_over_threshold(monkeypatch, db_session):
    await _seed_settings(db_session, min_liquidity_threshold=0.2)

    async def fake_orderbook(symbol, count=100):
        return {
            "asks": [
                {"price": 100.0, "volume": 0.5},
                {"price": 101.0, "volume": 0.5},
            ],
            "bids": [
                {"price": 99.0, "volume": 0.5},
                {"price": 98.5, "volume": 0.5},
            ],
        }

    monkeypatch.setattr("core.risk.kraken_service.get_orderbook", fake_orderbook)

    with pytest.raises(RiskException) as exc:
        await RiskService.validate_trade(db_session, "SOL/USD", 1.0, 100.0, "buy")

    assert "slippage" in exc.value.message.lower()
