# Context: Strategy Backtesting (Phase 5)

## Overview
Phase 5 introduces the ability for users to validate their trading strategies against historical market data. This is a critical step before deploying a strategy to live (or paper) trading.

## Requirements Reference
- **BACK-01**: User can select date range and symbol for backtest.
- **BACK-02**: Backtest runs strategy rules against historical candles.
- **BACK-03**: Results show total trades, win rate, P&L, max drawdown.
- **BACK-04**: Backtest respects configured risk limits.
- **BACK-05**: Results stored in database for comparison.

## Key Files & Services
- `backend/db/models.py`: Needs `BacktestRun` model.
- `backend/services/backtest_service.py`: New service for executing simulations.
- `backend/api/backtests.py`: New API endpoints for backtesting.
- `frontend/src/pages/Backtesting.js`: New UI page for configuring and viewing backtests.

## Technical Decisions
- **Rule Engine**: We will start with a simple rule engine that evaluates conditions based on indicators already supported by `backend/core/indicators.py` and `backend/core/patterns.py`.
- **Concurrency**: Backtests will be executed as background tasks (using Celery if available, or simple `asyncio.create_task`) to avoid blocking the main thread.
- **Data Source**: Historical data will be sourced from the `market_data` table. If data is missing for the requested range, the backtest will inform the user.

## Current Limitations
- Historical data depth is limited by what has been collected in the `market_data` table.
- Complex multi-timeframe strategies are not yet supported.
- Risk limits in backtesting will be simulated locally.
