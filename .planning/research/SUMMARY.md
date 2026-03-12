# Project Research Summary

**Project:** CryptoTrader Autonomous Trading Engine
**Domain:** Autonomous cryptocurrency day trading with AI agents
**Researched:** 2026-02-04
**Confidence:** MEDIUM-HIGH

## Executive Summary

CryptoTrader is an autonomous cryptocurrency trading system that uses multiple AI agents to analyze markets and execute trades. Based on research, the existing codebase has strong foundational components (FastAPI backend, React frontend, agent framework, paper trading engine, WebSocket market data) but is missing the critical **autonomous execution loop** that makes agents actually run continuously. The system is 60-70% complete as scaffolding but lacks the wiring to transition from "agents exist" to "agents autonomously trade."

The recommended approach is to build in three major phases: (1) Make agents run autonomously with proper state persistence, (2) Wire market data to decision logic to execution, and (3) Add risk management and live trading safety features. The core technical stack is sound (APScheduler for agent scheduling, Backtrader for strategy validation, pandas-ta for technical indicators, transitions for order state management), but several critical gaps must be addressed before any live trading: paper trading state is not persisted across restarts, rate limiting fails open when Redis is down, partial fills are not handled, and slippage/fees are not modeled in paper trading.

The key risk is the **paper-to-live transition** where all the "good enough for simulation" shortcuts become real-money disasters. Paper trading must be battle-tested with realistic fees, slippage, and state persistence for at least 30 days before enabling live trading. The second major risk is **exchange integration failures** (WebSocket disconnections, rate limiting, API errors) which require circuit breakers and fail-closed patterns. With proper attention to state management and risk controls, this architecture can produce a trustworthy autonomous trading system.

## Key Findings

### Recommended Stack

The existing stack (FastAPI, React, Celery+Redis, krakenex, SQLAlchemy/SQLite) provides the foundation and should be retained. To enable autonomous trading, add:

**Core technologies:**
- **APScheduler 3.10+**: Agent execution scheduling — lightweight, integrates with FastAPI lifecycle, supports sub-minute intervals for trading agents
- **Backtrader 1.9.78+**: Strategy backtesting — industry standard event-driven framework that mirrors live trading architecture
- **pandas-ta 0.3.14b**: Technical indicators — pure Python (no system dependencies), 130+ indicators for AI signal generation
- **transitions 0.9.0+**: Order state machines — prevents invalid order state transitions (e.g., canceling filled orders)
- **Custom paper trading engine**: Already built, but needs database persistence layer for positions, cash, and P&L
- **Custom portfolio service**: Track real-time positions, P&L, margin, and risk metrics using SQLAlchemy + numpy

**Installation script:**
```bash
pip install apscheduler==3.10.4
pip install backtrader==1.9.78.123
pip install pandas-ta==0.3.14b0
pip install transitions==0.9.0
pip install pytest-asyncio freezegun  # testing
```

**Architecture integration:** APScheduler runs in FastAPI process (not Celery), agents execute in scheduled loops, paper engine simulates fills with realistic latency/slippage, state persists to SQLite via SQLAlchemy.

### Expected Features

**Must have (table stakes):**
- Core trading loop: market data ingestion, signal generation, order execution, position tracking, trade logging, error handling
- Risk management: position size limits, stop-loss enforcement, daily loss limits, portfolio exposure limits, API rate limiting
- Position management: entry/exit execution, position sizing, partial fills handling, open position monitoring, failed order recovery
- Monitoring & alerting: system health, trade alerts, risk breach alerts, error alerts, daily summaries, connection status
- Safety features: emergency stop, manual override, paper trading mode, dry-run mode, balance validation

**Should have (competitive differentiators):**
- Multi-agent consensus: multiple AI perspectives reduce false signals
- Sentiment analysis: social/news sentiment as signal input
- Adaptive position sizing: dynamic sizing based on confidence/volatility (Kelly criterion)
- Historical backtesting: validate strategies on past data before live trading
- Performance feedback loop: agents learn from past trades (reinforcement learning)
- Real-time dashboards: live view of all bot activity via WebSocket

**Defer (v2+):**
- Multi-exchange support (start with Kraken only)
- Advanced learning/adaptation features (true AI self-improvement)
- Monte Carlo simulation and walk-forward analysis
- Tax reporting integration
- External signal integration (TradingView, etc.)

**Anti-features (explicitly avoid):**
- Guaranteed returns promises (illegal, impossible)
- High-frequency trading (infrastructure complexity not needed)
- Leverage trading initially (start with spot trading only)
- "Set and forget" marketing (requires active monitoring)
- Social trading/copy trading (legal liability)

**User trust factors:** Transparent decision-making (agent logs), proven paper trading results (30+ days profitable), conservative defaults (tight stop-losses), emergency controls always available, complete trade history never hidden, realistic performance claims (show drawdowns not just gains).

### Architecture Approach

Autonomous crypto trading requires a **hybrid event-driven + scheduled architecture** where market data streams trigger analysis while periodic health checks ensure reliability. The critical gap is the **autonomous execution loop** — agents exist but don't run continuously.

**Major components:**
1. **Agent Manager** — starts/stops all agents on FastAPI lifespan, monitors health, coordinates startup/shutdown sequencing
2. **Orchestrator Agent** — coordinates decisions from specialist agents, generates trade signals, enforces decision cooldowns (120s per symbol)
3. **Market Analyst Agent** — subscribes to Kraken WebSocket, analyzes price/volume patterns, publishes insights to message queue
4. **Trade Executor Agent** — subscribes to trade signals, routes to paper/live execution, handles order states, persists results
5. **Risk Monitor Agent** — runs checks every 10s, enforces position limits, publishes alerts, can pause trading via circuit breaker
6. **Strategy Optimizer Agent** — runs scheduled optimizations (every 6 hours), backtests strategies, publishes updated parameters
7. **Sentiment Agent** — scrapes news/social data (every 30 minutes), calculates sentiment scores, feeds orchestrator
8. **Paper Trading Engine** — simulates trades with realistic fills, slippage, and fees; tracks positions/P&L; **needs DB persistence**
9. **Trading Control Singleton** — global pause/resume state, trading mode (paper vs live), accessed by all agents

**Data flow patterns:**
- Market data (event-driven): Kraken WebSocket → Market Analyst → publishes insights → Orchestrator receives → generates trade signal
- Trading decision (hybrid): Orchestrator checks cooldown → fetches current price → calculates position size → publishes signal → Trade Executor routes to paper/live
- Risk monitoring (scheduled + event-driven): Risk Monitor checks limits every 10s + subscribes to trade events for immediate updates
- State persistence: Paper engine writes to DB on every trade, agents checkpoint state on shutdown, reconcile on startup

**Patterns to follow:**
- Agent lifecycle hooks: use `on_start()` and `on_stop()` for setup/teardown
- Circuit breakers for external services: fail closed, not open
- Graceful degradation: non-critical component failures don't halt trading
- Idempotent message handling: same message multiple times = same result

### Critical Pitfalls

**Confirmed in codebase analysis:**

1. **Paper trading state not persisted** — All positions, cash, P&L stored in memory. Restart = everything forgotten. False performance metrics, duplicate positions, live trading disaster waiting to happen. **FIX:** Add `positions` and `portfolio_snapshots` DB tables, load on startup, write on every trade.

2. **Rate limiter fails open** — When Redis is unavailable, rate limiter returns `True` (allow all requests). Bot hammers Kraken API, gets banned (15min to 24hr lockouts). **FIX:** Fail closed (raise exception), add circuit breaker, implement exponential backoff.

3. **Async/sync database query mismatch** — Synchronous SQLAlchemy queries in async functions block event loop. Trading decisions delayed, WebSocket timeouts. **FIX:** Wrap all DB calls in `asyncio.to_thread()` or migrate to AsyncSession.

4. **Partial fills not handled** — Order for 1.0 BTC only fills 0.3 BTC, bot thinks order completed, closes tracker. Remaining 0.7 BTC order still open. Position size mismatches, risk limits violated. **FIX:** Track `filled_volume` vs `requested_volume`, retry remaining, update positions with actual fills.

5. **Slippage and fees not modeled** — Paper trading fills at exact price with zero fees. Strategy looks profitable in paper (100 wins) but live trading adds 0.26% fees + slippage, becomes unprofitable (95 wins after costs). **FIX:** Apply Kraken fee schedule (0.16-0.26%), add slippage (0.1%), model bid-ask spread.

6. **Stop-loss not enforced** — Positions tracked but no trigger logic for stop-loss/take-profit. Losses exceed limits, manual intervention required. **FIX:** Continuous price monitoring, generate EXIT signal when stop-loss hit, add guardian agent for risk enforcement.

**Domain knowledge pitfalls:**

7. **WebSocket reconnection** — Disconnections not detected, stale data leads to bad decisions. **FIX:** Exponential backoff reconnection (1s→60s), heartbeat every 30s, log all disconnections.

8. **Race condition: price staleness** — Price fetched at T=0, order placed at T+200ms, price changed in between. Slippage exceeds thresholds. **FIX:** Add price timestamp, reject if >500ms stale, fetch fresh price before order.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Agent Execution Infrastructure
**Rationale:** Agents exist but don't run autonomously. Must build execution loop before anything else works.
**Delivers:** Agent Manager, FastAPI lifespan integration, agents start/stop properly, health check endpoint
**Addresses:** Autonomous execution loop (architecture gap)
**Avoids:** Silent agent failures (pitfall: agents appear running but frozen)
**Research needed:** Standard pattern, no deep research required

### Phase 2: State Persistence & Reliability
**Rationale:** Paper trading state loss is a critical bug that invalidates all testing and risks live trading disaster.
**Delivers:** DB schema for positions/portfolio, paper engine persistence, restart reconciliation, rate limiter fail-closed
**Addresses:** Paper trading state persistence (pitfall #1), rate limiting (pitfall #2), async DB handling (pitfall #3)
**Avoids:** False performance metrics, state corruption on restart, exchange API bans
**Research needed:** None (SQLAlchemy patterns well-documented)

### Phase 3: Market Data to Decision Flow
**Rationale:** Wire existing components into complete data flow: WebSocket → analysis → decision → execution.
**Delivers:** Market Analyst subscribes to WebSocket, publishes insights, Orchestrator generates signals, Trade Executor routes to paper engine
**Addresses:** Core trading loop (table stakes features)
**Avoids:** Stale data trading (pitfall: price staleness race condition)
**Research needed:** None (existing components, just wiring)

### Phase 4: Order Execution & Realism
**Rationale:** Paper trading must reflect reality (fees, slippage, partial fills) to validate strategies before live trading.
**Delivers:** Fee calculation (0.16-0.26%), slippage modeling (0.1%), partial fill handling, idempotent order placement
**Addresses:** Partial fills (pitfall #4), slippage/fees modeling (pitfall #5)
**Avoids:** False confidence in unprofitable strategies, live trading surprises
**Research needed:** Minimal (verify Kraken fee schedule, already have patterns)

### Phase 5: Risk Management & Safety
**Rationale:** Risk enforcement must work before increasing capital or enabling live trading.
**Delivers:** Stop-loss/take-profit enforcement, Risk Monitor agent running, circuit breakers, emergency stop, Trading Control pause/resume
**Addresses:** Stop-loss enforcement (pitfall #6), risk management (table stakes)
**Avoids:** Losses exceeding limits, catastrophic drawdowns
**Research needed:** None (risk patterns standard)

### Phase 6: Backtesting & Strategy Validation
**Rationale:** Validate strategies against historical data before risking capital.
**Delivers:** Backtrader integration, strategy parameter optimization, performance comparison (bot vs buy-and-hold)
**Addresses:** Historical backtesting (differentiator feature)
**Avoids:** Overfitting (use walk-forward validation)
**Research needed:** **YES** — Backtrader API integration, strategy translation patterns

### Phase 7: Additional Agents & Learning
**Rationale:** Enhance signal quality and adaptability after core loop proven stable.
**Delivers:** Strategy Optimizer agent (scheduled optimization), Sentiment Agent (news/social), performance feedback loop
**Addresses:** Multi-agent consensus, sentiment analysis, adaptive signals (differentiator features)
**Avoids:** Complexity before validation (anti-pattern: premature optimization)
**Research needed:** **YES** — Sentiment data sources (Twitter API, Reddit), ML feedback loop patterns

### Phase 8: Live Trading Readiness (Optional)
**Rationale:** Paper-to-live transition is most dangerous phase. Requires extensive checklist and validation.
**Delivers:** Kraken order management, live trading safety checks, manual approval workflow, parallel paper/live testing
**Addresses:** Live trading transition (anti-pattern: set-and-forget)
**Avoids:** All paper trading shortcuts becoming real-money disasters
**Research needed:** **YES** — Kraken API order management, error codes, rate limits, nonce handling

### Phase Ordering Rationale

- **Infrastructure first (Phase 1):** Can't test anything until agents actually run
- **Persistence early (Phase 2):** State corruption invalidates all subsequent testing
- **Wiring before features (Phase 3):** Prove data flows end-to-end with simplest agents
- **Realism before validation (Phase 4):** Paper trading must reflect reality to validate strategies
- **Safety before scaling (Phase 5):** Risk controls must work before increasing capital
- **Validation before complexity (Phase 6-7):** Prove core loop works before adding advanced features
- **Live trading last (Phase 8):** Only after 30+ days profitable paper trading with realistic fees

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 6 (Backtesting):** Backtrader API integration patterns, strategy class structure, data feed formats
- **Phase 7 (Learning Agents):** Sentiment data sources and APIs, ML feedback loop architecture, reinforcement learning patterns
- **Phase 8 (Live Trading):** Kraken API order management endpoints, error code handling, rate limit specifics, nonce requirements

**Phases with standard patterns (skip research-phase):**
- **Phase 1 (Agent Infrastructure):** APScheduler + FastAPI lifespan well-documented
- **Phase 2 (State Persistence):** SQLAlchemy ORM patterns standard
- **Phase 3 (Data Flow):** Message queue pub/sub patterns well-established
- **Phase 4 (Order Execution):** Standard e-commerce/trading patterns
- **Phase 5 (Risk Management):** Common trading risk patterns, circuit breaker pattern

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Existing stack is sound, additions are well-established libraries (APScheduler, Backtrader, pandas-ta) |
| Features | HIGH | Table stakes features align with industry standards for trading bots, differentiators validated by competitive analysis |
| Architecture | MEDIUM-HIGH | Hybrid event-driven + scheduled pattern is proven, but specific agent coordination needs testing |
| Pitfalls | HIGH | Six critical pitfalls confirmed via direct codebase analysis (paper state, rate limiting, async/sync, partial fills, fees, stop-loss) |

**Overall confidence:** MEDIUM-HIGH

Research is based on direct codebase analysis (HIGH confidence) combined with established trading system patterns (MEDIUM-HIGH confidence). Main uncertainty is around optimal agent coordination timing (decision cooldowns, health check intervals) which requires empirical testing and tuning.

### Gaps to Address

**Identified gaps requiring attention during implementation:**

- **WebSocket reconnection details:** Service exists (`kraken_ws.py`) but needs dedicated analysis to verify auto-reconnect logic, exponential backoff parameters, and subscription resumption
- **Optimal decision cooldown timing:** 120-second cooldown is hardcoded but needs backtesting to validate (may be too short in volatile markets or too long in trending markets)
- **Redis performance under high message volume:** Message queue scalability not tested; need load testing with multiple agents publishing at high frequency
- **Kraken API specifics:** Error codes, rate limit headers (Retry-After), nonce requirements need verification with current Kraken API documentation
- **Agent coordination patterns:** Multi-agent consensus logic (how orchestrator weights competing signals) needs design during Phase 7
- **Stop-loss trigger precision:** Sub-second price monitoring vs periodic checks tradeoff (performance vs accuracy) needs benchmarking

**How to handle gaps:**
- Gaps 1-4: Address during Phase 6-8 when features are implemented (defer until needed)
- Gap 5: Design during Phase 7 sprint planning (multi-agent feature)
- Gap 6: Benchmark during Phase 5 implementation (risk management)

## Sources

### Primary (HIGH confidence)
- `/home/packnation82/projects/CryptoTrader/backend/core/paper_trading.py` — Paper trading engine analysis (confirmed state persistence gap)
- `/home/packnation82/projects/CryptoTrader/backend/core/rate_limit.py` — Rate limiting fail-open confirmation
- `/home/packnation82/projects/CryptoTrader/backend/agents/trade_executor.py` — Order execution analysis (confirmed partial fill gap)
- `/home/packnation82/projects/CryptoTrader/backend/agents/orchestrator.py` — Decision coordination logic, cooldown mechanism
- `/home/packnation82/projects/CryptoTrader/backend/agents/base.py` — Agent base class architecture
- `/home/packnation82/projects/CryptoTrader/backend/core/message_queue.py` — Redis pub/sub implementation
- `/home/packnation82/projects/CryptoTrader/.planning/PROJECT.md` — Known tech debt inventory

### Secondary (MEDIUM confidence - training data through Jan 2025)
- APScheduler documentation patterns (agent scheduling integration)
- Backtrader documentation (event-driven backtesting framework)
- pandas-ta library (technical indicator calculation)
- transitions library (finite state machines for order lifecycle)
- Algorithmic trading system design patterns (event-driven architecture, risk management, circuit breakers)
- Crypto market characteristics (24/7 operation, high volatility, exchange failure modes)

### Tertiary (LOW confidence - needs verification)
- Specific Kraken API error codes and rate limit headers (should verify with current Kraken API docs)
- Optimal technical indicator parameters for crypto markets (needs backtesting)
- ML reinforcement learning patterns for trading agents (emerging area, limited battle-tested patterns)

---
*Research completed: 2026-02-04*
*Ready for roadmap: yes*
