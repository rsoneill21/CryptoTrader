import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_chat_context_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from db.database import AsyncSessionLocal, Base, async_engine
from db.models import RiskSettings, Trade
from services.chat_context import ChatContextAssembler
from services.portfolio import PortfolioHolding, PortfolioSnapshot


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


def _snapshot(*, now: datetime, expires_delta: timedelta) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        holdings=[
            PortfolioHolding(asset="BTC", total=Decimal("1.25"), available=Decimal("1.00"), reserved=Decimal("0.25")),
            PortfolioHolding(asset="ETH", total=Decimal("3.5"), available=Decimal("3.0"), reserved=Decimal("0.5")),
        ],
        fetched_at=now - timedelta(seconds=5),
        expires_at=now + expires_delta,
        ttl_seconds=60,
        source="kraken",
    )


@pytest.mark.asyncio
async def test_context_uses_adaptive_timeframes(db_session):
    now = datetime(2026, 2, 8, 12, 0, 0)

    async def active_snapshot():
        return _snapshot(now=now, expires_delta=timedelta(minutes=1))

    db_session.add(RiskSettings(current_risk_score=10.0, max_risk_score=80.0, updated_at=now))
    await db_session.commit()

    assembler = ChatContextAssembler(portfolio_fetcher=active_snapshot, now_provider=lambda: now)

    tactical = await assembler.build(db=db_session, prompt="Should I rotate my BTC position now?")
    day = await assembler.build(db=db_session, prompt="Show my performance and P&L today")
    week = await assembler.build(db=db_session, prompt="How did my week go?")

    assert tactical["timeframe_used"] == "session"
    assert day["timeframe_used"] == "24h"
    assert week["timeframe_used"] == "7d"
    assert tactical["baseline_comparison"]["baseline"] == "prior_session"
    assert day["baseline_comparison"]["baseline"] == "prior_day"


@pytest.mark.asyncio
async def test_context_flags_stale_when_portfolio_expired_and_risk_missing(db_session):
    now = datetime(2026, 2, 8, 12, 0, 0)

    async def expired_snapshot():
        return _snapshot(now=now, expires_delta=timedelta(seconds=-1))

    assembler = ChatContextAssembler(portfolio_fetcher=expired_snapshot, now_provider=lambda: now)
    payload = await assembler.build(db=db_session, prompt="What should I do next?")

    assert payload["stale_context"] is True
    assert "expired_portfolio_snapshot" in payload["refusal_reasons"]
    assert "missing_risk_reference_timestamp" in payload["refusal_reasons"]
    assert "risk.updated_at" in payload["missing_fields"]


@pytest.mark.asyncio
async def test_context_requires_trade_rationale_for_why_trade_prompts(db_session):
    now = datetime(2026, 2, 8, 12, 0, 0)

    async def active_snapshot():
        return _snapshot(now=now, expires_delta=timedelta(minutes=1))

    db_session.add(RiskSettings(current_risk_score=10.0, max_risk_score=80.0, updated_at=now))
    await db_session.flush()
    db_session.add(
        Trade(
            symbol="BTC/USD",
            side="buy",
            quantity=1.0,
            entry_price=50000.0,
            entry_time=now - timedelta(hours=1),
            is_manual=False,
            is_paper=True,
        )
    )
    await db_session.commit()

    assembler = ChatContextAssembler(portfolio_fetcher=active_snapshot, now_provider=lambda: now)

    no_trade_id = await assembler.build(db=db_session, prompt="Why did you make this trade?")
    missing_rationale = await assembler.build(db=db_session, prompt="Why did you make this trade 1?")

    assert no_trade_id["incomplete_context"] is True
    assert "trade_id" in no_trade_id["missing_fields"]
    assert "missing_trade_rationale_context" in no_trade_id["refusal_reasons"]

    assert missing_rationale["incomplete_context"] is True
    assert "trade_context.rationale" in missing_rationale["missing_fields"]
