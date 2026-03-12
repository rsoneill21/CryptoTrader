import os
import sys
import json
import asyncio
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
os.environ["OPENAI_API_KEY"] = "sk-test-key"

# Mock missing dependencies that might be imported during route loading
mock_anthropic = MagicMock()
mock_anthropic.AI_PROMPT = "AI:"
mock_anthropic.HUMAN_PROMPT = "Human:"
sys.modules["openai"] = MagicMock()
sys.modules["anthropic"] = mock_anthropic

from main import app
from db.database import AsyncSessionLocal, Base, async_engine
from db.models import Trade, RiskSettings, User, Strategy
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

async def mock_stream_response(chunks):
    for chunk in chunks:
        yield chunk
        await asyncio.sleep(0)

@pytest.mark.asyncio
async def test_chat_clarify_broad_prompt(client: AsyncClient, db_session):
    """Broad prompts should return a clarifying follow-up."""
    risk = RiskSettings(
        max_risk_score=100.0,
        current_risk_score=50.0,
        updated_at=datetime.utcnow()
    )
    db_session.add(risk)
    await db_session.commit()

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
            
    meta = next(e for e in events if "mode" in e)
    assert meta["mode"] == "clarify"
    assert "guardrail" in meta
    
    chunk = next(e for e in events if "chunk" in e)
    assert "tactical session update" in chunk["chunk"].lower()
    assert any(e.get("done") is True for e in events)

@pytest.mark.asyncio
async def test_chat_refuse_stale_context(client: AsyncClient, db_session):
    """Stale portfolio context should trigger a refusal."""
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

@pytest.mark.asyncio
async def test_chat_refuse_incomplete_why_trade(client: AsyncClient, db_session):
    """'Why trade' prompts without specific trade context should trigger a refusal."""
    risk = RiskSettings(max_risk_score=100.0, current_risk_score=50.0, updated_at=datetime.utcnow())
    db_session.add(risk)
    await db_session.commit()

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
            json={"prompt": "Why did I take that trade?"}
        )
        assert response.status_code == status.HTTP_200_OK
        
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
                
        meta = next(e for e in events if "mode" in e)
        assert meta["mode"] == "refuse"
        assert meta["guardrail"]["incomplete_context"] is True

@pytest.mark.asyncio
async def test_chat_elevated_risk_default_hold(client: AsyncClient, db_session):
    """Elevated risk mode should default recommendations to hold and include impact."""
    risk = RiskSettings(
        max_risk_score=100.0,
        current_risk_score=90.0,
        updated_at=datetime.utcnow()
    )
    db_session.add(risk)
    await db_session.commit()

    mock_snapshot = PortfolioSnapshot(
        fetched_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        ttl_seconds=300,
        source="mock",
        holdings=[]
    )
    
    chunks = ["Preserving ", "capital."]
    with patch("services.chat_context.portfolio_service.get_snapshot", AsyncMock(return_value=mock_snapshot)), \
         patch("api.ai.ChatAIService.stream_response", return_value=mock_stream_response(chunks)):
        response = await client.post(
            "/api/ai/chat",
            json={"prompt": "Should I buy more BTC?"}
        )
        assert response.status_code == status.HTTP_200_OK
        
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
                
        # Initial metadata
        initial_meta = events[0]
        assert initial_meta["mode"] == "answer"
        assert initial_meta["recommendations"]["primary"]["action"] == "hold"
        assert initial_meta["recommendations"]["portfolio_impact"] is not None
        
        # Final metadata
        final_meta = next(e for e in events if e.get("done") is True)
        assert final_meta["portfolio_impact"] == initial_meta["recommendations"]["portfolio_impact"]

@pytest.mark.asyncio
async def test_chat_why_trade_with_rationale(client: AsyncClient, db_session):
    """'Why trade' queries should extract and normalize trade_explanation."""
    risk = RiskSettings(max_risk_score=100.0, current_risk_score=50.0, updated_at=datetime.utcnow())
    db_session.add(risk)
    
    # Create a trade to provide context
    strategy = Strategy(name="Test Strategy", rules_json={}, status="paper")
    db_session.add(strategy)
    await db_session.flush()
    
    trade = Trade(
        strategy_id=strategy.id,
        symbol="BTC/USD",
        side="buy",
        entry_time=datetime.utcnow() - timedelta(hours=1),
        exit_time=datetime.utcnow() - timedelta(minutes=30),
        entry_price=50000.0,
        exit_price=51000.0,
        quantity=0.1,
        entry_reasoning_json={"signal": "buy", "reason": "test"}
    )
    db_session.add(trade)
    await db_session.commit()

    mock_snapshot = PortfolioSnapshot(fetched_at=datetime.utcnow(), expires_at=datetime.utcnow() + timedelta(minutes=5), ttl_seconds=300, source="mock", holdings=[])
    
    rationale_json = json.dumps({
        "thesis": "Momentum breakout",
        "market_signals": ["RSI > 70", "MACD cross"],
        "risk_checks": ["Stop loss hit", "Exposure OK"],
        "counterfactual": "Price drops below support"
    })
    chunks = ["The trade was taken because... ", f"<rationale>{rationale_json}</rationale>"]
    
    with patch("services.chat_context.portfolio_service.get_snapshot", AsyncMock(return_value=mock_snapshot)), \
         patch("api.ai.ChatAIService.stream_response", return_value=mock_stream_response(chunks)):
        response = await client.post(
            "/api/ai/chat",
            json={"prompt": f"Why did I take trade {trade.id}?"}
        )
        assert response.status_code == status.HTTP_200_OK
        
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
                
        final_meta = next(e for e in events if e.get("done") is True)
        assert "trade_explanation" in final_meta
        explanation = final_meta["trade_explanation"]
        assert explanation["thesis"] == "Momentum breakout"
        assert "RSI > 70" in explanation["market_signals"]
        
        # Verify JSON block was stripped from summary_paragraph
        assert "<rationale>" not in final_meta["summary_paragraph"]
        assert "taken because..." in final_meta["summary_paragraph"]

@pytest.mark.asyncio
async def test_chat_confidence_requested(client: AsyncClient, db_session):
    """Confidence should be included in meta only when requested."""
    risk = RiskSettings(max_risk_score=100.0, current_risk_score=50.0, updated_at=datetime.utcnow())
    db_session.add(risk)
    await db_session.commit()

    mock_snapshot = PortfolioSnapshot(fetched_at=datetime.utcnow(), expires_at=datetime.utcnow() + timedelta(minutes=5), ttl_seconds=300, source="mock", holdings=[])
    
    chunks = ["BTC looks good."]
    with patch("services.chat_context.portfolio_service.get_snapshot", AsyncMock(return_value=mock_snapshot)), \
         patch("api.ai.ChatAIService.stream_response", return_value=mock_stream_response(chunks)):
        
        # Case 1: Not requested
        response = await client.post("/api/ai/chat", json={"prompt": "BTC price?"})
        events = [json.loads(line[6:]) async for line in response.aiter_lines() if line.startswith("data: ")]
        meta = next(e for e in events if "mode" in e)
        assert meta.get("include_confidence") is False

        # Case 2: Requested
        response = await client.post("/api/ai/chat", json={"prompt": "How sure are you about BTC?"})
        events = [json.loads(line[6:]) async for line in response.aiter_lines() if line.startswith("data: ")]
        meta = next(e for e in events if "mode" in e)
        assert meta.get("include_confidence") is True

@pytest.mark.asyncio
async def test_chat_portfolio_impact_present_only_on_action(client: AsyncClient, db_session):
    """Portfolio impact appears only for position-changing recommendations."""
    risk = RiskSettings(max_risk_score=100.0, current_risk_score=50.0, updated_at=datetime.utcnow())
    db_session.add(risk)
    await db_session.commit()

    mock_snapshot = PortfolioSnapshot(fetched_at=datetime.utcnow(), expires_at=datetime.utcnow() + timedelta(minutes=5), ttl_seconds=300, source="mock", holdings=[])
    
    chunks = ["Processing..."]
    with patch("services.chat_context.portfolio_service.get_snapshot", AsyncMock(return_value=mock_snapshot)), \
         patch("api.ai.ChatAIService.stream_response", return_value=mock_stream_response(chunks)):
        
        # Case 1: General question (no action)
        response = await client.post("/api/ai/chat", json={"prompt": "Tell me about the market."})
        events = [json.loads(line[6:]) async for line in response.aiter_lines() if line.startswith("data: ")]
        meta = next(e for e in events if "mode" in e)
        assert meta["recommendations"]["portfolio_impact"] is None

        # Case 2: Recommendation request (action)
        response = await client.post("/api/ai/chat", json={"prompt": "Should I buy BTC?"})
        events = [json.loads(line[6:]) async for line in response.aiter_lines() if line.startswith("data: ")]
        meta = next(e for e in events if "mode" in e)
        assert meta["recommendations"]["portfolio_impact"] is not None
