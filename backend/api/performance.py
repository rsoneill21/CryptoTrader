from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional, AsyncIterator
from datetime import datetime, timedelta
from pydantic import BaseModel, ConfigDict
import json
import asyncio

from db.database import get_async_db
from db.models import PerformanceSnapshot, Trade
from core.exceptions import DatabaseException
from core.message_queue import message_queue, Channels

router = APIRouter()

# Pydantic models for response
class PerformanceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    total_equity: float
    cash_balance: float
    asset_value: float
    sharpe_ratio: Optional[float]
    sortino_ratio: Optional[float]
    volatility: Optional[float]
    max_drawdown: Optional[float]
    win_rate: Optional[float]
    alpha: Optional[float]
    timestamp: datetime

class PerformanceHistoryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    timestamp: datetime
    total_equity: float
    cash_balance: float
    asset_value: float
    sharpe_ratio: Optional[float]
    sortino_ratio: Optional[float]
    volatility: Optional[float]
    max_drawdown: Optional[float]
    alpha: Optional[float]

class PerformanceHistoryResponse(BaseModel):
    history: List[PerformanceHistoryPoint]

class TradeHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    symbol: str
    side: str
    entry_price: Optional[float]
    exit_price: Optional[float]
    quantity: float
    pnl: Optional[float]
    entry_time: Optional[datetime]
    exit_time: Optional[datetime]

class TradeHistoryResponse(BaseModel):
    trades: List[TradeHistoryItem]

@router.get("/summary", response_model=PerformanceSummary)
async def get_performance_summary(db: AsyncSession = Depends(get_async_db)):
    """Returns the latest calculated metrics from the most recent snapshot."""
    try:
        query = select(PerformanceSnapshot).order_by(desc(PerformanceSnapshot.timestamp)).limit(1)
        result = await db.execute(query)
        snapshot = result.scalar_one_or_none()
        
        if not snapshot:
            # Return empty summary if no snapshots exist
            return PerformanceSummary(
                total_equity=0.0,
                cash_balance=0.0,
                asset_value=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                volatility=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                alpha=0.0,
                timestamp=datetime.utcnow()
            )
            
        return snapshot
    except Exception as e:
        raise DatabaseException(f"Failed to fetch performance summary: {str(e)}")

@router.get("/history", response_model=PerformanceHistoryResponse)
async def get_performance_history(
    timeframe: str = Query("1w", pattern="^(1d|1w|1m|3m|all)$"),
    strategy_id: Optional[int] = Query(None),
    asset_pair: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db)
):
    """Returns time-series data (equity + metrics) filtered by timeframe and optionally strategy/asset."""
    try:
        now = datetime.utcnow()
        if timeframe == "1d":
            since = now - timedelta(days=1)
        elif timeframe == "1w":
            since = now - timedelta(days=7)
        elif timeframe == "1m":
            since = now - timedelta(days=30)
        elif timeframe == "3m":
            since = now - timedelta(days=90)
        else: # all
            since = datetime(2020, 1, 1)

        query = select(PerformanceSnapshot).where(PerformanceSnapshot.timestamp >= since)
        
        if strategy_id is not None:
            query = query.where(PerformanceSnapshot.strategy_id == strategy_id)
        if asset_pair is not None:
            query = query.where(PerformanceSnapshot.asset_pair == asset_pair)
            
        query = query.order_by(PerformanceSnapshot.timestamp)
        
        # If history > 30 days, we might want to filter to only daily anchors.
        # But for now we just return what's in the DB, assuming cleanup service
        # has already pruned high-resolution snapshots older than 30 days.
        
        result = await db.execute(query)
        history = result.scalars().all()
        return {"history": history}
    except Exception as e:
        raise DatabaseException(f"Failed to fetch performance history: {str(e)}")

@router.get("/trades", response_model=TradeHistoryResponse)
async def get_trade_history(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db)
):
    """Returns a list of recent closed trades."""
    try:
        query = select(Trade).where(Trade.exit_time != None).order_by(desc(Trade.exit_time)).limit(limit)
        result = await db.execute(query)
        trades = result.scalars().all()
        return {"trades": trades}
    except Exception as e:
        raise DatabaseException(f"Failed to fetch trade history: {str(e)}")

@router.get("/stream")
async def stream_performance():
    """SSE endpoint for real-time performance updates."""
    async def event_generator() -> AsyncIterator[str]:
        queue = asyncio.Queue()

        async def callback(message: dict):
            await queue.put(message)

        # Subscribe to performance channel
        await message_queue.subscribe(Channels.PERFORMANCE, callback)

        try:
            while True:
                # Wait for a message from the queue
                message = await queue.get()
                yield f"data: {json.dumps(message)}\n\n"
        except asyncio.CancelledError:
            # Unsubscribe on disconnect
            await message_queue.unsubscribe(Channels.PERFORMANCE)
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
