# Research: Strategy Backtesting (Phase 5)

## Objective
Users can test trading strategies against historical data before live deployment.

## Existing Components
- **`MarketDataService`**: Fetches and stores OHLCV candles. Can be used to retrieve historical data for backtesting.
- **`PaperTradingEngine`**: Simulates trade execution and tracks positions/P&L. Can be reused or adapted for backtesting logic.
- **`StrategyOptimizerAgent`**: Already implements a basic simulation loop (`_simulate_candidate`) which iterates through historical price tuples and evaluates a hardcoded momentum strategy.
- **`Strategy` Model**: Stores strategy rules as JSON.
- **`StrategyPerformance` Model**: Stores performance metrics like win rate, total P&L, etc.

## Proposed Architecture

### 1. Backtesting Engine
A specialized service (e.g., `BacktestService`) that:
- Takes a `strategy_id`, `symbol`, `start_date`, `end_date`, and `initial_capital`.
- Loads historical candles from `MarketData` table.
- Evaluates strategy rules for each candle.
- Uses a clean instance of `PaperTradingEngine` (persistence disabled) to simulate trades.
- Aggregates results into performance metrics.

### 2. Strategy Rule Evaluation
Currently, strategy rules are stored as JSON in the `Strategy` model. I need a way to interpret these rules.
The rules might include:
- Technical indicators (RSI, MA cross, etc.)
- Candlestick patterns (via `core.patterns`)
- Custom logic/thresholds.

I should probably implement a `StrategyEvaluator` that can parse these JSON rules and return a buy/sell/hold signal for a given data point.

### 3. Data Models
I need a `BacktestRun` model to track individual backtest attempts.
```python
class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"))
    symbol = Column(String(50))
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    initial_capital = Column(Float)
    final_capital = Column(Float)
    total_pnl = Column(Float)
    max_drawdown = Column(Float)
    win_rate = Column(Float)
    total_trades = Column(Integer)
    status = Column(String(20)) # running, completed, failed
    results_json = Column(JSON) # Detailed trade-by-trade logs
    created_at = Column(DateTime, server_default=func.now())
```

### 4. API Endpoints
- `POST /api/strategies/{strategy_id}/backtest`: Start a new backtest.
- `GET /api/backtests/{backtest_id}`: Get backtest results.
- `GET /api/strategies/{strategy_id}/backtests`: List backtests for a strategy.

### 5. UI Requirements
- Backtest configuration form (Symbol, Date Range, Initial Capital).
- Progress indicator for running backtests.
- Results dashboard (Equity curve, Trade list, Performance metrics).

## Implementation Challenges
- **Large Dataset Performance**: Backtesting over long periods with 1m candles can be slow. May need to fetch data in chunks or optimize rule evaluation.
- **Rule Flexibility**: The current system has no formal "Rule Engine". I'll need to define a schema for `rules_json` that can handle common technical indicators.
- **Lookahead Bias**: Ensuring the strategy only uses data available at the timestamp being evaluated.

## Next Steps
1. Define the `BacktestRun` database model.
2. Create a migration for the new model.
3. Implement `BacktestService` with support for basic rule evaluation.
4. Add API endpoints for triggering and viewing backtests.
5. Build the Backtesting UI component.
