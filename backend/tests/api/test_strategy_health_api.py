import os
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

# Setup PYTHONPATH and DATABASE_URL
ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_api_health_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from main import app
from db.database import AsyncSessionLocal, Base, async_engine, get_async_db
from db.models import Strategy, User
from core.auth import get_current_user

@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    
    async def override_get_current_user():
        return User(id=1, email="test@example.com")

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture
async def db_session():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        yield session

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

def test_get_strategy_health_fields(client, db_session):
    # 1. Create strategy with health info
    import asyncio
    
    async def _setup():
        strategy = Strategy(
            name="Health Test API",
            rules_json={"signal": "test"},
            status="paper",
            health_status="degraded",
            pending_adjustment_json={"suggestion": "improve stuff"}
        )
        db_session.add(strategy)
        await db_session.commit()
        await db_session.refresh(strategy)
        return strategy.id

    loop = asyncio.get_event_loop()
    strategy_id = loop.run_until_complete(_setup())

    # 2. Get strategy via API
    response = client.get(f"/api/strategies/{strategy_id}")
    assert response.status_code == 200
    data = response.json()
    
    assert data["health_status"] == "degraded"
    assert data["pending_adjustment"] == {"suggestion": "improve stuff"}
