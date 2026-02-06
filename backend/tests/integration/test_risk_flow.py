"""Integration coverage for end-to-end risk guardrail flow."""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_risk_flow_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from core.exceptions import RiskException
from core.paper_trading import PaperTradeSignal, PaperTradingEngine, TradeIntent, TradeSide
from core.risk import RiskService
from core.trading_control import TradingPauseStatus, trading_control
from db.database import AsyncSessionLocal, Base, SessionLocal, async_engine
from db.models import MarketData, RiskSettings, Trade


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


@pytest.mark.asyncio
async def test_risk_management_flow(db_session):
    now = datetime.utcnow()
    db_session.add(
        RiskSettings(
            max_position_size_pct=10.0,
            max_concurrent_positions=2,
            max_trades_per_hour=50,
            max_trades_per_day=3,
            max_asset_exposure=1_000_000.0,
            default_stop_loss_pct=2.0,
            daily_loss_limit=100.0,
        )
    )
    await db_session.commit()

    deep_orderbook = {
        "asks": [{"price": 1000.0, "volume": 10.0}],
        "bids": [{"price": 1000.0, "volume": 10.0}],
    }

    with patch(
        "core.risk.kraken_service.get_orderbook",
        new=AsyncMock(return_value=deep_orderbook),
    ):
        trading_control.pause_trading(reason="manual pause", triggered_by="operator")
        with pytest.raises(RiskException):
            await RiskService.validate_trade(db_session, "BTC/USD", 1.0, 100.0, "buy")
        assert trading_control.resume_trading(reason="resume", triggered_by="operator") is True

        with pytest.raises(RiskException):
            await RiskService.validate_trade(db_session, "BTC/USD", 20.0, 1_000.0, "buy")

        await RiskService.validate_trade(db_session, "BTC/USD", 5.0, 1_000.0, "buy")

    db_session.add_all(
        [
            Trade(
                symbol="BTC/USD",
                side="buy",
                quantity=0.5,
                entry_price=40_000.0,
                entry_time=now - timedelta(minutes=10),
                exit_time=None,
            ),
            Trade(
                symbol="ETH/USD",
                side="buy",
                quantity=1.0,
                entry_price=2_000.0,
                entry_time=now - timedelta(minutes=8),
                exit_time=None,
            ),
        ]
    )
    await db_session.commit()

    with patch(
        "core.risk.kraken_service.get_orderbook",
        new=AsyncMock(return_value=deep_orderbook),
    ):
        with pytest.raises(RiskException):
            await RiskService.validate_trade(db_session, "SOL/USD", 1.0, 100.0, "buy")

    await db_session.execute(delete(Trade))
    await db_session.commit()
    db_session.add_all(
        [
            Trade(
                symbol="ADA/USD",
                side="buy",
                quantity=1.0,
                entry_price=1.0,
                entry_time=now - timedelta(hours=4),
                exit_time=now - timedelta(hours=3),
                pnl=5.0,
            ),
            Trade(
                symbol="ADA/USD",
                side="buy",
                quantity=1.0,
                entry_price=1.1,
                entry_time=now - timedelta(hours=3),
                exit_time=now - timedelta(hours=2),
                pnl=5.0,
            ),
            Trade(
                symbol="ADA/USD",
                side="buy",
                quantity=1.0,
                entry_price=1.2,
                entry_time=now - timedelta(hours=2),
                exit_time=now - timedelta(hours=1),
                pnl=-1.0,
            ),
        ]
    )
    await db_session.commit()

    with patch(
        "core.risk.kraken_service.get_orderbook",
        new=AsyncMock(return_value=deep_orderbook),
    ):
        with pytest.raises(RiskException):
            await RiskService.validate_trade(db_session, "ADA/USD", 1.0, 1.0, "buy")

    engine_instance = PaperTradingEngine(
        db_factory=SessionLocal,
        async_session_factory=AsyncSessionLocal,
    )
    engine_instance._persistence_enabled = False
    closed_trades = []

    async def _capture_closed_trades(trades):
        trade_list = list(trades)
        closed_trades.extend(trade_list)
        return len(trade_list)

    engine_instance.persist_closed_trades = _capture_closed_trades  # type: ignore[method-assign]

    await engine_instance.execute_signal(
        PaperTradeSignal(
            symbol="SOL/USD",
            intent=TradeIntent.ENTRY,
            side=TradeSide.BUY,
            quantity=1.0,
            price=100.0,
        )
    )
    await engine_instance.update_market_price("SOL/USD", 97.0)
    assert len(closed_trades) == 1

    await db_session.execute(delete(Trade))
    await db_session.commit()

    db_session.add(
        Trade(
            symbol="BTC/USD",
            side="buy",
            quantity=1.0,
            entry_price=100.0,
            entry_time=now - timedelta(hours=1),
            exit_time=now - timedelta(minutes=45),
            pnl=-60.0,
        )
    )
    db_session.add(
        Trade(
            symbol="BTC/USD",
            side="buy",
            quantity=1.0,
            entry_price=100.0,
            entry_time=now - timedelta(minutes=10),
            exit_time=None,
            pnl=None,
        )
    )
    db_session.add(MarketData(symbol="BTC/USD", timestamp=now, open=40.0, high=40.0, low=40.0, close=40.0, volume=1.0))
    await db_session.commit()

    halted = await RiskService.check_daily_halt(db_session)
    assert halted is True
    assert trading_control.is_paused() is True

    with patch(
        "core.risk.kraken_service.get_orderbook",
        new=AsyncMock(return_value=deep_orderbook),
    ):
        with pytest.raises(RiskException):
            await RiskService.validate_trade(db_session, "BTC/USD", 1.0, 100.0, "buy")
