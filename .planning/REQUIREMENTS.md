# Requirements: CryptoTrader

**Defined:** 2026-02-04
**Core Value:** AI autonomously makes profitable trading decisions without constant human intervention

## v1 Requirements

Requirements for initial release. Paper trading only — no real money until validated.

### Infrastructure Fixes (INFRA)

- [ ] **INFRA-01**: Paper trading state persists across server restarts
- [ ] **INFRA-02**: Rate limiter fails closed on auth/sensitive endpoints when Redis is down
- [ ] **INFRA-03**: Async database queries in async endpoints (no event loop blocking)
- [ ] **INFRA-04**: Bare exception handlers replaced with specific exceptions and logging
- [ ] **INFRA-05**: Database indexes on frequently queried columns (user_id, timestamps, strategy_id)
- [ ] **INFRA-06**: Pagination on list endpoints (trades, strategies, alerts)

### Autonomous Trading Loop (LOOP)

- [ ] **LOOP-01**: Agent Manager starts all agents on application startup via FastAPI lifespan
- [ ] **LOOP-02**: Agents run continuously on configurable schedule (sub-minute granularity)
- [ ] **LOOP-03**: Market data streams from Kraken WebSocket into Market Analyst agent in real-time
- [ ] **LOOP-04**: Market Analyst publishes insights to message queue for other agents
- [ ] **LOOP-05**: Orchestrator evaluates insights against active strategies and generates trade signals
- [ ] **LOOP-06**: Trade Executor receives signals and places paper orders
- [ ] **LOOP-07**: Agents gracefully shut down on application exit
- [ ] **LOOP-08**: Agent execution loop recovers from individual agent failures without crashing

### Risk Management (RISK)

- [ ] **RISK-01**: Maximum position size enforced (configurable % of capital per trade)
- [ ] **RISK-02**: Stop-loss automatically placed on every position
- [ ] **RISK-03**: Daily loss limit halts all trading for the day when breached
- [ ] **RISK-04**: Maximum portfolio exposure limit per asset
- [ ] **RISK-05**: Trade frequency limit prevents over-trading (max trades per hour/day)
- [ ] **RISK-06**: Minimum liquidity check before entering a position
- [ ] **RISK-07**: API rate limits respected to avoid Kraken bans

### Position Management (POS)

- [ ] **POS-01**: Open new positions with market orders
- [ ] **POS-02**: Open new positions with limit orders
- [ ] **POS-03**: Close positions (take-profit and stop-loss exits)
- [ ] **POS-04**: Position sizing calculated from risk parameters and account balance
- [ ] **POS-05**: Partial fills tracked and reconciled
- [ ] **POS-06**: Open positions displayed with real-time P&L
- [ ] **POS-07**: Failed orders retried or alerted

### Performance Tracking (PERF)

- [ ] **PERF-01**: Realized and unrealized P&L calculated accurately
- [ ] **PERF-02**: Win rate tracked (percentage of profitable trades)
- [ ] **PERF-03**: Return on investment tracked over time
- [ ] **PERF-04**: Maximum drawdown from peak tracked
- [ ] **PERF-05**: Complete trade history browsable in UI
- [ ] **PERF-06**: Performance attributed per strategy

### Monitoring & Alerting (MON)

- [ ] **MON-01**: System health dashboard shows agent status, API connectivity, queue health
- [ ] **MON-02**: Alert generated on every trade entry and exit
- [ ] **MON-03**: Alert generated when risk limits are approached or breached
- [ ] **MON-04**: Alert generated on system errors (agent crash, API failure, DB issues)
- [ ] **MON-05**: Daily performance summary generated automatically
- [ ] **MON-06**: Exchange connection status displayed in UI

### Safety Features (SAFE)

- [ ] **SAFE-01**: Emergency stop button halts all trading immediately
- [ ] **SAFE-02**: Manual override disables autonomous trading
- [ ] **SAFE-03**: Paper trading simulates orders with realistic fills, fees, and slippage
- [ ] **SAFE-04**: Dry-run mode logs signals without executing any orders
- [ ] **SAFE-05**: First live trade requires explicit user confirmation
- [ ] **SAFE-06**: Balance validated before every order placement

### Signal Generation (SIG)

- [ ] **SIG-01**: Technical indicators (RSI, MACD, Bollinger, MA) generate buy/sell signals
- [ ] **SIG-02**: Pattern detection identifies chart patterns as signals
- [ ] **SIG-03**: Multi-agent consensus — multiple agents vote on trade decisions
- [ ] **SIG-04**: Orchestrator weighs agent confidence scores to make final decision
- [ ] **SIG-05**: Sentiment agent ingests social media sentiment as signal input
- [ ] **SIG-06**: News feed data factored into trading decisions

### Advanced Risk (ARISK)

- [ ] **ARISK-01**: Dynamic position sizing adjusts based on signal confidence and volatility
- [ ] **ARISK-02**: Adaptive trailing stop-losses adjust to market volatility (ATR-based)

### Backtesting (BACK)

- [ ] **BACK-01**: Historical price data stored for backtesting
- [ ] **BACK-02**: Strategy backtested against historical data with realistic fills
- [ ] **BACK-03**: Backtest results show P&L, win rate, drawdown, Sharpe ratio
- [ ] **BACK-04**: Strategy comparison with statistical significance testing

### Tax Reporting (TAX)

- [ ] **TAX-01**: Trade data exportable in tax-ready format (CSV with cost basis, proceeds, gain/loss)

### Exchange Abstraction (EXCH)

- [ ] **EXCH-01**: Exchange interface abstracted behind common contract
- [ ] **EXCH-02**: Kraken implementation fulfills exchange interface
- [ ] **EXCH-03**: Paper trading engine implements same exchange interface

### Dashboard (DASH)

- [ ] **DASH-01**: Dashboard shows real portfolio value and positions (not placeholder data)
- [ ] **DASH-02**: Dashboard shows AI agent status (running/stopped/error)
- [ ] **DASH-03**: Dashboard shows recent trades and P&L
- [ ] **DASH-04**: Live trading page shows real-time chart with actual market data
- [ ] **DASH-05**: AI chat references current positions, market state, and agent reasoning
- [ ] **DASH-06**: Settings page allows configuring autonomy level, risk parameters, and signal weights

## v2 Requirements

Deferred to future release. Not in current roadmap.

### Advanced Signals

- **SIG-07**: Order book depth analysis for whale detection
- **SIG-08**: Cross-market correlation analysis (BTC leads alts)
- **SIG-09**: Adaptive signal thresholds that learn over time
- **SIG-10**: Custom user-defined indicators

### Intelligent Risk

- **ARISK-03**: Portfolio rebalancing to maintain target allocation
- **ARISK-04**: Volatility-adjusted limits (tighter in volatile markets)
- **ARISK-05**: Correlation-aware position sizing
- **ARISK-06**: Time-of-day risk adjustments

### Advanced Backtesting

- **BACK-05**: Walk-forward analysis (rolling optimization windows)
- **BACK-06**: Monte Carlo simulation for strategy stress testing
- **BACK-07**: Automated parameter optimization (grid search / genetic)
- **BACK-08**: Slippage modeling calibrated to exchange data

### Learning & Adaptation

- **LEARN-01**: Performance feedback loop (agents learn from past trades)
- **LEARN-02**: Market regime detection (trending vs ranging)
- **LEARN-03**: Auto-strategy switching based on market conditions
- **LEARN-04**: Anomaly detection (halt trading in unusual conditions)
- **LEARN-05**: Self-improvement over time

### Advanced Monitoring

- **ADVMON-01**: Trade replay (visualize past trades on charts)
- **ADVMON-02**: Prediction tracking (were signals correct?)
- **ADVMON-03**: Comparative benchmarking (bot vs buy-and-hold)

### Integration

- **INT-01**: Multi-exchange support (Coinbase, Binance, etc.)
- **INT-02**: Stock/equity broker integration
- **INT-03**: Webhook notifications (Slack, Discord, Telegram)
- **INT-04**: External signal integration (TradingView, etc.)
- **INT-05**: Portfolio synchronization (import existing holdings)
- **INT-06**: API access for programmatic control

## Out of Scope

| Feature | Reason |
|---------|--------|
| Live trading with real money | Paper trading only until AI proves profitable |
| Guaranteed returns / promises | Unethical and impossible |
| Leverage trading | Magnifies losses; spot trading only for v1 |
| High-frequency trading | Latency requirements beyond scope; focus on signal quality |
| Social / copy trading | Legal liability; single-user tool |
| Grid/DCA without stop-loss | Infinite loss potential |
| Automatic withdrawals/deposits | Security risk; user manages funds manually |
| Mobile native app | Responsive web for monitoring; desktop for control |
| Multi-user deployment | Single user for v1 |
| Set-and-forget operation | Requires active monitoring; alerts mandatory |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Pending |
| INFRA-02 | Phase 1 | Pending |
| INFRA-03 | Phase 1 | Pending |
| INFRA-04 | Phase 1 | Pending |
| INFRA-05 | Phase 1 | Pending |
| INFRA-06 | Phase 1 | Pending |
| LOOP-01 | Phase 2 | Pending |
| LOOP-02 | Phase 2 | Pending |
| LOOP-03 | Phase 2 | Pending |
| LOOP-04 | Phase 2 | Pending |
| LOOP-05 | Phase 2 | Pending |
| LOOP-06 | Phase 2 | Pending |
| LOOP-07 | Phase 2 | Pending |
| LOOP-08 | Phase 2 | Pending |
| RISK-01 | Phase 3 | Complete |
| RISK-02 | Phase 3 | Complete |
| RISK-03 | Phase 3 | Complete |
| RISK-04 | Phase 3 | Complete |
| RISK-05 | Phase 3 | Complete |
| RISK-06 | Phase 3 | Complete |
| RISK-07 | Phase 3 | Complete |
| POS-01 | Phase 4 | Pending |
| POS-02 | Phase 4 | Pending |
| POS-03 | Phase 4 | Pending |
| POS-04 | Phase 4 | Pending |
| POS-05 | Phase 4 | Pending |
| POS-06 | Phase 4 | Pending |
| POS-07 | Phase 4 | Pending |
| PERF-01 | Phase 5 | Pending |
| PERF-02 | Phase 5 | Pending |
| PERF-03 | Phase 5 | Pending |
| PERF-04 | Phase 5 | Pending |
| PERF-05 | Phase 5 | Pending |
| PERF-06 | Phase 5 | Pending |
| MON-01 | Phase 6 | Pending |
| MON-02 | Phase 6 | Pending |
| MON-03 | Phase 6 | Pending |
| MON-04 | Phase 6 | Pending |
| MON-05 | Phase 6 | Pending |
| MON-06 | Phase 6 | Pending |
| SIG-01 | Phase 7 | Pending |
| SIG-02 | Phase 7 | Pending |
| SIG-03 | Phase 7 | Pending |
| SIG-04 | Phase 7 | Pending |
| SIG-05 | Phase 7 | Pending |
| SIG-06 | Phase 7 | Pending |
| ARISK-01 | Phase 7 | Pending |
| ARISK-02 | Phase 7 | Pending |
| BACK-01 | Phase 8 | Pending |
| BACK-02 | Phase 8 | Pending |
| BACK-03 | Phase 8 | Pending |
| BACK-04 | Phase 8 | Pending |
| EXCH-01 | Phase 9 | Pending |
| EXCH-02 | Phase 9 | Pending |
| EXCH-03 | Phase 9 | Pending |
| SAFE-01 | Phase 10 | Pending |
| SAFE-02 | Phase 10 | Pending |
| SAFE-03 | Phase 10 | Pending |
| SAFE-04 | Phase 10 | Pending |
| SAFE-05 | Phase 10 | Pending |
| SAFE-06 | Phase 10 | Pending |
| DASH-01 | Phase 11 | Pending |
| DASH-02 | Phase 11 | Pending |
| DASH-03 | Phase 11 | Pending |
| DASH-04 | Phase 11 | Pending |
| DASH-05 | Phase 11 | Pending |
| DASH-06 | Phase 11 | Pending |
| TAX-01 | Phase 11 | Pending |

**Coverage:**
- v1 requirements: 63 total
- Mapped to phases: 63
- Unmapped: 0

---
*Requirements defined: 2026-02-04*
*Last updated: 2026-02-04 after roadmap creation*
