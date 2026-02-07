"""Service for executing historical strategy backtests."""

import logging
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models import BacktestRun, MarketData, Strategy
from core.paper_trading import PaperTradingEngine, PaperTradeSignal, TradeIntent, TradeSide
from core.strategy_evaluator import StrategyEvaluator
from services.market_data import market_data_service

logger = logging.getLogger(__name__)

class BacktestService:
    """Executes strategy simulations against historical market data."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    async def run_backtest(self, backtest_id: int) -> None:
        """Execute a backtest run by ID."""
        backtest = await self.db.get(BacktestRun, backtest_id)
        if not backtest:
            logger.error("Backtest %s not found", backtest_id)
            return

        try:
            strategy = await self.db.get(Strategy, backtest.strategy_id)
            if not strategy:
                raise ValueError(f"Strategy {backtest.strategy_id} not found")

            # 1. Fetch historical data
            df = await self._fetch_historical_data(
                backtest.symbol, backtest.start_date, backtest.end_date
            )
            if df.empty:
                raise ValueError(f"No market data found for {backtest.symbol} in range")

            # 2. Evaluate strategy signals
            evaluator = StrategyEvaluator(strategy.rules_json)
            eval_df = evaluator.evaluate(df)

            # 3. Simulate trading
            results = await self._simulate(eval_df, backtest)

            # 4. Save results
            backtest.status = "completed"
            backtest.final_capital = results["final_capital"]
            backtest.total_pnl = results["total_pnl"]
            backtest.max_drawdown = results["max_drawdown"]
            backtest.win_rate = results["win_rate"]
            backtest.total_trades = results["total_trades"]
            backtest.results_json = results["history"]
            
            await self.db.commit()
            logger.info("Backtest %s completed successfully", backtest_id)

        except Exception as exc:
            logger.exception("Backtest %s failed: %s", backtest_id, exc)
            backtest.status = "failed"
            backtest.error_message = str(exc)
            await self.db.commit()

    async def _fetch_historical_data(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        """Fetch and prepare historical data from DB."""
        stmt = (
            select(MarketData)
            .where(
                MarketData.symbol == symbol,
                MarketData.timestamp >= start_date,
                MarketData.timestamp <= end_date
            )
            .order_by(MarketData.timestamp.asc())
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        
        if not rows:
            return pd.DataFrame()
            
        data = [
            {
                "timestamp": r.timestamp,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume
            }
            for r in rows
        ]
        return pd.DataFrame(data)

    async def _simulate(self, df: pd.DataFrame, backtest: BacktestRun) -> Dict[str, Any]:
        """Run the simulation loop."""
        engine = PaperTradingEngine(starting_cash=backtest.initial_capital)
        engine._persistence_enabled = False # Don't save backtest trades to main trade table
        
        trade_history = []
        equity_curve = [backtest.initial_capital]
        
        # We iterate row by row to simulate time
        for index, row in df.iterrows():
            timestamp = row['timestamp']
            price = float(row['close'])
            
            # Update engine price
            await engine.update_market_price(backtest.symbol, price)
            
            # Check for signals
            if row.get('entry_signal'):
                # Check if already in position (simplified: engine handles multiple positions if we want)
                # For now, let's assume we want to enter if signals say so.
                # In a real backtest, we'd check current exposure.
                
                # Check available cash
                snapshot = await engine.snapshot()
                if snapshot.cash > price:
                    # Default quantity calculation (e.g. 10% of equity)
                    qty = (snapshot.equity * 0.1) / price
                    if qty > 0:
                        entry_signal = PaperTradeSignal(
                            symbol=backtest.symbol,
                            intent=TradeIntent.ENTRY,
                            side=TradeSide.BUY,
                            quantity=qty,
                            price=price,
                            timestamp=timestamp,
                            strategy_id=backtest.strategy_id
                        )
                        await engine.execute_signal(entry_signal)
            
            if row.get('exit_signal'):
                snapshot = await engine.snapshot()
                # Find positions for this symbol
                positions = [p for p in snapshot.open_positions if p.symbol == backtest.symbol]
                for pos in positions:
                    exit_signal = PaperTradeSignal(
                        symbol=backtest.symbol,
                        intent=TradeIntent.EXIT,
                        quantity=pos.quantity,
                        price=price,
                        timestamp=timestamp,
                        strategy_id=backtest.strategy_id
                    )
                    results = await engine.execute_signal(exit_signal)
                    for res in results:
                        trade_data = res.model_dump()
                        # Convert datetime to string for JSON serialization
                        if isinstance(trade_data.get('entry_time'), datetime):
                            trade_data['entry_time'] = trade_data['entry_time'].isoformat()
                        if isinstance(trade_data.get('exit_time'), datetime):
                            trade_data['exit_time'] = trade_data['exit_time'].isoformat()
                        trade_history.append(trade_data)
            
            # Record equity
            snap = await engine.snapshot()
            equity_curve.append(float(snap.equity))

        # Final snapshot
        final_snap = await engine.snapshot()
        
        # Calculate metrics
        total_trades = len(trade_history)
        winning_trades = sum(1 for t in trade_history if float(t.get('pnl', 0)) > 0)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        
        # Max drawdown
        max_dd = 0.0
        peak = equity_curve[0]
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
                
        return {
            "final_capital": float(final_snap.equity),
            "total_pnl": float(final_snap.equity - backtest.initial_capital),
            "max_drawdown": float(max_dd),
            "win_rate": float(win_rate),
            "total_trades": int(total_trades),
            "history": {
                "trades": trade_history,
                "equity_curve": [float(v) for v in equity_curve[::max(1, len(equity_curve)//100)]] # Sample for UI
            }
        }
