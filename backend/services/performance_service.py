import logging
import pandas as pd
import numpy as np
import quantstats as qs
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc, delete, func
from decimal import Decimal

from db.database import AsyncSessionLocal
from db.models import PerformanceSnapshot, Trade, MarketData
from services.portfolio import portfolio_service
from agents.market_analyst import market_analyst_agent
from core.message_queue import message_queue, Channels

logger = logging.getLogger(__name__)

class PerformanceService:
    """Service for capturing and managing portfolio performance snapshots."""

    async def capture_snapshot(self, strategy_id: Optional[int] = None) -> Optional[PerformanceSnapshot]:
        """
        Capture a snapshot of the current portfolio performance and persist it.
        
        Calculates metrics like Sharpe, Sortino, Max Drawdown, Win Rate, and Alpha.
        """
        try:
            # 1. Fetch balances
            from services.kraken import kraken_service
            from services.paper_trading_service import paper_trading_engine
            
            cash_balance = 0.0
            asset_value = 0.0
            total_equity = 0.0
            prices = {}

            if kraken_service.is_authenticated:
                # Live mode
                portfolio = await portfolio_service.get_snapshot(force_refresh=True)
                for holding in portfolio.holdings:
                    # Kraken uses ZUSD for USD in some contexts, or just USD
                    if holding.asset in ["USD", "ZUSD", "USDT", "USDC"]:
                        cash_balance += float(holding.total)
                    else:
                        # Get price for asset
                        asset = holding.asset
                        if asset == "XXBT": asset = "BTC"
                        if asset == "XETH": asset = "ETH"
                        
                        symbol = f"{asset}/USD"
                        summary = await market_analyst_agent.get_indicator_summary(symbol)
                        price = summary.get("last_price")
                        
                        if price is None:
                            try:
                                price_info = await kraken_service.get_ticker(symbol)
                                price = float(price_info.last)
                            except Exception:
                                price = 0.0
                        else:
                            price = float(price)
                        
                        prices[symbol] = price
                        asset_value += float(holding.total) * price
                total_equity = cash_balance + asset_value
            else:
                # Paper mode - use PaperTradingEngine state
                snapshot = await paper_trading_engine.snapshot()
                total_equity = snapshot.equity
                cash_balance = snapshot.cash # Starting cash + realized P&L
                
                # Calculate asset value from open positions
                asset_value = 0.0
                for pos in snapshot.open_positions:
                    price = pos.last_price or pos.entry_price
                    asset_value += pos.quantity * price
                    prices[pos.symbol] = price
            
            # 2. Fetch history for metrics calculation
            async with AsyncSessionLocal() as session:
                # Get last 100 snapshots to calculate metrics
                query = select(PerformanceSnapshot).order_by(desc(PerformanceSnapshot.timestamp)).limit(100)
                result = await session.execute(query)
                history = list(result.scalars().all())
                history.reverse() # Chronological order
                
                # Append current equity to history for calculation
                equity_history = [float(h.total_equity) for h in history] + [total_equity]
                timestamps = [h.timestamp for h in history] + [datetime.utcnow()]
                
                # Default metrics
                sharpe = 0.0
                sortino = 0.0
                volatility = 0.0
                max_drawdown = 0.0
                win_rate = 0.0
                alpha = 0.0
                
                if len(equity_history) > 2:
                    # Create a series of returns
                    # Quantstats works best with daily data, but we use what we have
                    returns = pd.Series(equity_history, index=timestamps).pct_change().dropna()
                    
                    if not returns.empty and returns.std() > 0:
                        try:
                            sharpe = float(qs.stats.sharpe(returns))
                            sortino = float(qs.stats.sortino(returns))
                            volatility = float(qs.stats.volatility(returns))
                            max_drawdown = float(qs.stats.max_drawdown(returns))
                        except Exception as e:
                            logger.warning(f"Error calculating quantstats: {e}")

                    # Win rate from trades
                    trade_query = select(Trade).where(Trade.exit_time != None)
                    if strategy_id:
                        trade_query = trade_query.where(Trade.strategy_id == strategy_id)
                    trade_result = await session.execute(trade_query)
                    trades = trade_result.scalars().all()
                    if trades:
                        wins = len([t for t in trades if (t.pnl or 0) > 0])
                        win_rate = wins / len(trades)
                    
                    # Alpha (Active Return - Benchmark Return) relative to BTC/USD
                    alpha = await self._calculate_alpha(session, returns, timestamps)

                # 3. Persist snapshot
                snapshot = PerformanceSnapshot(
                    total_equity=total_equity,
                    cash_balance=cash_balance,
                    asset_value=asset_value,
                    strategy_id=strategy_id,
                    metadata_json={"prices": prices},
                    sharpe_ratio=self._sanitize_metric(sharpe),
                    sortino_ratio=self._sanitize_metric(sortino),
                    volatility=self._sanitize_metric(volatility),
                    max_drawdown=self._sanitize_metric(max_drawdown),
                    win_rate=win_rate,
                    alpha=self._sanitize_metric(alpha),
                    timestamp=datetime.utcnow()
                )
                session.add(snapshot)
                await session.commit()
                await session.refresh(snapshot)
                
                # Publish snapshot to SSE channel
                try:
                    await message_queue.publish(Channels.PERFORMANCE, {
                        "total_equity": float(snapshot.total_equity),
                        "cash_balance": float(snapshot.cash_balance),
                        "asset_value": float(snapshot.asset_value),
                        "sharpe_ratio": float(snapshot.sharpe_ratio or 0),
                        "sortino_ratio": float(snapshot.sortino_ratio or 0),
                        "volatility": float(snapshot.volatility or 0),
                        "max_drawdown": float(snapshot.max_drawdown or 0),
                        "win_rate": float(snapshot.win_rate or 0),
                        "alpha": float(snapshot.alpha or 0),
                        "timestamp": snapshot.timestamp.isoformat()
                    })
                except Exception as mq_err:
                    logger.warning(f"Failed to publish performance snapshot to MQ: {mq_err}")

                logger.info(f"Captured performance snapshot: equity={total_equity:.2f}, sharpe={sharpe:.2f}")
                return snapshot
                
        except Exception as e:
            logger.error(f"Failed to capture performance snapshot: {e}", exc_info=True)
            return None

    def _sanitize_metric(self, value: float) -> float:
        """Ensure metric is a valid float for the database."""
        if np.isnan(value) or np.isinf(value):
            return 0.0
        return float(value)

    async def _calculate_alpha(self, session, portfolio_returns: pd.Series, timestamps: List[datetime]) -> float:
        """Calculate Alpha relative to BTC/USD benchmark."""
        try:
            if portfolio_returns.empty:
                return 0.0
            
            start_time = timestamps[0]
            end_time = timestamps[-1]
            
            # Get BTC price near start_time
            start_price_query = select(MarketData.close).where(
                MarketData.symbol == "BTC/USD",
                MarketData.timestamp <= start_time
            ).order_by(desc(MarketData.timestamp)).limit(1)
            
            # Get BTC price near end_time
            end_price_query = select(MarketData.close).where(
                MarketData.symbol == "BTC/USD",
                MarketData.timestamp <= end_time
            ).order_by(desc(MarketData.timestamp)).limit(1)
            
            start_price_res = await session.execute(start_price_query)
            end_price_res = await session.execute(end_price_query)
            
            start_price = start_price_res.scalar_one_or_none()
            end_price = end_price_res.scalar_one_or_none()
            
            # Fallback if MarketData is empty: use first/last from MarketAnalyst if available
            if start_price is None or end_price is None:
                summary = await market_analyst_agent.get_indicator_summary("BTC/USD")
                end_price = summary.get("last_price")
                # We don't have a good way to get start_price if MarketData is empty
                # For now, just return 0 if we can't get both
                if start_price is None or end_price is None:
                    return 0.0

            start_price = float(start_price)
            end_price = float(end_price)
            
            if start_price > 0:
                btc_return = (end_price - start_price) / start_price
                portfolio_total_return = (portfolio_returns + 1).prod() - 1
                return float(portfolio_total_return - btc_return)
        except Exception as e:
            logger.warning(f"Alpha calculation failed: {e}")
            
        return 0.0

    async def cleanup_old_snapshots(self):
        """
        Delete snapshots older than 30 days EXCEPT for the first snapshot of each day.
        
        Tiered retention: 
        - < 30 days: All snapshots (hourly/trade-based)
        - > 30 days: Daily 'closing' snapshot only
        """
        try:
            cutoff = datetime.utcnow() - timedelta(days=30)
            
            async with AsyncSessionLocal() as session:
                # We want to find snapshots older than 30 days that ARE NOT the first of their day
                # In SQLite, we can use strftime('%Y-%m-%d', timestamp)
                
                # Subquery to find the minimum ID for each day for snapshots older than cutoff
                # This works for daily 'anchor' points
                daily_anchors_subquery = select(
                    func.min(PerformanceSnapshot.id)
                ).where(
                    PerformanceSnapshot.timestamp < cutoff
                ).group_by(
                    func.strftime('%Y-%m-%d', PerformanceSnapshot.timestamp)
                )
                
                # Delete all snapshots older than cutoff that are not in the daily anchors list
                delete_query = delete(PerformanceSnapshot).where(
                    PerformanceSnapshot.timestamp < cutoff,
                    PerformanceSnapshot.id.not_in(daily_anchors_subquery)
                )
                
                result = await session.execute(delete_query)
                await session.commit()
                
                logger.info(f"Cleaned up {result.rowcount} old performance snapshots")
                return result.rowcount
        except Exception as e:
            logger.error(f"Failed to cleanup old snapshots: {e}", exc_info=True)
            return 0

performance_service = PerformanceService()
