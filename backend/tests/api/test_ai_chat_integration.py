import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from fastapi import status
from httpx import AsyncClient, ASGITransport

# Setup paths
ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

# Use a separate test database
TEST_DB_PATH = Path("/tmp/cryptotrader_chat_integration_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

# Mock missing dependencies that might be imported during route loading
mock_anthropic = MagicMock()
mock_anthropic.AI_PROMPT = "AI:"
mock_anthropic.HUMAN_PROMPT = "Human:"
sys.modules["openai"] = MagicMock()
sys.modules["anthropic"] = mock_anthropic

from main import app
from db.database import AsyncSessionLocal, Base, async_engine
from db.models import Trade, RiskSettings, User
from services.portfolio import PortfolioSnapshot, PortfolioHolding

@pytest_asyncio.fixture
async def db_session():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        yield session

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_chat_clarify_broad_prompt(client: AsyncClient, db_session):
    """Broad prompts should return a clarifying follow-up."""
    # Seed risk settings to avoid stale context refusal
    risk = RiskSettings(
        max_risk_score=100.0,
        current_risk_score=50.0,
        updated_at=datetime.utcnow()
    )
    db_session.add(risk)
    await db_session.commit()

    # Mock portfolio to avoid Kraken calls
    mock_snapshot = PortfolioSnapshot(
        fetched_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        ttl_seconds=300,
        source="mock",
        holdings=[]
    )
    
    with patch("services.chat_context.portfolio_service.get_snapshot", AsyncMock(return_value=mock_snapshot)):
        response = await client.post(
            "/api/ai/chat",
            json={"prompt": "How am I doing?"}
        )
        assert response.status_code == status.HTTP_200_OK
    
    events = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
            
    # Should have mode: clarify
    meta = next(e for e in events if "mode" in e)
    assert meta["mode"] == "clarify"
    assert "guardrail" in meta
    
    # Should have a chunk with the clarifying question
    chunk = next(e for e in events if "chunk" in e)
    assert "tactical session update" in chunk["chunk"].lower()
    
    # Should have done: True
    assert any(e.get("done") is True for e in events)

@pytest.mark.asyncio
async def test_chat_refuse_stale_context(client: AsyncClient, db_session):
    """Stale portfolio context should trigger a refusal."""
    # We need to mock portfolio_service.get_snapshot to return an expired one
    expired_time = datetime.utcnow() - timedelta(hours=1)
    mock_snapshot = PortfolioSnapshot(
        fetched_at=expired_time - timedelta(minutes=5),
        expires_at=expired_time,
        ttl_seconds=0,
        source="mock",
        holdings=[]
    )
    
    with patch("services.chat_context.portfolio_service.get_snapshot", AsyncMock(return_value=mock_snapshot)):
        response = await client.post(
            "/api/ai/chat",
            json={"prompt": "What is my current balance?"}
        )
        assert response.status_code == status.HTTP_200_OK
        
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
                
        meta = next(e for e in events if "mode" in e)
        assert meta["mode"] == "refuse"
        assert meta["guardrail"]["stale_context"] is True
        assert "expired_portfolio_snapshot" in meta["guardrail"]["refusal_reason"]