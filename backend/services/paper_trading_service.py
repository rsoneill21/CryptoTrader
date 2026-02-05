"""
Global paper trading engine instance with state persistence.
"""

import asyncio
import logging

from core.paper_trading import PaperTradingEngine
from db.database import SessionLocal, AsyncSessionLocal
from services.paper_trading_state import PaperTradingStateService

logger = logging.getLogger(__name__)

# Create a singleton instance of the paper trading engine
paper_trading_engine = PaperTradingEngine(
    db_factory=SessionLocal,
    async_session_factory=AsyncSessionLocal,
    state_service=PaperTradingStateService()
)


async def initialize_paper_trading_engine() -> None:
    """
    Initialize the paper trading engine by loading persisted state.

    This should be called on application startup.
    """
    logger.info("Initializing paper trading engine...")
    loaded = await paper_trading_engine.load_state_from_db()
    if loaded:
        logger.info("Paper trading state loaded from database")
    else:
        logger.info("Starting with fresh paper trading state")


async def shutdown_paper_trading_engine() -> None:
    """
    Shutdown the paper trading engine by persisting final state.

    This should be called on application shutdown.
    """
    logger.info("Shutting down paper trading engine...")
    await paper_trading_engine.persist_state()
    logger.info("Paper trading state persisted")


# Expose initialization and shutdown hooks
__all__ = [
    "paper_trading_engine",
    "initialize_paper_trading_engine",
    "shutdown_paper_trading_engine"
]
