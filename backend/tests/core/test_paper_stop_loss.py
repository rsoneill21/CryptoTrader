"""Tests for stop-loss defaults and trigger behavior in paper trading."""

import os
import sys
from pathlib import Path

import pytest

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_paper_stop_loss_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from core.paper_trading import PaperTradeSignal, PaperTradingEngine, TradeIntent, TradeSide
from db.database import AsyncSessionLocal, Base, SessionLocal, engine
from db.models import RiskSettings


@pytest.fixture(autouse=True)
def reset_database_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


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


def _seed_risk_settings(default_stop_loss_pct: float) -> None:
    session = SessionLocal()
    try:
        session.add(RiskSettings(default_stop_loss_pct=default_stop_loss_pct))
        session.commit()
    finally:
        session.close()


@pytest.mark.asyncio
async def test_default_stop_loss_is_derived_for_buy_and_sell_positions():
    _seed_risk_settings(default_stop_loss_pct=2.0)

    engine_instance = PaperTradingEngine(
        db_factory=SessionLocal,
        async_session_factory=AsyncSessionLocal,
    )
    engine_instance._persistence_enabled = False

    await engine_instance.execute_signal(
        PaperTradeSignal(
            symbol="BTC/USD",
            intent=TradeIntent.ENTRY,
            side=TradeSide.BUY,
            quantity=1.0,
            price=100.0,
        )
    )
    await engine_instance.execute_signal(
        PaperTradeSignal(
            symbol="ETH/USD",
            intent=TradeIntent.ENTRY,
            side=TradeSide.SELL,
            quantity=1.0,
            price=100.0,
        )
    )

    snapshot = await engine_instance.snapshot()
    positions = {position.symbol: position for position in snapshot.open_positions}

    assert positions["BTC/USD"].stop_loss_price == pytest.approx(98.0)
    assert positions["ETH/USD"].stop_loss_price == pytest.approx(102.0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "side, trigger_price",
    [
        (TradeSide.BUY, 97.0),
        (TradeSide.SELL, 103.0),
    ],
)
async def test_stop_loss_trigger_closes_position_and_records_reason(side: TradeSide, trigger_price: float):
    _seed_risk_settings(default_stop_loss_pct=2.0)

    engine_instance = PaperTradingEngine(
        db_factory=SessionLocal,
        async_session_factory=AsyncSessionLocal,
    )
    engine_instance._persistence_enabled = False

    captured_closes = []

    async def _capture_closed_trades(trades):
        trade_list = list(trades)
        captured_closes.extend(trade_list)
        return len(trade_list)

    engine_instance.persist_closed_trades = _capture_closed_trades  # type: ignore[method-assign]

    await engine_instance.execute_signal(
        PaperTradeSignal(
            symbol="SOL/USD",
            intent=TradeIntent.ENTRY,
            side=side,
            quantity=1.0,
            price=100.0,
        )
    )
    await engine_instance.update_market_price("SOL/USD", trigger_price)

    snapshot = await engine_instance.snapshot()
    assert snapshot.open_positions == []
    assert len(captured_closes) == 1
    assert captured_closes[0].metadata["exit_reasoning"]["summary"] == "Stop-Loss Triggered"
