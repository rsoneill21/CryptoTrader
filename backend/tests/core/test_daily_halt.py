"""Tests for daily loss halts that include unrealized P&L."""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_daily_halt_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from core.risk import RiskService
from core.trading_control import TradingPauseStatus, trading_control
from db.database import AsyncSessionLocal, Base, SessionLocal, async_engine
from db.models import MarketData, RiskSettings, SystemLog, Trade


@pytest_asyncio.fixture
async def db_session():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        yield session

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def reset_trading_control_state():
    trading_control._status = TradingPauseStatus(
        paused=False,
        reason=None,
        triggered_by=None,
        timestamp=None,
        halted_until_date=None,
    )
    yield
    trading_control._status = TradingPauseStatus(
        paused=False,
        reason=None,
        triggered_by=None,
        timestamp=None,
        halted_until_date=None,
    )


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


def _persist_system_log(level: str, source: str, message: str, details: dict) -> None:
    db = SessionLocal()
    try:
        db.add(SystemLog(level=level, source=source, message=message, details_json=details))
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_daily_halt_pauses_when_total_pnl_breaches_limit(db_session):
    now = datetime.utcnow()
    db_session.add(
        RiskSettings(
            daily_loss_limit=100.0,
            max_position_size_pct=100.0,
            max_concurrent_positions=100,
            max_trades_per_hour=100,
            max_trades_per_day=100,
            max_asset_exposure=1_000_000.0,
        )
    )
    db_session.add(
        Trade(
            symbol="BTC/USD",
            side="buy",
            quantity=1.0,
            entry_price=100.0,
            entry_time=now - timedelta(hours=2),
            exit_time=now - timedelta(hours=1),
            pnl=-60.0,
        )
    )
    db_session.add(
        Trade(
            symbol="BTC/USD",
            side="buy",
            quantity=1.0,
            entry_price=100.0,
            entry_time=now - timedelta(minutes=20),
            exit_time=None,
            pnl=None,
        )
    )
    db_session.add(MarketData(symbol="BTC/USD", timestamp=now, open=50.0, high=50.0, low=50.0, close=50.0, volume=1.0))
    await db_session.commit()

    with patch("core.trading_control.log_system_event.delay", side_effect=_persist_system_log):
        halted = await RiskService.check_daily_halt(db_session)

    assert halted is True
    assert trading_control.is_paused() is True
    pause_status = trading_control.status()
    assert "Daily loss limit reached" in (pause_status.reason or "")
    assert pause_status.halted_until_date is not None

    logs = await db_session.execute(
        select(SystemLog).where(SystemLog.message.contains("Daily loss limit reached"))
    )
    assert logs.scalars().first() is not None


@pytest.mark.asyncio
async def test_same_day_resume_is_denied_for_daily_halt(db_session):
    fixed_now = datetime(2026, 2, 6, 10, 0, 0)

    class FrozenDateTime(datetime):
        @classmethod
        def utcnow(cls):
            return fixed_now

    with patch("core.trading_control.datetime", FrozenDateTime):
        trading_control.pause_trading(
            reason="Daily loss limit reached (including unrealized)",
            triggered_by="risk_service",
            lock_until_next_day=True,
        )
        resumed = trading_control.resume_trading(reason="operator attempt", triggered_by="operator")

    assert resumed is False
    assert trading_control.is_paused() is True


@pytest.mark.asyncio
async def test_next_day_resume_is_allowed_after_daily_halt(db_session):
    day_one = datetime(2026, 2, 6, 10, 0, 0)
    day_two = datetime(2026, 2, 7, 10, 0, 0)

    class DayOneDateTime(datetime):
        @classmethod
        def utcnow(cls):
            return day_one

    class DayTwoDateTime(datetime):
        @classmethod
        def utcnow(cls):
            return day_two

    with patch("core.trading_control.datetime", DayOneDateTime):
        trading_control.pause_trading(
            reason="Daily loss limit reached (including unrealized)",
            triggered_by="risk_service",
            lock_until_next_day=True,
        )

    with patch("core.trading_control.datetime", DayTwoDateTime):
        resumed = trading_control.resume_trading(reason="new day", triggered_by="operator")

    assert resumed is True
    assert trading_control.is_paused() is False
