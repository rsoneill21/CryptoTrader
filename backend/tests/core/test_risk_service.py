"""Focused tests for RiskService trade validation gates."""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_risk_service_test.db")
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
from db.models import RiskSettings, Trade


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
async def test_validate_trade_rejects_when_trading_paused(db_session):
    with patch("core.risk.trading_control.is_paused", return_value=True), patch(
        "core.risk.trading_control.status"
    ) as status_mock:
        status_mock.return_value.reason = "manual stop"
        status_mock.return_value.triggered_by = "operator"

        with pytest.raises(RiskException) as exc:
            await RiskService.validate_trade(
                db_session,
                symbol="BTC/USD",
                quantity=0.1,
                price=50_000.0,
                side="buy",
            )

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "risk_limit_exceeded"


@pytest.mark.asyncio
async def test_validate_trade_rejects_hourly_frequency_limit(db_session):
    settings = RiskSettings(
        max_position_size_pct=100.0,
        max_concurrent_positions=10,
        max_trades_per_hour=1,
        max_trades_per_day=10,
        max_asset_exposure=1_000_000.0,
    )
    db_session.add(settings)
    db_session.add(
        Trade(
            symbol="ETH/USD",
            side="buy",
            quantity=0.5,
            entry_price=3_000.0,
            entry_time=datetime.utcnow() - timedelta(minutes=5),
            exit_time=datetime.utcnow() - timedelta(minutes=1),
        )
    )
    await db_session.commit()

    with patch("core.risk.trading_control.is_paused", return_value=False):
        with pytest.raises(RiskException) as exc:
            await RiskService.validate_trade(
                db_session,
                symbol="ETH/USD",
                quantity=0.1,
                price=3_100.0,
                side="buy",
            )

    assert "Hourly" in exc.value.message


@pytest.mark.asyncio
async def test_validate_trade_rejects_daily_frequency_limit(db_session):
    settings = RiskSettings(
        max_position_size_pct=100.0,
        max_concurrent_positions=10,
        max_trades_per_hour=10,
        max_trades_per_day=1,
        max_asset_exposure=1_000_000.0,
    )
    db_session.add(settings)
    db_session.add(
        Trade(
            symbol="SOL/USD",
            side="buy",
            quantity=3.0,
            entry_price=100.0,
            entry_time=datetime.utcnow() - timedelta(hours=4),
            exit_time=datetime.utcnow() - timedelta(hours=2),
        )
    )
    await db_session.commit()

    with patch("core.risk.trading_control.is_paused", return_value=False):
        with pytest.raises(RiskException) as exc:
            await RiskService.validate_trade(
                db_session,
                symbol="SOL/USD",
                quantity=1.0,
                price=110.0,
                side="buy",
            )

    assert "Daily" in exc.value.message


@pytest.mark.asyncio
async def test_validate_trade_rejects_asset_exposure_limit(db_session):
    settings = RiskSettings(
        max_position_size_pct=100.0,
        max_concurrent_positions=10,
        max_trades_per_hour=100,
        max_trades_per_day=100,
        max_asset_exposure=10_000.0,
    )
    db_session.add(settings)
    db_session.add(
        Trade(
            symbol="BTC/USD",
            side="buy",
            quantity=90.0,
            entry_price=100.0,
            entry_time=datetime.utcnow() - timedelta(hours=2),
            exit_time=None,
        )
    )
    await db_session.commit()

    with patch("core.risk.trading_control.is_paused", return_value=False):
        with pytest.raises(RiskException) as exc:
            await RiskService.validate_trade(
                db_session,
                symbol="BTC/USD",
                quantity=20.0,
                price=100.0,
                side="buy",
            )

    assert "exposure" in exc.value.message.lower()
