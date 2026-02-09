import os
import sys
from pathlib import Path
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sqlalchemy import select

# Add ROOT_PATH to sys.path
ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

# Use a temporary test DB
TEST_DB_PATH = Path("/tmp/cryptotrader_perf_service_test.db")
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from db.database import AsyncSessionLocal, Base, async_engine
from db.models import PerformanceSnapshot, Trade, MarketData
from services.performance_service import performance_service

@pytest_asyncio.fixture
async def db_session():
    async with async_engine.begin() as conn:
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

class AsyncContextManagerMock:
    def __init__(self, session):
        self.session = session
    async def __aenter__(self):
        return self.session
    async def __aexit__(self, exc_type, exc, tb):
        pass

@pytest.mark.asyncio
async def test_capture_snapshot_paper(db_session):
    # Mock paper trading engine
    mock_snapshot = MagicMock()
    mock_snapshot.equity = 15000.0
    mock_snapshot.cash = 10000.0
    mock_snapshot.open_positions = []
    
    with patch("services.performance_service.paper_trading_engine.snapshot", AsyncMock(return_value=mock_snapshot)), \
         patch("services.performance_service.kraken_service.is_authenticated", False), \
         patch("services.performance_service.AsyncSessionLocal", return_value=AsyncContextManagerMock(db_session)):
        
        snapshot = await performance_service.capture_snapshot()
        assert snapshot is not None
        assert snapshot.total_equity == 15000.0
        assert snapshot.cash_balance == 10000.0

@pytest.mark.asyncio
async def test_sanitize_metric():
    assert performance_service._sanitize_metric(1.23) == 1.23
    assert performance_service._sanitize_metric(np.nan) == 0.0
    assert performance_service._sanitize_metric(np.inf) == 0.0

@pytest.mark.asyncio
async def test_cleanup_old_snapshots(db_session):
    # Add old snapshots
    now = datetime.utcnow()
    # Ensure they are distinct days for the anchor test
    old1 = now - timedelta(days=35)
    old2 = now - timedelta(days=36)
    
    # Day 1 (old1): 3 snapshots (one should stay)
    s1 = PerformanceSnapshot(total_equity=10000.0, cash_balance=10000.0, asset_value=0.0, timestamp=old1)
    s2 = PerformanceSnapshot(total_equity=10100.0, cash_balance=10100.0, asset_value=0.0, timestamp=old1 + timedelta(hours=1))
    s3 = PerformanceSnapshot(total_equity=10200.0, cash_balance=10200.0, asset_value=0.0, timestamp=old1 + timedelta(hours=2))
    
    # Recent snapshot (should stay)
    s4 = PerformanceSnapshot(total_equity=11000.0, cash_balance=11000.0, asset_value=0.0, timestamp=now)
    
    db_session.add_all([s1, s2, s3, s4])
    await db_session.commit()
    
    with patch("services.performance_service.AsyncSessionLocal", return_value=AsyncContextManagerMock(db_session)):
        count = await performance_service.cleanup_old_snapshots()
        assert count == 2 # s2 and s3 should be deleted
        
    # Verify s1 and s4 remain
    result = await db_session.execute(select(PerformanceSnapshot))
    remaining = result.scalars().all()
    assert len(remaining) == 2
    ids = [r.id for r in remaining]
    assert s1.id in ids
    assert s4.id in ids
