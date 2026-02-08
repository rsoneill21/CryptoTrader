import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Setup PYTHONPATH and DATABASE_URL
ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_tasks_health_test.db")
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
from services.strategy_service import monitor_strategies

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
async def test_monitor_task(db_session: AsyncSession):
    # 1. Setup strategy with poor performance
    strategy = Strategy(
        name="Degrading Strategy",
        rules_json={},
        status="paper",
        health_status="healthy"
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)

    # Add losing trades
    for i in range(10):
        trade = Trade(
            strategy_id=strategy.id,
            symbol="BTC/USD",
            side="buy",
            quantity=1.0,
            pnl=-10.0,
            exit_time=datetime.now() - timedelta(minutes=i)
        )
        db_session.add(trade)
    await db_session.commit()

    # 2. Mock AI service
    mock_suggestions = {
        "reasoning": "Market conditions changed",
        "suggestions": ["Tighten stop loss"],
        "proposed_rules": {"stop_loss": 0.01}
    }
    
    with patch("services.strategy_ai.strategy_ai_service.analyze_degradation", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = mock_suggestions
        
        # 3. Run the service function directly
        result = await monitor_strategies(db_session)
        
        # 4. Verify results
        assert result["strategies_monitored"] >= 1
        assert result["degraded_identified"] >= 1
        
        # Verify Alert was created
        query = select(Alert).where(Alert.related_strategy_id == strategy.id)
        alert_result = await db_session.execute(query)
        alert = alert_result.scalar_one_or_none()
        assert alert is not None
        assert "Degrading Strategy" in alert.title
        assert alert.severity in ["warning", "critical"]
        
        # Verify AI service was called
        mock_analyze.assert_called_once()
        
        # Verify Strategy was updated
        await db_session.refresh(strategy)
        assert strategy.health_status in ["degraded", "critical"]
        assert strategy.pending_adjustment_json == mock_suggestions