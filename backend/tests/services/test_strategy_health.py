import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

# Setup PYTHONPATH and DATABASE_URL
ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_health_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from db.database import AsyncSessionLocal, Base, async_engine
from db.models import Strategy, Trade, Alert
from services.strategy_service import check_strategy_health, HealthStatus, monitor_strategies

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
async def test_health_check_degradation(db_session: AsyncSession):
    # 1. Create a strategy
    strategy = Strategy(
        name="Test Strategy",
        rules_json={},
        status="paper"
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)

    # 2. Seed with losing trades (Win Rate = 20%)
    for i in range(10):
        trade = Trade(
            strategy_id=strategy.id,
            symbol="BTC/USD",
            side="buy",
            quantity=1.0,
            entry_price=100.0,
            exit_price=90.0 if i < 8 else 110.0, # 8 losses, 2 wins
            pnl=-10.0 if i < 8 else 10.0,
            exit_time=datetime.now() - timedelta(minutes=i)
        )
        db_session.add(trade)
    
    await db_session.commit()

    # 3. Check health
    health_result = await check_strategy_health(db_session, strategy.id)
    
    assert health_result["status"] == HealthStatus.CRITICAL
    assert health_result["metrics"]["win_rate"] == 0.2
    assert health_result["metrics"]["total_trades"] == 10

@pytest.mark.asyncio
async def test_health_check_healthy(db_session: AsyncSession):
    # 1. Create a strategy
    strategy = Strategy(
        name="Healthy Strategy",
        rules_json={},
        status="paper"
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)

    # 2. Seed with winning trades (Win Rate = 80%)
    for i in range(10):
        trade = Trade(
            strategy_id=strategy.id,
            symbol="BTC/USD",
            side="buy",
            quantity=1.0,
            entry_price=100.0,
            exit_price=110.0 if i < 8 else 90.0,
            pnl=10.0 if i < 8 else -10.0,
            exit_time=datetime.now() - timedelta(minutes=i)
        )
        db_session.add(trade)
    
    await db_session.commit()

    # 3. Check health
    health_result = await check_strategy_health(db_session, strategy.id)
    
    assert health_result["status"] == HealthStatus.HEALTHY
    assert health_result["metrics"]["win_rate"] == 0.8

@pytest.mark.asyncio
async def test_monitor_task(db_session: AsyncSession):
    # 1. Create a degraded strategy
    strategy = Strategy(
        name="Degraded Strategy",
        rules_json={},
        status="paper"
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)

    # Seed with losing trades
    for i in range(10):
        trade = Trade(
            strategy_id=strategy.id,
            symbol="BTC/USD",
            side="buy",
            quantity=1.0,
            entry_price=100.0,
            exit_price=90.0,
            pnl=-10.0,
            exit_time=datetime.now() - timedelta(minutes=i)
        )
        db_session.add(trade)
    await db_session.commit()

    # 2. Mock AI service
    with patch("services.strategy_service.strategy_ai_service.analyze_degradation", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = {
            "reasoning": "Market conditions changed",
            "suggestions": ["Adjust stop loss"],
            "proposed_rules": {"stop_loss": 0.05}
        }

        # 3. Run monitor task
        result = await monitor_strategies(db_session)

        # 4. Verify results
        assert result["strategies_monitored"] == 1
        assert result["degraded_identified"] == 1

        # Check strategy status updated
        await db_session.refresh(strategy)
        assert strategy.health_status == HealthStatus.CRITICAL.value
        assert strategy.pending_adjustment_json == mock_analyze.return_value

        # Check Alert created
        from sqlalchemy import select
        alerts_query = select(Alert).where(Alert.related_strategy_id == strategy.id)
        alerts_result = await db_session.execute(alerts_query)
        alerts = list(alerts_result.scalars().all())
        assert len(alerts) == 1
        assert "is critical" in alerts[0].title
        
        # Verify AI service called
        mock_analyze.assert_called_once()
