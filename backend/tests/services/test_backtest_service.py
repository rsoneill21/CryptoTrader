import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
import pandas as pd

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_backtest_service_test.db")
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

from services.backtest_service import BacktestService
from core.strategy_evaluator import StrategyEvaluator
from db.database import AsyncSessionLocal, Base, async_engine
from db.models import Strategy, MarketData, BacktestRun

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
async def test_strategy_evaluator_basic():
    rules = {
        "entry": {
            "conditions": [
                {"indicator": "rsi", "window": 14, "operator": "<", "value": 30}
            ],
            "logic": "and"
        },
        "exit": {
            "conditions": [
                {"indicator": "rsi", "window": 14, "operator": ">", "value": 70}
            ],
            "logic": "and"
        }
    }
    evaluator = StrategyEvaluator(rules)
    
    # Create dummy data
    data = []
    now = datetime.utcnow()
    for i in range(100):
        # RSI < 30 at start, then RSI > 70
        price = 100.0 - i if i < 20 else 100.0 + i
        data.append({
            "timestamp": now + timedelta(minutes=i),
            "close": price
        })
    df = pd.DataFrame(data)
    
    eval_df = evaluator.evaluate(df)
    assert 'entry_signal' in eval_df.columns
    assert 'exit_signal' in eval_df.columns
    assert eval_df['entry_signal'].any()
    assert eval_df['exit_signal'].any()

@pytest.mark.asyncio
async def test_backtest_service_run(db_session):
    # 1. Seed Market Data
    now = datetime.utcnow()
    symbol = "BTC/USD"
    for i in range(50):
        # price goes down then up
        price = 50000.0 - (i * 100) if i < 25 else 50000.0 - (2500) + ((i-25) * 200)
        md = MarketData(
            symbol=symbol,
            timestamp=now + timedelta(minutes=i),
            open=price,
            high=price + 10,
            low=price - 10,
            close=price,
            volume=1.0,
            timeframe="1m"
        )
        db_session.add(md)
    
    # 2. Seed Strategy
    strategy = Strategy(
        name="RSI Mean Reversion",
        rules_json={
            "entry": {
                "conditions": [{"indicator": "rsi", "window": 10, "operator": "<", "value": 30}],
                "logic": "and"
            },
            "exit": {
                "conditions": [{"indicator": "rsi", "window": 10, "operator": ">", "value": 70}],
                "logic": "and"
            }
        },
        status="paper"
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)
    
    # 3. Create BacktestRun
    backtest = BacktestRun(
        strategy_id=strategy.id,
        symbol=symbol,
        start_date=now,
        end_date=now + timedelta(minutes=50),
        initial_capital=100000.0,
        status="running"
    )
    db_session.add(backtest)
    await db_session.commit()
    await db_session.refresh(backtest)
    
    # 4. Run Backtest
    service = BacktestService(db_session)
    await service.run_backtest(backtest.id)
    
    # 5. Verify Results
    await db_session.refresh(backtest)
    assert backtest.status == "completed"
    assert backtest.total_trades >= 0
    assert backtest.final_capital is not None
    assert backtest.results_json is not None
    assert "equity_curve" in backtest.results_json
