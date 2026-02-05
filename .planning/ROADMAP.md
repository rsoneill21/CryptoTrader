# Roadmap: CryptoTrader

**Project:** Autonomous AI-powered cryptocurrency trading engine
**Core Value:** AI autonomously makes profitable trading decisions without constant human intervention
**Milestone:** Paper trading with functional autonomous agents
**Created:** 2026-02-04

## Overview

Transform existing scaffolding into a functional autonomous trading system. This roadmap delivers paper trading with agents that run continuously, analyze markets, make decisions, execute trades, and manage risk — all without manual intervention. The infrastructure (FastAPI, React, agent framework, Kraken integration) exists but agents don't actually run or make real decisions. This roadmap bridges the gap from "skeleton" to "autonomous system."

## Phase Structure

### Phase 1: Infrastructure Hardening
**Goal:** Application infrastructure is reliable and production-ready for autonomous operation

**Dependencies:** None (foundation phase)

**Requirements:** INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06

**Success Criteria:**
1. Server restart preserves all paper trading state (positions, cash, P&L)
2. Rate limiter fails closed when Redis is unavailable (no requests bypass limits)
3. Database queries complete without blocking event loop in async endpoints
4. Exception handlers provide specific error types with stack traces logged
5. List endpoints return paginated results with cursor navigation

**Plan progress:** 9/9 infrastructure plans complete (Phase complete)

### Phase 2: Autonomous Agent Loop
**Goal:** AI agents run continuously on schedule and coordinate via message queue

**Dependencies:** Phase 1 (requires reliable infrastructure)

**Requirements:** LOOP-01, LOOP-02, LOOP-03, LOOP-04, LOOP-05, LOOP-06, LOOP-07, LOOP-08

**Success Criteria:**
1. All agents start automatically when FastAPI application starts
2. Market Analyst agent receives real-time price data from Kraken WebSocket
3. Orchestrator agent receives insights from Market Analyst and generates trade signals
4. Trade Executor agent receives signals and places paper orders
5. Agents continue running after individual agent failure without crashing system
6. Agents shut down gracefully when application stops (no zombie processes)

### Phase 3: Core Risk Management
**Goal:** Configurable risk limits prevent excessive losses and over-trading

**Dependencies:** Phase 2 (requires functioning agent loop)

**Requirements:** RISK-01, RISK-02, RISK-03, RISK-04, RISK-05, RISK-06, RISK-07

**Success Criteria:**
1. Order rejected when position size would exceed configured capital percentage
2. Stop-loss order automatically placed when position opens
3. Trading halts for remainder of day when daily loss limit breached
4. Order rejected when portfolio exposure to single asset exceeds limit
5. Trade rejected when hourly or daily trade frequency limit reached
6. Kraken API rate limits respected (no 429 errors or bans)

### Phase 4: Position & Order Management
**Goal:** Users can open and close positions with market and limit orders

**Dependencies:** Phase 3 (requires risk enforcement)

**Requirements:** POS-01, POS-02, POS-03, POS-04, POS-05, POS-06, POS-07

**Success Criteria:**
1. Market order placed and filled at current market price in paper trading
2. Limit order placed at specified price and filled when price reached
3. Position closed when take-profit or stop-loss triggered
4. Position size calculated from risk parameters and current balance
5. Partial fills tracked and position reflects actual filled volume
6. Open positions display with real-time P&L updating as price changes
7. Failed orders generate alerts and retry with exponential backoff

### Phase 5: Performance Tracking
**Goal:** System accurately calculates and displays trading performance metrics

**Dependencies:** Phase 4 (requires order execution)

**Requirements:** PERF-01, PERF-02, PERF-03, PERF-04, PERF-05, PERF-06

**Success Criteria:**
1. Dashboard shows accurate realized P&L from closed trades and unrealized P&L from open positions
2. Win rate percentage calculated and displayed (profitable trades / total trades)
3. ROI tracked over time with historical chart
4. Maximum drawdown from peak equity tracked and displayed
5. Trade history browsable with filtering by date, symbol, strategy
6. Performance metrics calculated per strategy with comparison view

### Phase 6: Monitoring & Alerting
**Goal:** Users receive real-time notifications of system events and trading activity

**Dependencies:** Phase 4 (requires trading activity to monitor)

**Requirements:** MON-01, MON-02, MON-03, MON-04, MON-05, MON-06

**Success Criteria:**
1. System health dashboard shows agent status (running/stopped/error) and API connectivity
2. Alert generated and displayed when trade opens or closes
3. Alert generated when risk limit approached (80% of limit) or breached (100%)
4. Alert generated on system errors with stack trace for debugging
5. Daily summary email sent with trade count, P&L, and win rate
6. Kraken connection status indicator shows connected/disconnected/reconnecting

### Phase 7: Signal Generation & Intelligence
**Goal:** AI agents generate buy/sell signals from technical indicators and multi-agent consensus

**Dependencies:** Phase 2 (requires agent loop)

**Requirements:** SIG-01, SIG-02, SIG-03, SIG-04, SIG-05, SIG-06, ARISK-01, ARISK-02

**Success Criteria:**
1. Technical indicators (RSI, MACD, Bollinger, MA) calculate and generate signals
2. Pattern detection identifies chart patterns and generates signals
3. Multiple agents vote on trade decisions with confidence scores
4. Orchestrator weighs confidence scores and makes final trade decision
5. Sentiment agent fetches social media sentiment and factors into decisions
6. Position size adjusts dynamically based on signal confidence and market volatility
7. Trailing stop-loss adjusts to market volatility using ATR calculation

### Phase 8: Backtesting & Strategy Validation
**Goal:** Strategies tested against historical data before risking capital

**Dependencies:** Phase 4 (requires order execution logic)

**Requirements:** BACK-01, BACK-02, BACK-03, BACK-04

**Success Criteria:**
1. Historical price data stored in database for backtesting
2. Strategy executed against historical data with realistic fill simulation
3. Backtest results show P&L, win rate, drawdown, Sharpe ratio
4. Strategy comparison view shows statistical significance testing results

### Phase 9: Exchange Abstraction Layer
**Goal:** Kraken implementation hidden behind common interface for future exchange support

**Dependencies:** Phase 4 (requires order management implementation)

**Requirements:** EXCH-01, EXCH-02, EXCH-03

**Success Criteria:**
1. Exchange interface defines common contract (get_price, place_order, get_positions)
2. KrakenExchange class implements interface with Kraken-specific logic
3. PaperTradingExchange class implements same interface for simulation
4. Trade Executor routes to correct exchange based on trading mode setting
5. Adding new exchange requires only implementing interface (no agent changes)

### Phase 10: Safety Features & Controls
**Goal:** Users can halt trading and override AI decisions at any time

**Dependencies:** Phase 2 (requires agent loop)

**Requirements:** SAFE-01, SAFE-02, SAFE-03, SAFE-04, SAFE-05, SAFE-06

**Success Criteria:**
1. Emergency stop button immediately halts all agents and cancels pending orders
2. Manual override toggle disables autonomous trading (agents analyze but don't execute)
3. Paper trading simulates realistic fills with fees (0.16-0.26%), slippage (0.1%), and latency
4. Dry-run mode logs signals and decisions without executing any orders
5. First live trade blocked until user explicitly confirms transition from paper trading
6. Balance validation prevents orders when insufficient funds

### Phase 11: Dashboard & User Experience
**Goal:** Dashboard displays real trading data and provides full control over system

**Dependencies:** Phase 5, Phase 6 (requires performance metrics and alerts)

**Requirements:** DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06, TAX-01

**Success Criteria:**
1. Dashboard shows real portfolio value from database (not placeholder data)
2. Agent status indicators show running/stopped/error with last execution time
3. Recent trades table shows actual executed trades with real timestamps and P&L
4. Live chart displays real-time market data from Kraken WebSocket
5. AI chat references current open positions and market conditions in responses
6. Settings page allows configuring autonomy level, risk limits, and signal weights
7. Trade export generates CSV with cost basis, proceeds, gain/loss for tax reporting

## Progress Tracking

| Phase | Requirements | Status | Completion |
|-------|--------------|--------|------------|
| Phase 1: Infrastructure Hardening | 6 | Complete | 100% |
| Phase 2: Autonomous Agent Loop | 8 | Pending | 0% |
| Phase 3: Core Risk Management | 7 | Pending | 0% |
| Phase 4: Position & Order Management | 7 | Pending | 0% |
| Phase 5: Performance Tracking | 6 | Pending | 0% |
| Phase 6: Monitoring & Alerting | 6 | Pending | 0% |
| Phase 7: Signal Generation & Intelligence | 8 | Pending | 0% |
| Phase 8: Backtesting & Strategy Validation | 4 | Pending | 0% |
| Phase 9: Exchange Abstraction Layer | 3 | Pending | 0% |
| Phase 10: Safety Features & Controls | 6 | Pending | 0% |
| Phase 11: Dashboard & User Experience | 7 | Pending | 0% |

**Total Requirements:** 63 v1 requirements mapped
**Current Phase:** Phase 1
**Milestone Progress:** ~9% (Phase 1 of 11 complete)

## Phase Ordering Rationale

**Infrastructure first (Phase 1):** Paper trading state persistence, rate limiting, and async DB queries must work before agents run continuously. State loss invalidates all testing.

**Agent loop early (Phase 2):** Core autonomous execution must work before adding features. Agents need to actually run before we can validate anything else.

**Risk before execution (Phase 3):** Risk limits must enforce before enabling position management. Prevents testing with unsafe parameters.

**Execution before metrics (Phase 4 → 5):** Need actual trades before performance tracking makes sense. Can't measure what doesn't exist.

**Monitoring alongside execution (Phase 6):** Alerts needed early for debugging agent behavior during development. Visibility into autonomous system is critical.

**Intelligence after core loop (Phase 7):** Advanced signals and consensus require stable agent coordination. Prove simple signals work first.

**Backtesting after execution (Phase 8):** Need order execution logic before historical simulation. Backtesting reuses same execution code.

**Abstraction after implementation (Phase 9):** Extract interface after Kraken implementation proven. Premature abstraction causes over-engineering.

**Safety throughout (Phase 10):** Emergency controls needed before increasing risk. Manual override required for testing.

**Dashboard last (Phase 11):** Polish UI after features work. Real data requires working backend.

## Coverage

**Mapped:** 63/63 v1 requirements
**Unmapped:** 0
**Deferred to v2:** 40 requirements (advanced signals, learning, multi-exchange)

All v1 requirements have been assigned to phases. No orphaned requirements.

---
*Last updated: 2026-02-05*
