"""Service for monitoring and managing strategy health."""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Strategy, Trade, StrategyPerformance, Alert
from core.paper_trading import PaperStrategyPerformanceSummary
from services.strategy_ai import strategy_ai_service, StrategyPromotionContext

logger = logging.getLogger(__name__)

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"

async def check_strategy_health(db: AsyncSession, strategy_id: int, lookback_trades: int = 20) -> Dict[str, Any]:
    """
    Evaluate strategy health based on recent performance.
    Returns a dict with status and performance summary.
    """
    # Load recent trades for this strategy
    query = (
        select(Trade)
        .where(Trade.strategy_id == strategy_id)
        .where(Trade.exit_time.is_not(None))
        .order_by(desc(Trade.exit_time))
        .limit(lookback_trades)
    )
    result = await db.execute(query)
    trades = list(result.scalars().all())
    
    if not trades:
        return {
            "status": HealthStatus.HEALTHY,
            "metrics": {
                "total_trades": 0,
                "win_rate": 0.0,
                "max_drawdown": 0.0,
                "total_pnl": 0.0
            }
        }
        
    total_trades = len(trades)
    winning_trades = len([t for t in trades if (t.pnl or 0) > 0])
    win_rate = winning_trades / total_trades if total_trades > 0 else 0
    total_pnl = sum(t.pnl or 0 for t in trades)
    
    # Calculate drawdown from these recent trades
    balance = 0.0
    equity_curve = [0.0]
    for t in reversed(trades): # process in chronological order
        balance += (t.pnl or 0)
        equity_curve.append(balance)
        
    max_equity = 0.0
    max_drawdown = 0.0
    for equity in equity_curve:
        if equity > max_equity:
            max_equity = equity
        drawdown = max_equity - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            
    # Thresholds (Win Rate < 40%, Drawdown > 15% - assuming some base capital or relative drawdown)
    # Since we don't have capital here, we'll use win rate and maybe a PnL threshold.
    # For the purpose of the task, we'll focus on Win Rate as a primary health indicator.
    
    status = HealthStatus.HEALTHY
    if win_rate < 0.30:
        status = HealthStatus.CRITICAL
    elif win_rate < 0.40:
        status = HealthStatus.DEGRADED
        
    return {
        "status": status,
        "metrics": {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "max_drawdown": max_drawdown,
            "total_pnl": total_pnl
        }
    }
