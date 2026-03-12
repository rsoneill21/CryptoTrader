"""Risk API settings tests for newly added risk fields."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_risk_api_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

@pytest.fixture(autouse=True, scope="module")
def mock_missing_deps():
    """Fixture to mock missing dependencies and restore them after tests."""
    anthropic_mock = MagicMock()
    anthropic_mock.AI_PROMPT = ""
    anthropic_mock.HUMAN_PROMPT = ""
    anthropic_mock.Anthropic = MagicMock()
    
    mocks = {
        "openai": MagicMock(),
        "anthropic": anthropic_mock,
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

from api.risk import (
    RiskSettingsUpdate,
    _build_settings_response,
    get_risk_settings,
    update_risk_settings,
)
from db.database import AsyncSessionLocal, Base, async_engine
from db.models import RiskSettings


@pytest_asyncio.fixture
async def db_session():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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


@pytest.mark.asyncio
async def test_build_settings_response_includes_new_fields():
    settings = RiskSettings(
        max_position_size_pct=5.0,
        max_concurrent_positions=3,
        max_asset_exposure=12_500.0,
        max_trades_per_hour=7,
        max_trades_per_day=42,
        min_liquidity_threshold=1_500.0,
        kraken_tier="pro",
        default_stop_loss_pct=1.25,
    )

    response = _build_settings_response(settings)

    assert response.max_asset_exposure == 12_500.0
    assert response.max_trades_per_hour == 7
    assert response.max_trades_per_day == 42
    assert response.min_liquidity_threshold == 1_500.0
    assert response.kraken_tier == "pro"
    assert response.default_stop_loss_pct == 1.25


@pytest.mark.asyncio
async def test_update_risk_settings_persists_new_fields(db_session):
    payload = RiskSettingsUpdate(
        max_asset_exposure=9_000.0,
        max_trades_per_hour=5,
        max_trades_per_day=25,
        min_liquidity_threshold=2_000.0,
        kraken_tier="intermediate",
        default_stop_loss_pct=2.5,
    )

    updated = await update_risk_settings(payload, db=db_session)
    current = await get_risk_settings(db=db_session)

    assert updated.max_asset_exposure == 9_000.0
    assert updated.max_trades_per_hour == 5
    assert updated.max_trades_per_day == 25
    assert updated.min_liquidity_threshold == 2_000.0
    assert updated.kraken_tier == "intermediate"
    assert updated.default_stop_loss_pct == 2.5

    assert current.max_asset_exposure == 9_000.0
    assert current.max_trades_per_hour == 5
    assert current.max_trades_per_day == 25
    assert current.min_liquidity_threshold == 2_000.0
    assert current.kraken_tier == "intermediate"
    assert current.default_stop_loss_pct == 2.5