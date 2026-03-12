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

async def check_strategy_health(
    db: AsyncSession, 
    strategy_id: int, 
    lookback_trades: int = 20,
    win_rate_threshold: float = 0.40,
    critical_win_rate: float = 0.30,
    drawdown_threshold: float = 15.0 # percentage
) -> Dict[str, Any]:
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
                "max_drawdown_pct": 0.0,
                "total_pnl": 0.0
            }
        }
        
    total_trades = len(trades)
    winning_trades = len([t for t in trades if (t.pnl or 0) > 0])
    win_rate = winning_trades / total_trades if total_trades > 0 else 0
    total_pnl = sum(t.pnl or 0 for t in trades)
    
    # Calculate drawdown from these recent trades
    # We'll assume a nominal starting balance if we don't have one, 
    # to calculate a meaningful percentage.
    nominal_balance = 10000.0 
    balance = 0.0
    equity_curve = [0.0]
    for t in reversed(trades): # process in chronological order
        balance += (t.pnl or 0)
        equity_curve.append(balance)
        
    max_equity_peak = 0.0
    max_drawdown = 0.0
    for equity in equity_curve:
        if equity > max_equity_peak:
            max_equity_peak = equity
        drawdown = max_equity_peak - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            
    # Drawdown percentage relative to nominal balance + peak
    drawdown_pct = (max_drawdown / (nominal_balance + max_equity_peak)) * 100
    
    status = HealthStatus.HEALTHY
    
    # Check Win Rate
    if win_rate < critical_win_rate:
        status = HealthStatus.CRITICAL
    elif win_rate < win_rate_threshold:
        status = HealthStatus.DEGRADED
        
    # Check Drawdown (if already critical, stay critical)
    if status != HealthStatus.CRITICAL:
        if drawdown_pct > drawdown_threshold * 1.5:
            status = HealthStatus.CRITICAL
        elif drawdown_pct > drawdown_threshold:
            status = HealthStatus.DEGRADED
        
    return {
        "status": status,
        "metrics": {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": drawdown_pct,
            "total_pnl": total_pnl
        }
    }

async def monitor_strategies(db: AsyncSession) -> Dict[str, Any]:
    """
    Scan all active strategies, check health, and trigger AI interventions.
    """
    # Iterate all live/paper strategies
    query = select(Strategy).where(Strategy.status.in_(["live", "paper"]))
    result = await db.execute(query)
    strategies = result.scalars().all()
    
    monitored_count = 0
    degraded_count = 0
    
    for strategy in strategies:
        monitored_count += 1
        health_result = await check_strategy_health(db, strategy.id)
        status = health_result["status"]
        
        # Update strategy health status in DB
        strategy.health_status = status.value
        
        if status in [HealthStatus.DEGRADED, HealthStatus.CRITICAL]:
            degraded_count += 1
            # 1. Create System Alert
            alert = Alert(
                type="strategy_health",
                title=f"Strategy {strategy.name} is {status.value}",
                message=f"Performance degradation detected for {strategy.name}: Win Rate {health_result['metrics']['win_rate']:.2%}",
                severity="warning" if status == HealthStatus.DEGRADED else "critical",
                related_strategy_id=strategy.id
            )
            db.add(alert)
            
            # 2. Call AI for suggestions
            try:
                suggestions = await strategy_ai_service.analyze_degradation(
                    strategy.id,
                    strategy.name,
                    health_result["metrics"]
                )
                # 3. Save suggestion
                strategy.pending_adjustment_json = suggestions
            except Exception:
                logger.exception("AI degradation analysis failed for strategy %s", strategy.id)
    
    await db.commit()
    return {
        "strategies_monitored": monitored_count,
        "degraded_identified": degraded_count
    }
