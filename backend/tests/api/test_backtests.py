import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_backtest_api_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

# Mock dependencies
@pytest.fixture(autouse=True, scope="module")
def mock_deps():
    mocks = {
        "core.settings": MagicMock(),
        "websockets": MagicMock(),
        "openai": MagicMock(),
        "anthropic": MagicMock(),
    }
    original_modules = {}
    for name, m in mocks.items():
        if name in sys.modules:
            original_modules[name] = sys.modules[name]
        sys.modules[name] = m
    yield mocks
    for name in mocks:
        if name in original_modules:
            sys.modules[name] = original_modules[name]
        else:
            del sys.modules[name]

from api.backtests import trigger_backtest, get_backtest, list_strategy_backtests, BacktestRequest
from db.database import AsyncSessionLocal, Base, async_engine
from db.models import Strategy, User, BacktestRun

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

@pytest.mark.asyncio
async def test_trigger_backtest_creates_record(db_session):
    # Seed strategy
    strategy = Strategy(
        name="Test Strategy",
        rules_json={"momentum": 0.01},
        status="paper"
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)

    payload = BacktestRequest(
        strategy_id=strategy.id,
        symbol="BTC/USD",
        start_date=datetime.utcnow() - timedelta(days=7),
        end_date=datetime.utcnow(),
        initial_capital=50000.0
    )

    response = await trigger_backtest(payload, current_user=_user(), db=db_session)
    assert response.strategy_id == strategy.id
    assert response.symbol == "BTC/USD"
    assert response.initial_capital == 50000.0
    assert response.status == "running"

    # Verify in DB
    db_record = await db_session.get(BacktestRun, response.id)
    assert db_record is not None
    assert db_record.symbol == "BTC/USD"

@pytest.mark.asyncio
async def test_trigger_backtest_nonexistent_strategy(db_session):
    payload = BacktestRequest(
        strategy_id=999,
        symbol="BTC/USD",
        start_date=datetime.utcnow() - timedelta(days=7),
        end_date=datetime.utcnow(),
        initial_capital=50000.0
    )

    with pytest.raises(HTTPException) as exc:
        await trigger_backtest(payload, current_user=_user(), db=db_session)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_get_backtest(db_session):
    # Seed strategy and backtest
    strategy = Strategy(name="S1", rules_json={}, status="paper")
    db_session.add(strategy)
    await db_session.commit()
    
    backtest = BacktestRun(
        strategy_id=strategy.id,
        symbol="ETH/USD",
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow(),
        initial_capital=1000.0,
        status="completed",
        total_trades=5
    )
    db_session.add(backtest)
    await db_session.commit()
    await db_session.refresh(backtest)

    response = await get_backtest(backtest.id, current_user=_user(), db=db_session)
    assert response.id == backtest.id
    assert response.status == "completed"
    assert response.total_trades == 5

@pytest.mark.asyncio
async def test_list_strategy_backtests(db_session):
    strategy = Strategy(name="S1", rules_json={}, status="paper")
    db_session.add(strategy)
    await db_session.commit()

    for i in range(3):
        bt = BacktestRun(
            strategy_id=strategy.id,
            symbol="BTC/USD",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow(),
            initial_capital=1000.0,
            status="completed"
        )
        db_session.add(bt)
    await db_session.commit()

    response = await list_strategy_backtests(strategy.id, limit=20, current_user=_user(), db=db_session)
    assert len(response) == 3
