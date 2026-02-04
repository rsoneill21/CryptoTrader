# Autonomous Crypto Trading Bot Pitfalls

**Domain:** Autonomous cryptocurrency day trading with AI agents
**Researched:** 2026-02-04
**Confidence:** HIGH (based on codebase analysis + domain knowledge)

## Executive Summary

Autonomous crypto trading bots fail primarily in the transition from "code exists" to "bot actually trades profitably." The critical failure modes are: **paper trading that doesn't reflect reality** (leading to false confidence), **state management failures** (losing positions across restarts), **order execution edge cases** (partial fills, race conditions, slippage), **exchange API integration pitfalls** (rate limits, nonce errors, WebSocket disconnections), **risk management that fails under pressure**, and **the dangerous paper-to-live transition** (where real money exposes all the previously hidden bugs).

This project has **substantial scaffolding** but multiple critical gaps identified in codebase analysis.

---

## Critical Pitfalls

These mistakes cause catastrophic losses, data corruption, or complete system failure.

### Pitfall 1: Paper Trading State Not Persisted (CONFIRMED IN CODEBASE)

**What goes wrong:**
- Paper trading engine stores all state in memory (`_positions`, `_cash`, `_realized_pnl` in `PaperTradingEngine`)
- Bot restart = all positions forgotten, P&L reset, trading history lost
- AI agents make decisions based on "empty portfolio" when positions actually exist
- When graduating to live trading, this pattern becomes catastrophic (real positions forgotten)

**Why it happens:**
- Paper trading treated as "temporary" simulation rather than training ground
- "We'll fix persistence later" thinking
- Underestimating restart frequency during development

**Consequences:**
- False performance metrics (P&L resets hide losses)
- Duplicate position entries (bot doesn't know it already has a position)
- Strategy validation impossible (can't track multi-day performance)
- Live trading disaster waiting to happen (same pattern would lose real money)

**Detection:**
- Check if `PaperTradingEngine` writes state to DB on shutdown/restart
- Test: Start bot, open position, restart, check if position still exists
- Look for persistence layer in paper trading service

**Current state in CryptoTrader:**
```python
# backend/core/paper_trading.py lines 166-178
def __init__(self, starting_cash: float = 100_000.0, ...):
    self._cash = starting_cash
    self._realized_pnl = 0.0
    self._unrealized_pnl = 0.0
    self._positions: Dict[str, List[_MutablePosition]] = defaultdict(list)
    self._price_book: Dict[str, float] = {}
    # No DB persistence for portfolio state
```
**Status:** CONFIRMED - All portfolio state is in-memory only.

**Prevention:**
```python
# Required changes:
# 1. Add PaperPortfolio DB model (cash, realized_pnl, unrealized_pnl)
# 2. Add PaperPosition DB model (symbol, side, quantity, entry_price, entry_time)
# 3. PaperTradingEngine.__init__() loads state from DB
# 4. PaperTradingEngine writes state to DB on every trade
# 5. Add snapshot() method that persists current state
```

**Phase mapping:** Phase 1 (Core Paper Trading) - MUST fix before any trading

---

### Pitfall 2: Exchange Rate Limits Fail Open (CONFIRMED IN CODEBASE)

**What goes wrong:**
- Rate limiting code returns `True` (allow request) when Redis unavailable
- Bot hammers Kraken API when rate limiter is down
- Kraken bans your IP/API key (temporary or permanent)
- All trading stops until ban lifts (hours to days)

**Why it happens:**
- "Fail open" design pattern prioritizes availability over correctness
- Developer assumes Redis is always up
- Testing doesn't simulate Redis failures

**Consequences:**
- Kraken API ban (15-minute to 24-hour lockouts)
- Loss of trading opportunities during ban period
- Potential permanent API key revocation
- Emergency manual intervention required

**Detection:**
- Search code for "Fail open" or "return True" in rate limit failures
- Test: Stop Redis, verify bot stops making API calls
- Check if rate limiter raises exception when Redis unavailable

**Current state in CryptoTrader:**
```python
# backend/core/rate_limit.py lines 44-47
async def check_rate_limit(key: str, limit: int, window: int) -> bool:
    r = await get_redis()
    if not r:
        # Fail open if Redis is unavailable
        return True  # <-- DANGER: Always allows requests
```
**Status:** CONFIRMED - Rate limiter fails open.

**Prevention:**
```python
# Required changes:
# 1. Fail closed (raise exception) when Redis unavailable
# 2. Add circuit breaker pattern for exchange API
# 3. Implement exponential backoff on API errors
# 4. Local rate limit tracking as fallback (in-memory)
```

**Phase mapping:** Phase 1 (Reliability) - Fix immediately, test with Redis down

---

### Pitfall 3: Async/Sync Database Query Mismatch (CONFIRMED IN CODEBASE)

**What goes wrong:**
- Synchronous SQLAlchemy queries called inside async functions
- Blocks event loop (trading decisions delayed)
- Under load, entire bot becomes unresponsive
- WebSocket connections timeout, market data stales

**Why it happens:**
- SQLAlchemy defaults to sync operations
- Mixing async API (FastAPI) with sync ORM
- `asyncio.to_thread()` wrapper not consistently used

**Consequences:**
- Multi-second delays in order execution
- Missed trading opportunities (price moves while query blocks)
- WebSocket disconnections (event loop frozen)
- Race conditions in order status checks

**Detection:**
- Search for `SessionLocal()` or `db.query()` in async functions
- Look for missing `await asyncio.to_thread()`
- Profile event loop blocking time

**Current state in CryptoTrader:**
```python
# backend/core/paper_trading.py line 209
async def persist_closed_trades(self, trades: Iterable[PaperTradeResult]) -> int:
    persisted = await asyncio.to_thread(self._persist_trades, list(trades))
    return persisted
```
**Status:** PARTIAL FIX - Paper trading uses `asyncio.to_thread()` but project notes mention "sync DB queries in async routes" as tech debt.

**Prevention:**
```python
# Required changes:
# 1. Audit all async routes for direct SQLAlchemy calls
# 2. Wrap all DB operations in asyncio.to_thread()
# 3. OR migrate to async SQLAlchemy (AsyncSession)
# 4. Add event loop blocking detector in tests
```

**Phase mapping:** Phase 1 (Core Reliability) - Blocks all async operations

---

### Pitfall 4: Partial Fill Handling Missing

**What goes wrong:**
- Place order for 1.0 BTC, only 0.3 BTC fills
- Bot thinks order completed, closes position tracker
- Remaining 0.7 BTC order still open on exchange
- Second trade attempt fails (insufficient capital) or creates unexpected position

**Why it happens:**
- Testing only with market orders that fill instantly
- Limit orders partially fill during low liquidity
- Order status polling doesn't check `filled_volume` vs `requested_volume`

**Consequences:**
- Position size mismatches (bot thinks it has X, exchange shows Y)
- Capital calculation errors (overspending or underspending)
- Risk limits violated (positions larger than intended)
- Liquidation risk (over-leveraged without knowing)

**Detection:**
- Check if order executor compares `filled_volume` to `requested_volume`
- Test with limit orders in low-liquidity pairs
- Look for "partial fill" handling in order status logic

**Current state in CryptoTrader:**
```python
# backend/agents/trade_executor.py lines 289-315
# Order status check logs filled_volume but doesn't handle partial fills:
if status.status in (OrderStatus.CLOSED, OrderStatus.CANCELED, OrderStatus.EXPIRED):
    self._log_system_event("info", "Order reached terminal status", {
        "filled_volume": str(status.filled_volume),
        # ... but no logic to retry remaining volume
    })
    self._pending_orders.pop(signal_id, None)  # <-- Removes from tracking
```
**Status:** CONFIRMED GAP - No partial fill retry logic.

**Prevention:**
```python
# Required changes:
# 1. Track filled_volume vs requested_volume per order
# 2. If filled_volume < requested_volume and status is CLOSED:
#    - Create new order for remaining volume
#    - Or notify orchestrator of partial fill
# 3. Update position size with actual filled amount, not requested
# 4. Add partial fill test cases (mock exchange returns 50% fills)
```

**Phase mapping:** Phase 2 (Order Management) - Critical before live trading

---

### Pitfall 5: Race Condition Between Price Updates and Order Placement

**What goes wrong:**
- AI agent checks price: BTC = $50,000, decides to buy
- 200ms later: Places market order
- Price is now $50,500 (slippage)
- Order fills at unexpected price, violates risk limits

**Why it happens:**
- Price fetched separately from order placement
- No atomic "check price and place order" operation
- WebSocket price updates not used for order decisions

**Consequences:**
- Slippage exceeds acceptable thresholds
- Losses on every trade due to stale prices
- Risk management calculates wrong position sizes
- Arbitrage opportunities missed (price moved before execution)

**Detection:**
- Timestamp price fetches and order placements
- Measure time delta between decision and execution
- Check if orders use real-time price or cached price

**Current state in CryptoTrader:**
```python
# Paper trading uses cached prices from price_book:
# backend/core/paper_trading.py line 434
def _resolve_price(self, symbol: str, candidate_price: Optional[float]) -> float:
    if candidate_price is not None:
        return float(candidate_price)
    known_price = self._price_book.get(symbol)  # <-- May be stale
```
**Status:** VULNERABLE - Price book updated async, no freshness guarantee.

**Prevention:**
```python
# Required changes:
# 1. Add price timestamp to _price_book entries
# 2. Reject orders if price is >500ms stale
# 3. Fetch fresh price immediately before order placement
# 4. For paper trading: Simulate realistic latency and slippage
# 5. Use WebSocket last trade price (most current)
```

**Phase mapping:** Phase 2 (Order Execution) - Affects profitability

---

### Pitfall 6: Agent Message Queue Deadlock

**What goes wrong:**
- Agent A sends message to Agent B, awaits response
- Agent B sends message to Agent A, awaits response
- Both agents blocked forever (deadlock)
- Trading stops until manual restart

**Why it happens:**
- Synchronous message passing between agents
- No timeout on message responses
- Circular dependencies in agent communication

**Consequences:**
- Complete system freeze (no orders, no updates)
- Requires manual intervention (restart)
- Data loss if messages were mid-processing
- SLA violation (trading halted during market opportunities)

**Detection:**
- Trace agent message flows for circular dependencies
- Add timeout to all `await` calls on message responses
- Look for blocking `send_message()` calls

**Current state in CryptoTrader:**
```python
# backend/agents/base.py lines 192-220
async def send_message(self, recipient: str, ...):
    # Sends message to target agent's queue
    target = AgentRegistry.get(recipient)
    if target:
        await target.receive_message(message)  # <-- No timeout
    # No response mechanism, so no deadlock risk currently
    # BUT: If response mechanism added later, deadlock possible
```
**Status:** LOW RISK (no response mechanism yet) but ARCHITECTURAL CONCERN.

**Prevention:**
```python
# Required changes:
# 1. Add timeout to all message operations (default 5s)
# 2. Use request-response pattern with correlation IDs
# 3. Detect circular message patterns at runtime
# 4. Implement message priority queue (high-priority breaks cycles)
# 5. Add deadlock detector (monitors message queue depths)
```

**Phase mapping:** Phase 3 (Agent Coordination) - Test multi-agent scenarios

---

## Moderate Pitfalls

These cause delays, technical debt, or degraded performance but not immediate catastrophic failure.

### Pitfall 7: WebSocket Reconnection Logic Missing

**What goes wrong:**
- WebSocket to Kraken disconnects (network hiccup, exchange restart)
- Bot doesn't detect disconnection
- Continues making decisions on stale data (last price before disconnect)
- Executes unprofitable trades based on outdated market conditions

**Why it happens:**
- Testing with stable connections
- No WebSocket heartbeat/ping monitoring
- Reconnection logic not implemented

**Consequences:**
- Stale market data (prices lag by minutes)
- Bad trading decisions (buying/selling at wrong times)
- Loss of real-time data advantages
- Manual monitoring required (defeats "autonomous" goal)

**Detection:**
- Check for WebSocket heartbeat monitoring
- Test: Kill WebSocket connection, verify auto-reconnect
- Look for "reconnect on close" logic

**Current state in CryptoTrader:**
```python
# backend/services/kraken_ws.py exists but needs review
# TODO: Analyze WebSocket reconnection logic
```
**Status:** UNKNOWN - Needs dedicated review.

**Prevention:**
- Implement exponential backoff reconnection (1s, 2s, 4s, 8s, max 60s)
- Add connection health check (ping every 30s, reconnect if no pong)
- Log all disconnections and reconnections
- Add metric: "seconds since last price update"

**Phase mapping:** Phase 2 (Market Data Reliability) - Critical for real-time trading

---

### Pitfall 8: No Order Nonce/Idempotency Handling

**What goes wrong:**
- Network timeout while placing order
- Bot doesn't know if order succeeded
- Retries order placement
- Two orders placed instead of one (double position)

**Why it happens:**
- HTTP request times out, unclear if server processed it
- Retry logic doesn't use idempotency keys
- No deduplication on exchange side

**Consequences:**
- Duplicate orders (2x intended position size)
- Risk limits exceeded
- Over-exposure to market risk
- Emergency manual cancellation required

**Detection:**
- Check if order placement uses `client_order_id` (idempotency key)
- Test: Simulate timeout, verify retry doesn't duplicate
- Look for nonce handling in Kraken API calls

**Current state in CryptoTrader:**
```python
# backend/agents/trade_executor.py line 256
result = await kraken_service.place_order(
    # ...
    client_order_id=signal.client_order_id or signal.signal_id,  # <-- GOOD
)
```
**Status:** GOOD - Using client_order_id for idempotency.

**Prevention:**
- Already implemented correctly
- Verify Kraken API respects `client_order_id` for deduplication
- Add test: Same client_order_id twice should reject second order

**Phase mapping:** N/A - Already handled

---

### Pitfall 9: AI Decision Quality Not Measurable

**What goes wrong:**
- AI agent makes trade decision
- No logging of reasoning, confidence, or context
- Trade loses money
- Impossible to debug why AI made bad decision
- Can't improve AI over time

**Why it happens:**
- Focus on "making it work" rather than observability
- Treating AI as black box
- Insufficient structured logging

**Consequences:**
- AI remains stupid (can't learn from mistakes)
- No confidence scoring (bad trades same priority as good trades)
- Regulatory/audit trail missing (can't explain decisions)
- User trust eroded (bot seems random)

**Detection:**
- Check if AI decisions log: reasoning, confidence, market context, indicators
- Review trade records for decision metadata
- Look for structured logging of AI outputs

**Current state in CryptoTrader:**
```python
# Paper trading already captures rich context:
# backend/core/paper_trading.py lines 321-388
def _build_decision_context(self, signal, price):
    return {
        "reasoning": {...},
        "market_conditions": {...},
        "indicators": {...},
        "near_miss": {...},
    }
# And stores in Trade.metadata
```
**Status:** GOOD - Paper trading captures context. Need to verify agents populate it.

**Prevention:**
- Ensure agents pass context in `PaperTradeSignal.metadata`
- Add AI confidence score to each decision (0.0-1.0)
- Log rejected decisions (why didn't we trade?)
- Build decision replay system (what would different AI have done?)

**Phase mapping:** Phase 3 (AI Improvement) - Enables iterative refinement

---

### Pitfall 10: Paper Trading Doesn't Model Slippage or Fees

**What goes wrong:**
- Paper trading fills orders at exact bid/ask price, zero fees
- Strategy looks profitable in paper trading (100 wins, 50 losses)
- Live trading adds 0.26% fees + slippage
- Same strategy is now unprofitable (95 wins, 55 losses after fees)

**Why it happens:**
- Paper trading simplified for initial implementation
- "We'll add realism later" thinking
- Underestimating impact of fees on high-frequency strategies

**Consequences:**
- False confidence in unprofitable strategies
- Surprised by losses when switching to live trading
- Strategies optimized for zero-cost environment fail in reality

**Detection:**
- Check if paper trading applies fees to trades
- Look for slippage modeling (market orders fill worse than last price)
- Review `PaperTradeResult` for fee field usage

**Current state in CryptoTrader:**
```python
# backend/core/paper_trading.py line 88
class PaperTradeResult(BaseModel):
    # ...
    fees: float = 0.0  # <-- Always zero currently
```
**Status:** CONFIRMED GAP - Fees not calculated, slippage not modeled.

**Prevention:**
```python
# Required changes:
# 1. Apply Kraken fee schedule (0.16%-0.26% depending on volume)
# 2. Add configurable slippage (default 0.1% for market orders)
# 3. Model bid-ask spread (buy at ask + slippage, sell at bid - slippage)
# 4. Add fee calculation: fees = (entry_cost + exit_cost) * fee_rate
```

**Phase mapping:** Phase 2 (Realistic Paper Trading) - Before strategy validation

---

### Pitfall 11: No Stop-Loss or Take-Profit Enforcement

**What goes wrong:**
- Strategy sets stop-loss at -5% and take-profit at +10%
- Price hits stop-loss trigger
- No mechanism to automatically close position
- Loss grows to -15% before manual intervention

**Why it happens:**
- Stop-loss treated as "nice to have" feature
- No continuous position monitoring
- Risk management separated from execution

**Consequences:**
- Losses exceed risk limits
- Emotional trading (manual intervention under stress)
- Risk management rules ignored
- Account drawdown larger than planned

**Detection:**
- Check if positions track stop-loss/take-profit levels
- Look for price monitoring that triggers closes
- Test: Set stop-loss, move price past it, verify auto-close

**Current state in CryptoTrader:**
```python
# Paper trading has position tracking but no trigger logic
# No stop-loss enforcement found in orchestrator or trade executor
```
**Status:** CONFIRMED GAP - No automatic stop-loss/take-profit.

**Prevention:**
- Add stop-loss and take-profit fields to positions
- Implement continuous price monitoring (every price update checks triggers)
- Generate EXIT signal when stop-loss or take-profit hit
- Add separate "guardian agent" that enforces risk rules

**Phase mapping:** Phase 2 (Risk Management) - Essential before increasing capital

---

## Minor Pitfalls

These cause annoyance but are relatively easy to fix.

### Pitfall 12: Bare Exception Handling (CONFIRMED IN CODEBASE)

**What goes wrong:**
- `except Exception:` catches all errors (KeyboardInterrupt, MemoryError, etc.)
- Bot ignores critical errors
- Hides bugs during development
- Makes debugging nearly impossible

**Why it happens:**
- "Make it not crash" during rapid development
- Copy-paste error handling patterns
- Not understanding exception hierarchy

**Consequences:**
- Silent failures (errors logged but not addressed)
- Bugs hidden until production
- Difficult debugging (no stack traces)

**Detection:**
- Search code for `except Exception:` or `except:`
- Look for missing `raise` after logging

**Current state in CryptoTrader:**
- Project notes explicitly mention "bare exception handling" as tech debt

**Prevention:**
- Catch specific exceptions (KrakenAPIError, ValidationError, etc.)
- Re-raise after logging for critical errors
- Use bare except only for logging and cleanup, then re-raise

**Phase mapping:** Phase 4 (Quality) - Ongoing refactoring

---

### Pitfall 13: No Health Check Endpoint

**What goes wrong:**
- Bot running but agents frozen
- WebSocket disconnected but HTTP API responds
- External monitoring thinks bot is healthy
- Trading stopped but no alerts

**Why it happens:**
- HTTP 200 response = "healthy" assumption
- No deep health checks (agent status, WebSocket connection, DB, Redis)

**Consequences:**
- Silent failures (bot appears up but not trading)
- Late detection (hours before human notices)
- Lost opportunities during downtime

**Detection:**
- Check for `/health` endpoint that validates:
  - Agent registry (all agents running)
  - WebSocket connected
  - Redis reachable
  - Database reachable
  - Last price update within 60s

**Current state in CryptoTrader:**
- System health monitoring mentioned in requirements but needs verification

**Prevention:**
- Implement comprehensive `/health` endpoint
- Return 503 if any critical component unhealthy
- Add `/health/ready` for startup checks
- Include health check in monitoring/alerting

**Phase mapping:** Phase 4 (Observability) - Production readiness

---

### Pitfall 14: Timestamp Timezone Confusion

**What goes wrong:**
- Trading engine uses UTC timestamps
- Exchange API returns local timezone
- Logs show EDT timestamps
- Off-by-hours errors in backtesting and analysis

**Why it happens:**
- Mixing `datetime.now()` and `datetime.utcnow()`
- Not specifying timezone in datetime objects
- Exchange API inconsistencies

**Consequences:**
- Incorrect trade time attribution
- Backtesting gives wrong results
- Off-hours trading when user expects daytime only

**Detection:**
- Search for `datetime.now()` (should be `datetime.now(timezone.utc)`)
- Check if all DB timestamps use timezone-aware datetimes
- Verify exchange API responses parsed with correct timezone

**Current state in CryptoTrader:**
```python
# backend/agents/base.py line 22
timestamp: datetime = field(default_factory=datetime.utcnow)
# Uses utcnow() but without timezone info (naive datetime)
```
**Status:** POTENTIAL ISSUE - Naive datetimes (no timezone info).

**Prevention:**
- Use `datetime.now(timezone.utc)` everywhere
- Make all datetimes timezone-aware
- Store all DB timestamps as UTC
- Convert to user timezone only in UI

**Phase mapping:** Phase 4 (Quality) - Prevent subtle bugs

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Phase 1: Core Paper Trading | State not persisted (Pitfall #1) | Implement DB persistence for positions and cash |
| Phase 1: Core Paper Trading | Rate limits fail open (Pitfall #2) | Fail closed, add circuit breaker |
| Phase 2: Order Management | Partial fills ignored (Pitfall #4) | Track filled_volume, retry remaining |
| Phase 2: Order Management | Slippage not modeled (Pitfall #10) | Add fees and slippage to paper trading |
| Phase 2: Risk Management | Stop-loss not enforced (Pitfall #11) | Continuous price monitoring, auto-close |
| Phase 3: Agent Coordination | Message queue deadlock (Pitfall #6) | Add timeouts, detect circular deps |
| Phase 3: Market Data | WebSocket reconnection (Pitfall #7) | Exponential backoff, heartbeat monitoring |
| Phase 4: Live Trading Transition | Paper-to-live differences | Checklist: persistence, fees, slippage, rate limits, partial fills |

---

## The Dangerous Paper-to-Live Transition

**The most critical phase is graduating from paper to live trading.** This is where all the "good enough for simulation" shortcuts become real-money disasters.

**Checklist before enabling live trading:**

1. **State Management**
   - [ ] All positions persisted to database
   - [ ] Restart doesn't lose portfolio state
   - [ ] Historical P&L accurate for 30+ days

2. **Order Execution**
   - [ ] Partial fills handled correctly
   - [ ] Idempotency prevents duplicate orders
   - [ ] Slippage modeled (paper trading matches live results within 10%)
   - [ ] Fees calculated accurately

3. **Risk Management**
   - [ ] Stop-loss automatically enforced
   - [ ] Daily loss limit halts trading
   - [ ] Max concurrent positions enforced
   - [ ] Max drawdown triggers emergency stop

4. **Exchange Integration**
   - [ ] Rate limiting fails closed (not open)
   - [ ] WebSocket auto-reconnects
   - [ ] API credentials secured (not in code)
   - [ ] Nonce errors handled gracefully

5. **Observability**
   - [ ] Every trade decision logged with reasoning
   - [ ] AI confidence scores recorded
   - [ ] Alerts configured for all risk limit violations
   - [ ] Health check validates all subsystems

6. **Kill Switch**
   - [ ] One-click emergency stop (halts all trading)
   - [ ] Closes all positions immediately
   - [ ] SMS/email alert on emergency stop
   - [ ] Manual confirmation required to restart

7. **Paper-Live Parity Test**
   - [ ] Run paper and live bots in parallel for 7 days
   - [ ] Compare decisions (should be >95% identical)
   - [ ] Compare execution prices (should be within 1%)
   - [ ] Compare P&L (paper should be slightly more optimistic)

**Start with $100 live capital, not $10,000.** Treat the first week of live trading as "production debugging with real money."

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|-----------|-------|
| State persistence issues | HIGH | Direct codebase analysis confirming in-memory-only state |
| Rate limiting fail-open | HIGH | Direct codebase analysis showing return True on Redis failure |
| Async/sync DB mismatch | HIGH | Project notes and codebase analysis |
| Partial fill handling | HIGH | Code review of trade executor showing gap |
| WebSocket reconnection | MEDIUM | Service exists but needs deeper analysis |
| General trading bot pitfalls | HIGH | Domain knowledge from training data (Jan 2025) |

---

## Sources

**Codebase Analysis (HIGH confidence):**
- `/home/packnation82/projects/CryptoTrader/backend/core/paper_trading.py` - Paper trading engine analysis
- `/home/packnation82/projects/CryptoTrader/backend/core/rate_limit.py` - Rate limiting fail-open confirmation
- `/home/packnation82/projects/CryptoTrader/backend/agents/trade_executor.py` - Order execution analysis
- `/home/packnation82/projects/CryptoTrader/.planning/PROJECT.md` - Known tech debt inventory

**Domain Knowledge (MEDIUM confidence - training data):**
- Common crypto trading bot failure modes (exchange rate limiting, WebSocket failures, order execution)
- Python async/sync mixing pitfalls
- SQLAlchemy in async context challenges

**Methodology:** Combined direct codebase analysis (HIGH confidence) with domain knowledge (MEDIUM confidence). All "CONFIRMED" items are backed by specific code references. Domain knowledge items flagged appropriately.
