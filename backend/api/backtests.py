"""Backtest management endpoints."""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from db.database import get_async_db, async_session_factory
from db.models import BacktestRun, Strategy, User
from core.exceptions import DatabaseException
from services.backtest_service import BacktestService

logger = logging.getLogger("cryptotrader.backtests")
router = APIRouter()

async def _run_backtest_task(backtest_id: int):
    """Background task to run the backtest."""
    async with async_session_factory() as session:
        service = BacktestService(session)
        await service.run_backtest(backtest_id)

class BacktestRequest(BaseModel):
    """Payload to trigger a new backtest."""
    strategy_id: int
    symbol: str = Field(..., min_length=1)
    start_date: datetime
    end_date: datetime
    initial_capital: float = Field(100000.0, gt=0)

class BacktestResponse(BaseModel):
    """Backtest summary response."""
    id: int
    strategy_id: int
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: Optional[float]
    total_pnl: Optional[float]
    max_drawdown: Optional[float]
    win_rate: Optional[float]
    total_trades: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

@router.post("/", response_model=BacktestResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_backtest(
    payload: BacktestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> BacktestResponse:
    """
    Trigger a new backtest simulation.
    Initially, this just creates the record. The actual simulation logic will follow.
    """
    try:
        # Verify strategy exists
        strategy = await db.get(Strategy, payload.strategy_id)
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )

        backtest = BacktestRun(
            strategy_id=payload.strategy_id,
            symbol=payload.symbol.upper(),
            start_date=payload.start_date,
            end_date=payload.end_date,
            initial_capital=payload.initial_capital,
            status="running" # We'll start it immediately in next tasks
        )
        db.add(backtest)
        await db.commit()
        await db.refresh(backtest)
        
        # Start background task
        import asyncio
        asyncio.create_task(_run_backtest_task(backtest.id))
        
        logger.info(
            "Backtest %s triggered for strategy %s on %s",
            backtest.id, payload.strategy_id, payload.symbol
        )
        
        return backtest
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to create backtest run", exc_info=True)
        raise DatabaseException(
            message="Unable to trigger backtest",
            details={"operation": "trigger_backtest"}
        ) from exc

@router.get("/{backtest_id}", response_model=BacktestResponse)
async def get_backtest(
    backtest_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> BacktestResponse:
    """Fetch status and results of a specific backtest."""
    try:
        backtest = await db.get(BacktestRun, backtest_id)
        if not backtest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Backtest not found"
            )
        return backtest
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.error("Failed to load backtest %s", backtest_id, exc_info=True)
        raise DatabaseException(
            message="Unable to load backtest",
            details={"backtest_id": backtest_id}
        ) from exc

@router.get("/strategy/{strategy_id}", response_model=List[BacktestResponse])
async def list_strategy_backtests(
    strategy_id: int,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> List[BacktestResponse]:
    """List recent backtests for a specific strategy."""
    try:
        stmt = (
            select(BacktestRun)
            .where(BacktestRun.strategy_id == strategy_id)
            .order_by(desc(BacktestRun.created_at))
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
    except SQLAlchemyError as exc:
        logger.error("Failed to list backtests for strategy %s", strategy_id, exc_info=True)
        raise DatabaseException(
            message="Unable to list backtests",
            details={"strategy_id": strategy_id}
        ) from exc
