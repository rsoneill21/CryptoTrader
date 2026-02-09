import os
import sys
from pathlib import Path
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

# Add ROOT_PATH to sys.path
ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

# Use a temporary test DB
TEST_DB_PATH = Path("/tmp/cryptotrader_perf_api_test.db")
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from main import app
from fastapi.responses import StreamingResponse
from db.database import get_async_db, AsyncSessionLocal, Base, async_engine
from db.models import PerformanceSnapshot, Trade, Strategy

@pytest_asyncio.fixture
async def db_session():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        yield session

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def client(db_session):
    async def _get_test_db():
        yield db_session
    
    app.dependency_overrides[get_async_db] = _get_test_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

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
async def test_get_performance_summary_empty(client):
    response = await client.get("/api/performance/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_equity"] == 0.0
    assert "timestamp" in data

@pytest.mark.asyncio
async def test_get_performance_summary_with_data(client, db_session):
    snapshot = PerformanceSnapshot(
        total_equity=10000.0,
        cash_balance=5000.0,
        asset_value=5000.0,
        timestamp=datetime.utcnow()
    )
    db_session.add(snapshot)
    await db_session.commit()
    
    response = await client.get("/api/performance/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_equity"] == 10000.0

@pytest.mark.asyncio
async def test_get_performance_history_filters(client, db_session):
    # Add some snapshots
    now = datetime.utcnow()
    s1 = PerformanceSnapshot(
        total_equity=10000.0, cash_balance=5000.0, asset_value=5000.0,
        timestamp=now - timedelta(days=5), asset_pair="BTC/USD"
    )
    s2 = PerformanceSnapshot(
        total_equity=11000.0, cash_balance=5000.0, asset_value=6000.0,
        timestamp=now - timedelta(days=2), asset_pair="ETH/USD"
    )
    db_session.add_all([s1, s2])
    await db_session.commit()
    
    # Test timeframe
    response = await client.get("/api/performance/history?timeframe=1w")
    assert len(response.json()["history"]) == 2
    
    response = await client.get("/api/performance/history?timeframe=1d")
    assert len(response.json()["history"]) == 0
    
    # Test asset_pair filter
    response = await client.get("/api/performance/history?asset_pair=BTC/USD")
    assert len(response.json()["history"]) == 1
    assert response.json()["history"][0]["total_equity"] == 10000.0

@pytest.mark.asyncio
async def test_get_performance_trades(client, db_session):
    trade = Trade(
        symbol="BTC/USD",
        side="buy",
        quantity=1.0,
        entry_price=50000.0,
        exit_price=51000.0,
        pnl=1000.0,
        entry_time=datetime.utcnow() - timedelta(hours=2),
        exit_time=datetime.utcnow() - timedelta(hours=1)
    )
    db_session.add(trade)
    await db_session.commit()
    
    response = await client.get("/api/performance/trades")
    assert response.status_code == 200
    data = response.json()
    assert len(data["trades"]) == 1
    assert data["trades"][0]["pnl"] == 1000.0

@pytest.mark.asyncio
async def test_performance_stream_smoke(client):
    # Mock the generator itself to just yield one thing and exit
    async def mock_generator():
        yield "data: {}\n\n"
    
    with patch("api.performance.StreamingResponse", side_effect=lambda gen, **kwargs: StreamingResponse(mock_generator(), **kwargs)):
        response = await client.get("/api/performance/stream")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
