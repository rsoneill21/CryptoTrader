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

Plans:
- [x] 01-01-PLAN.md — Async database session factory for trades API
- [x] 01-02-PLAN.md — Fail-closed rate limiting and structured exception scaffolding
- [x] 01-03-PLAN.md — Paper trading engine state persistence & archival
- [x] 01-04-PLAN.md — Alerts API cursor pagination implementation
- [x] 01-05-PLAN.md — Backend import path corrections plus pybreaker install
- [x] 01-06-PLAN.md — FastAPI lifespan hooks for the paper trading engine
- [x] 01-07-PLAN.md — AsyncSession migration for alerts, market, strategies, risk APIs
- [x] 01-08-PLAN.md — Shared pagination helper plus strategies/trades cursors
- [x] 01-09-PLAN.md — Structured exception handling with exc_info logging
- [x] 01-10-PLAN.md — Fix trades POST endpoints to load orders relationship
- [x] 01-11-PLAN.md — Add paper trading session reset/archive API endpoints
- [x] 01-12-PLAN.md — Fix cursor pagination for DESC ordering
- [x] 01-13-PLAN.md — Fix auth rate limiter return value assumption
- [x] 01-14-PLAN.md — AsyncSession migration for auth/export/ai routes
- [x] 01-15-PLAN.md — Replace bare except blocks with typed exceptions

**Plans:** 15 plans (15 complete; Phase 1 ready to close)

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
1. Dashboard displays active positions with real-time P&L
2. User can manually open long/short positions via UI
3. User can close positions at market price via UI
4. Limit orders execute when market reaches target price
5. Stop-loss orders trigger automatically when price threshold breached

### Phase 5: Strategy Backtesting
**Goal:** Users can test trading strategies against historical data before live deployment

**Dependencies:** Phase 4 (requires position management)

**Requirements:** BACK-01, BACK-02, BACK-03, BACK-04, BACK-05, BACK-06

**Success Criteria:**
1. User can select date range and symbol for backtest
2. Backtest runs strategy rules against historical candles
3. Results show total trades, win rate, P&L, max drawdown
4. Backtest respects configured risk limits
5. Results stored in database for comparison

### Phase 6: Advanced Strategy Features
**Goal:** Strategies can use complex rules, multiple timeframes, and AI-driven decisions

**Dependencies:** Phase 5 (requires backtesting)

**Requirements:** STRAT-01, STRAT-02, STRAT-03, STRAT-04, STRAT-05, STRAT-06, STRAT-07, STRAT-08, STRAT-09

**Success Criteria:**
1. Strategy can reference indicators across multiple timeframes
2. Agent generates strategy suggestions based on market conditions
3. User can customize AI-proposed strategy via UI
4. Strategy can be promoted from paper to live after performance review
5. AI agent auto-adjusts strategy parameters when performance degrades

### Phase 7: AI Chat Integration
**Goal:** Users can query trading context and get recommendations via AI assistant

**Dependencies:** Phase 6 (requires advanced strategies)

**Requirements:** CHAT-01, CHAT-02, CHAT-03, CHAT-04, CHAT-05, CHAT-06, CHAT-07, CHAT-08

**Success Criteria:**
1. User asks "Why did you make this trade?" and gets detailed explanation
2. Chat surfaces current positions, P&L, and portfolio exposure
3. Agent provides risk-adjusted suggestions when user asks "What should I do?"
4. Chat references market conditions from Market Analyst agent
5. User can request strategy adjustments via conversational interface

### Phase 8: Performance Analytics
**Goal:** Dashboard displays comprehensive trading performance metrics

**Dependencies:** Phase 7 (requires full data pipeline)

**Requirements:** DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06, DASH-07

**Success Criteria:**
1. Dashboard shows cumulative P&L chart over time
2. User can filter performance by strategy, timeframe, asset
3. Dashboard displays Sharpe ratio, max drawdown, win rate
4. Performance compared against buy-and-hold baseline
5. Dashboard updates in real-time as trades execute

### Phase 9: Safety & Reliability
**Goal:** System detects and mitigates failures before they cause losses

**Dependencies:** Phase 8 (requires mature system)

**Requirements:** SAFE-01, SAFE-02, SAFE-03, SAFE-04, SAFE-05, SAFE-06

**Success Criteria:**
1. Kraken API outage triggers fail-closed behavior (no trades)
2. Agent crash auto-restarts without data loss
3. Paper-to-live transition requires manual confirmation
4. Trading halts if slippage exceeds configured threshold
5. All position state logged for audit trail

### Phase 10: Multi-Asset Support
**Goal:** System supports equities, forex, and commodities alongside crypto

**Dependencies:** Phase 9 (requires stable foundation)

**Requirements:** MULTI-01, MULTI-02, MULTI-03, MULTI-04, MULTI-05

**Success Criteria:**
1. User can connect Alpaca account for equities trading
2. Dashboard displays mixed portfolio (crypto + stocks)
3. Risk limits apply across all asset classes
4. Strategy can trade cross-asset pairs (BTC vs SPY)

### Phase 11: Exchange Abstraction
**Goal:** Agents can trade across Kraken, Coinbase, Binance with unified interface

**Dependencies:** Phase 10 (requires multi-asset proven)

**Requirements:** EXCH-01, EXCH-02, EXCH-03, EXCH-04, EXCH-05

**Success Criteria:**
1. User can connect Coinbase account via settings
2. Single strategy trades on both Kraken and Coinbase
3. Order routing selects exchange with best price
4. Portfolio aggregates positions across all exchanges

---

## Tracking

**Total phases:** 11
**Total requirements:** 63
**Completion:** 1/11 phases (9%)
**Current phase:** Phase 1 (Infrastructure Hardening) — complete
**Updated:** 2026-02-05
