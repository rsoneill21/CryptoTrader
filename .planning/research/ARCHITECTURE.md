# Architecture Patterns for Autonomous Crypto Trading Systems

**Domain:** Autonomous cryptocurrency trading bots
**Researched:** 2026-02-04
**Overall confidence:** MEDIUM

## Executive Summary

Autonomous crypto trading systems require a hybrid event-driven + scheduled architecture where market data streams trigger analysis while periodic health checks ensure system reliability. The existing CryptoTrader scaffold has the right building blocks (agents, message queue, WebSocket market data, paper trading engine) but lacks the critical **autonomous execution loop** that wires these components together.

Key architectural challenge: **How do we transition from scaffolding where agents exist but don't run, to a continuously-operating system where agents autonomously analyze markets and execute trades?**

## Recommended Architecture

### High-Level System Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                     ORCHESTRATION LAYER                         │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
│  │Agent Manager │────>│ Orchestrator │────>│ Trading      │   │
│  │(Start/Stop)  │     │    Agent     │     │  Control     │   │
│  └──────────────┘     └──────────────┘     └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Message Queue (Redis Pub/Sub)
                              │
┌─────────────────────────────┼─────────────────────────────────┐
│                    AGENT EXECUTION LAYER                        │
│                             │                                   │
│  ┌──────────┐  ┌──────────┐│┌──────────┐  ┌──────────┐       │
│  │ Market   │  │Strategy  │││  Risk    │  │Sentiment │       │
│  │ Analyst  │  │Optimizer │││ Monitor  │  │  Agent   │       │
│  └──────────┘  └──────────┘│└──────────┘  └──────────┘       │
│       │            │        │      │             │             │
│       └────────────┴────────┼──────┴─────────────┘             │
│                             │                                   │
│                    ┌────────▼────────┐                         │
│                    │ Trade Executor  │                         │
│                    └─────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────┼─────────────────────────────────┐
│                     DATA/EXECUTION LAYER                        │
│                             │                                   │
│  ┌──────────┐  ┌──────────┐│┌──────────┐  ┌──────────┐       │
│  │ Kraken   │  │  Paper   │││ Database │  │  State   │       │
│  │WebSocket │  │ Trading  │││(SQLite)  │  │  Store   │       │
│  └──────────┘  └──────────┘│└──────────┘  └──────────┘       │
│       │            │        │      │             │             │
│       └────────────┴────────┼──────┴─────────────┘             │
│                             │                                   │
│                      ┌──────▼──────┐                           │
│                      │Kraken REST  │                           │
│                      │     API     │                           │
│                      └─────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

### Component Boundaries

| Component | Responsibility | Communicates With | State Owned |
|-----------|---------------|-------------------|-------------|
| **Agent Manager** | Start/stop agents, health monitoring | All agents, Trading Control | Agent lifecycle state (running/paused/stopped) |
| **Orchestrator Agent** | Coordinate decisions, chat interface, signal generation | All agents via message queue | Decision timestamps, insight cache, strategy cache |
| **Market Analyst Agent** | Process market data, identify patterns, publish insights | Orchestrator (via queue) | Market indicators, pattern state |
| **Strategy Optimizer Agent** | Optimize strategy parameters, backtest | Orchestrator (via queue) | Strategy configurations, optimization results |
| **Risk Monitor Agent** | Track exposure, enforce risk limits, publish alerts | Orchestrator, Trade Executor | Position limits, drawdown state, risk metrics |
| **Trade Executor Agent** | Execute trades (paper or live), manage orders | Kraken API, Paper Engine, Database | Order state, execution history |
| **Sentiment Agent** | Analyze market sentiment, news, social signals | Orchestrator (via queue) | Sentiment scores, news cache |
| **Message Queue** | Async communication between agents | All agents | Subscription state |
| **Trading Control** | Global pause/resume, circuit breaker | All agents (via shared singleton) | Paused state, reason, triggered_by |
| **Kraken WebSocket** | Real-time market data stream | Paper Engine, Market Analyst | Connection state, subscriptions |
| **Paper Trading Engine** | Simulate trades, track virtual P&L | Trade Executor, WebSocket | Positions, cash, realized/unrealized P&L |
| **Database** | Persist trades, strategies, system logs | Trade Executor, various services | All persistent state |
| **Celery + Redis** | Background tasks (sync trades, cleanup) | FastAPI app, background jobs | Task queue state |

## Data Flow Architecture

### 1. Market Data Flow (Event-Driven)

```
Kraken WebSocket (ticker update)
    │
    ├──> Paper Trading Engine (update_market_price)
    │       └──> Recalculate unrealized P&L
    │
    └──> Market Analyst Agent (callback)
            └──> Analyze price movement, volume, indicators
                └──> Publish market insight → Message Queue
                    └──> Orchestrator receives insight
                        └──> Check if paired with strategy
                            └──> Generate trade signal
```

**Current State:** Market data flows to paper engine ✓, but Market Analyst doesn't have callback wired ✗

**What to Build:**
- Wire Market Analyst to subscribe to Kraken WebSocket ticker callbacks
- Agent processes ticker data in `run()` loop or callback
- Publishes insights to `Channels.AI_DECISIONS`

### 2. Trading Decision Flow (Hybrid: Event + Decision Cooldown)

```
Market Insight + Strategy Update arrive at Orchestrator
    │
    ├──> Check decision cooldown (120s per symbol)
    │       └──> If cooled down, proceed
    │
    ├──> Check Trading Control (paused?)
    │       └──> If paused, skip
    │
    ├──> Determine trade side from insight (bullish → BUY, bearish → SELL)
    │
    ├──> Fetch current price from Kraken REST
    │
    ├──> Calculate position size from strategy params
    │
    └──> Publish trade signal → Channels.TRADE_SIGNALS
            └──> Trade Executor receives signal
                └──> Execute via Paper Engine or Kraken API
                    └──> Persist to database
                        └──> Update Risk Monitor
```

**Current State:** Orchestrator has this logic ✓, Trade Executor exists ✗ (needs implementation)

**What to Build:**
- Trade Executor agent subscribes to `Channels.TRADE_SIGNALS`
- Routes to Paper Engine for paper trades
- Routes to Kraken API for live trades (with confirmation)
- Persists completed trades to database

### 3. Risk Monitoring Flow (Scheduled + Event-Driven)

```
Every 10 seconds (scheduled):
    └──> Risk Monitor checks:
        ├──> Current position sizes vs limits
        ├──> Drawdown vs max drawdown threshold
        ├──> Open order count vs max orders
        └──> Exposure per symbol vs concentration limit
            └──> If violation detected:
                └──> Publish risk alert → Channels.RISK_ALERTS
                    ├──> Orchestrator receives (logs to context)
                    └──> Trading Control receives (may pause trading)

On trade execution (event-driven):
    └──> Trade Executor publishes to Channels.SYSTEM_EVENTS
        └──> Risk Monitor receives
            └──> Updates position tracking
```

**Current State:** Risk Monitor agent exists ✓, but doesn't run autonomously ✗

**What to Build:**
- Risk Monitor runs periodic check in `run()` loop (sleep 10s)
- Subscribes to trade execution events for immediate updates
- Publishes alerts when limits breached

### 4. State Persistence Flow

```
On trade completion:
    └──> Paper Trading Engine: persist_closed_trades()
        └──> Writes Trade records to database
            └──> Includes entry/exit reasoning, P&L, metadata

On agent decision:
    └──> Agent logs to Celery task: log_system_event()
        └──> Async write to system_logs table

On strategy optimization:
    └──> Strategy Optimizer writes to strategies table
        └──> Tracks parameters, backtest results

On application shutdown:
    └──> Each agent: on_stop() hook
        └──> Checkpoint state if needed (positions, pending orders)
```

**Current State:** Paper engine has persistence ✓, agents don't checkpoint state ✗

**What to Build:**
- Agent state checkpointing on shutdown
- Resume from checkpoint on restart (positions, open orders, analysis state)

## Autonomous Execution Loop Architecture

### Problem: Making Agents Actually Run

**Current State:**
- Agents have `BaseAgent` class with `start()`, `stop()`, `_run_loop()`
- Agents are instantiated (e.g., `orchestrator_agent = OrchestratorAgent()`)
- **But nobody calls `start()` on them** → agents never run autonomously

**Solution: Agent Manager Component**

```python
# New component: backend/core/agent_manager.py

class AgentManager:
    """Manages lifecycle of all trading agents."""

    def __init__(self):
        self.agents = {
            "orchestrator": orchestrator_agent,
            "market_analyst": market_analyst_agent,
            "strategy_optimizer": strategy_optimizer_agent,
            "risk_monitor": risk_monitor_agent,
            "trade_executor": trade_executor_agent,
            "sentiment": sentiment_agent,
        }
        self._running = False

    async def start_all(self):
        """Start all agents in dependency order."""
        # Start supporting agents first
        await self.agents["risk_monitor"].start()
        await self.agents["market_analyst"].start()
        await self.agents["strategy_optimizer"].start()
        await self.agents["sentiment"].start()
        await self.agents["trade_executor"].start()

        # Start orchestrator last (coordinates others)
        await self.agents["orchestrator"].start()

        self._running = True
        logger.info("All agents started")

    async def stop_all(self):
        """Stop all agents gracefully."""
        # Stop orchestrator first (stop coordination)
        await self.agents["orchestrator"].stop()

        # Stop others
        for name, agent in self.agents.items():
            if name != "orchestrator":
                await agent.stop()

        self._running = False
        logger.info("All agents stopped")

    async def health_check(self):
        """Periodic health check for all agents."""
        while self._running:
            for name, agent in self.agents.items():
                if agent._running and not agent.is_running:
                    logger.warning(f"Agent {name} is stuck (running but paused)")

            await asyncio.sleep(30)
```

**Integration Point:** FastAPI lifespan event

```python
# backend/main.py

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await start_kraken_ws()
    await agent_manager.start_all()  # <-- START AGENTS HERE

    yield

    # Shutdown
    await agent_manager.stop_all()  # <-- STOP AGENTS HERE
    await stop_kraken_ws()

app = FastAPI(lifespan=lifespan)
```

### Execution Models: Scheduled vs Event-Driven vs Hybrid

| Agent | Execution Model | Loop Behavior | Why This Model |
|-------|----------------|---------------|----------------|
| **Orchestrator** | Hybrid | Processes message queue, minimal sleep (0.1s) | Needs fast response to incoming insights/signals |
| **Market Analyst** | Event-driven | Sleeps until WebSocket callback, then analyzes | Market data arrives unpredictably |
| **Strategy Optimizer** | Scheduled | Runs optimization every 6 hours, sleeps between | Expensive computation, doesn't need real-time |
| **Risk Monitor** | Hybrid | Checks limits every 10s, also subscribes to trade events | Periodic checks + immediate response to trades |
| **Trade Executor** | Event-driven | Sleeps until trade signal, then executes | Only acts when orchestrator sends signal |
| **Sentiment Agent** | Scheduled | Scrapes news/social every 30 minutes | External API rate limits, data updates slowly |

**Pattern: Hybrid Loop for Most Agents**

```python
async def run(self) -> None:
    """Agent-specific logic called repeatedly by base class."""

    # Check if it's time for scheduled work
    if self._should_run_scheduled_task():
        await self._do_scheduled_work()

    # Process any pending events (handled by base class message queue)
    # Base class already processes self._message_queue

    # Sleep to control loop frequency
    await asyncio.sleep(self.loop_interval)
```

**Pattern: Pure Event-Driven (Trade Executor)**

```python
async def run(self) -> None:
    """Event-driven agent sleeps until message arrives."""
    # Base class handles message queue processing
    # We just sleep and let messages wake us via callbacks
    await asyncio.sleep(1.0)  # Long sleep, events wake us

async def process_message(self, message: AgentMessage) -> None:
    """Handle trade signal from orchestrator."""
    if message.message_type == "trade_signal":
        await self._execute_trade(message.payload)
```

## State Management Across Restarts

### Critical State to Preserve

| State Type | Where Stored | Persistence Strategy | Recovery Strategy |
|------------|--------------|---------------------|-------------------|
| **Open Positions** | Paper Trading Engine (in-memory) | Write to `positions` table on every trade | Reload from DB on startup |
| **Open Orders** | Kraken API (live) or Paper Engine (paper) | Query Kraken on startup, or load from DB | Cancel stale orders, recreate active ones |
| **Realized P&L** | Paper Trading Engine | Calculated from closed trades in DB | Sum all trades on startup |
| **Agent Decision State** | Orchestrator (cooldown timestamps) | Write to Redis with TTL | Reload cooldowns from Redis |
| **Strategy Parameters** | Database (`strategies` table) | Write on every optimization | Load latest strategy configs |
| **Risk Limits** | Risk Monitor (in-memory) | Config file or DB settings | Reload from config/DB |
| **Market Data Cache** | Market Analyst (price history) | Recent prices in Redis | Query Kraken for recent candles |

### Position Reconciliation on Restart

**Problem:** Paper trading engine state is in-memory. On restart, open positions are lost.

**Solution:**

1. **Add `positions` table to database:**
   ```sql
   CREATE TABLE positions (
       id INTEGER PRIMARY KEY,
       symbol TEXT NOT NULL,
       side TEXT NOT NULL,  -- 'buy' or 'sell'
       quantity REAL NOT NULL,
       entry_price REAL NOT NULL,
       entry_time TIMESTAMP NOT NULL,
       strategy_id INTEGER,
       is_paper BOOLEAN DEFAULT TRUE,
       metadata_json JSON,
       closed_at TIMESTAMP NULL
   );
   ```

2. **Paper Engine writes positions on open:**
   ```python
   async def _open_position(self, signal: PaperTradeSignal, price: float):
       # ... existing logic ...

       # Persist to DB
       await self._persist_position(entry)
   ```

3. **Paper Engine reconciles on startup:**
   ```python
   async def reconcile_positions(self):
       """Load open positions from database on startup."""
       db = self._db_factory()
       open_positions = db.query(Position).filter(
           Position.is_paper == True,
           Position.closed_at.is_(None)
       ).all()

       for db_pos in open_positions:
           self._positions[db_pos.symbol].append(
               _MutablePosition(
                   symbol=db_pos.symbol,
                   side=TradeSide(db_pos.side),
                   entry_price=db_pos.entry_price,
                   entry_time=db_pos.entry_time,
                   strategy_id=db_pos.strategy_id,
                   metadata=db_pos.metadata_json or {},
                   quantity=db_pos.quantity,
               )
           )

       logger.info(f"Reconciled {len(open_positions)} open positions")
   ```

### Order State Management

**Paper Trading:**
- Orders execute immediately (no partial fills)
- No need to track order state separately from positions

**Live Trading:**
- Orders may partially fill over time
- Must track: `pending`, `partially_filled`, `filled`, `cancelled`
- Store in `orders` table with `status` column
- On restart: query Kraken for open orders, reconcile with DB

**Recommendation:** Start with paper trading only. Add live order tracking in Phase 2.

## Multi-Agent Coordination Without Conflicts

### Problem: Multiple Agents Acting on Same Symbol

**Scenario:**
- Market Analyst publishes bullish insight on BTC/USD
- Strategy Optimizer also publishes optimized strategy for BTC/USD
- Both trigger Orchestrator to generate trade signal
- **Risk:** Double-trading the same symbol

**Solution 1: Decision Cooldown (Already Implemented)**

Orchestrator has 120-second cooldown per symbol:
```python
# In orchestrator.py
last = self._decision_timestamps.get(symbol)
if last and (now - last) < self.DECISION_COOLDOWN:
    return  # Skip duplicate decision
```

This prevents duplicate signals for same symbol within 2 minutes.

**Solution 2: Signal Deduplication**

```python
# In orchestrator.py
def _signal_hash(self, symbol: str, side: OrderSide) -> str:
    """Create unique identifier for a trading decision."""
    return f"{symbol}:{side.value}"

async def _maybe_create_trade_signal(self, symbol: str):
    # ... existing logic ...

    signal_id = self._signal_hash(symbol, side)
    if signal_id in self._recent_signals:
        logger.debug(f"Signal {signal_id} already sent recently")
        return

    self._recent_signals[signal_id] = now
```

**Solution 3: Risk Monitor Enforcement**

Risk Monitor subscribes to `Channels.TRADE_SIGNALS` and validates before execution:

```python
# In risk_monitor.py
async def _validate_signal(self, signal: Dict[str, Any]) -> bool:
    """Check if signal violates risk limits."""
    symbol = signal["symbol"]

    # Check position limits
    current_positions = await self._get_open_positions(symbol)
    if len(current_positions) >= self.max_positions_per_symbol:
        await self._publish_risk_alert("position_limit", symbol)
        return False

    # Check exposure
    total_exposure = sum(p.quantity * p.entry_price for p in current_positions)
    if total_exposure >= self.max_exposure_per_symbol:
        await self._publish_risk_alert("exposure_limit", symbol)
        return False

    return True
```

**Recommendation:** Use all three (cooldown + deduplication + risk validation) for defense in depth.

### Agent Priority and Sequencing

**Principle:** Agents should not depend on execution order, but some natural sequencing helps:

1. **Market Analyst** runs continuously, publishes insights whenever patterns detected
2. **Strategy Optimizer** runs on schedule (every 6 hours), publishes updated strategies
3. **Orchestrator** waits for both insight + strategy, then generates signal
4. **Trade Executor** acts on signal immediately
5. **Risk Monitor** validates before/after execution

**No hard dependencies:** If Market Analyst is slow, Orchestrator doesn't block. It waits for next insight.

## Paper vs Live Trading Separation

### Two-Mode Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  Trading Control Singleton                │
│                                                           │
│  trading_mode: "paper" | "live"                          │
│  paused: bool                                            │
│  reason: str                                             │
│                                                           │
│  Methods:                                                │
│  - set_mode(mode: str) -> None                          │
│  - is_paper() -> bool                                   │
│  - is_live() -> bool                                    │
│  - pause(reason: str) -> None                           │
│  - resume() -> None                                     │
└──────────────────────────────────────────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        │                                  │
        ▼                                  ▼
┌──────────────────┐            ┌──────────────────┐
│ Paper Trading    │            │  Live Trading    │
│   Engine         │            │   Kraken API     │
│                  │            │                  │
│ - Instant fills  │            │ - Real orders    │
│ - Virtual P&L    │            │ - Actual risk    │
│ - No real money  │            │ - Partial fills  │
└──────────────────┘            └──────────────────┘
```

### Trade Executor Routing Logic

```python
class TradeExecutorAgent(BaseAgent):
    async def _execute_trade(self, signal: Dict[str, Any]):
        """Route to paper or live based on trading mode."""

        if trading_control.is_paper():
            result = await self._execute_paper_trade(signal)
        else:
            # Extra safety check for live trading
            if not await self._confirm_live_trade(signal):
                logger.warning("Live trade cancelled by safety check")
                return

            result = await self._execute_live_trade(signal)

        # Log result regardless of mode
        await self._log_execution(result)

    async def _confirm_live_trade(self, signal: Dict[str, Any]) -> bool:
        """Extra validation before executing real money trade."""
        # Check balance
        # Check order size vs account equity
        # Check daily loss limits
        # Possibly require manual approval for large trades
        return True
```

### Preventing Accidental Live Trading

**Safety Mechanisms:**

1. **Environment Variable Requirement:**
   ```python
   TRADING_MODE = os.getenv("TRADING_MODE", "paper")  # Defaults to paper

   if TRADING_MODE == "live":
       if not os.getenv("LIVE_TRADING_CONFIRMED"):
           raise RuntimeError("Set LIVE_TRADING_CONFIRMED=true to enable live trading")
   ```

2. **Startup Warning:**
   ```python
   if trading_control.is_live():
       logger.warning("=" * 60)
       logger.warning("LIVE TRADING MODE ENABLED - REAL MONEY AT RISK")
       logger.warning("=" * 60)
       await asyncio.sleep(5)  # Force user to see warning
   ```

3. **UI Indicator:**
   - Large red banner in frontend when live trading active
   - Separate "Enable Live Trading" button with confirmation dialog

4. **Separate API Keys:**
   - Paper trading uses Kraken public API endpoints (no auth needed for prices)
   - Live trading requires `KRAKEN_API_KEY` and `KRAKEN_API_SECRET` env vars
   - If env vars missing, live trading disabled automatically

## Exchange Downtime and API Failure Handling

### Failure Modes

| Failure Type | Detection | Recovery Strategy |
|--------------|-----------|-------------------|
| **WebSocket Disconnect** | Connection closed exception | Auto-reconnect with exponential backoff (already implemented in `kraken_ws.py`) |
| **REST API Timeout** | `asyncio.TimeoutError` | Retry with backoff (max 3 attempts), then pause trading |
| **Rate Limit Hit** | HTTP 429 response | Sleep for retry-after duration, queue pending requests |
| **Invalid API Credentials** | HTTP 401/403 | Pause trading, alert operator, don't retry |
| **Partial Fill** | Order status = "partially_filled" | Track remaining quantity, retry or cancel based on strategy |
| **Order Rejected** | Kraken returns error | Log reason, alert Risk Monitor, don't retry automatically |
| **Exchange Maintenance** | Scheduled or unexpected downtime | Pause trading, set resume timer based on announced duration |

### WebSocket Reconnection (Already Built)

Kraken WebSocket service has auto-reconnection:
```python
async def _reconnect(self) -> None:
    """Attempt to reconnect with exponential backoff."""
    for attempt in range(1, self._max_reconnect_attempts + 1):
        if await self.connect():
            await self._resubscribe()  # Resume data stream
            return
        await asyncio.sleep(delay)
        delay = min(delay * 2, self._reconnect_delay_max)
```

**What it does:**
- Detects connection loss
- Retries up to 10 times with exponential backoff (1s → 60s max)
- Resubscribes to all previously subscribed feeds

**What to add:**
- Notify Risk Monitor on disconnect (pause trading during reconnection)
- Notify on successful reconnect (resume trading)

### REST API Retry Logic

**Pattern: Retry Wrapper with Circuit Breaker**

```python
# backend/services/kraken.py

class KrakenService:
    def __init__(self):
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,  # Open after 5 failures
            recovery_timeout=60,  # Try again after 60s
        )

    async def _api_call_with_retry(self, func, *args, max_retries=3):
        """Execute API call with retry and circuit breaker."""

        if self._circuit_breaker.is_open():
            raise ServiceUnavailableError("Kraken API circuit breaker open")

        for attempt in range(max_retries):
            try:
                result = await func(*args)
                self._circuit_breaker.record_success()
                return result

            except asyncio.TimeoutError:
                logger.warning(f"Kraken API timeout, attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    self._circuit_breaker.record_failure()
                    raise

            except HTTPError as e:
                if e.status_code == 429:  # Rate limit
                    retry_after = int(e.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited, sleeping {retry_after}s")
                    await asyncio.sleep(retry_after)
                elif e.status_code in {401, 403}:  # Auth failure
                    self._circuit_breaker.record_failure()
                    await trading_control.pause("Kraken API authentication failed")
                    raise
                else:
                    raise
```

**Circuit Breaker State Machine:**
```
CLOSED (normal) --[5 failures]--> OPEN (reject all calls)
                                      |
                                      | [60s timeout]
                                      ▼
                                  HALF_OPEN (try one call)
                                      |
                        [success]─────┴─────[failure]
                           │                    │
                           ▼                    ▼
                        CLOSED                OPEN
```

### Partial Fill Handling

**Problem:** Live orders may fill partially over time (e.g., bought 0.5 BTC of 1.0 BTC order).

**Solution:**

1. **Track Order State:**
   ```python
   @dataclass
   class Order:
       order_id: str
       symbol: str
       side: OrderSide
       requested_quantity: float
       filled_quantity: float
       remaining_quantity: float
       status: str  # "pending", "partial", "filled", "cancelled"
   ```

2. **Periodic Order Status Check:**
   ```python
   # In Trade Executor
   async def _check_open_orders(self):
       """Poll Kraken for order status updates."""
       open_orders = await kraken_service.get_open_orders()

       for order in open_orders:
           if order.status == "partially_filled":
               # Decision: cancel or wait?
               if order.age > timedelta(minutes=5):
                   await kraken_service.cancel_order(order.order_id)
                   logger.info(f"Cancelled slow-filling order {order.order_id}")
   ```

3. **Position Reconciliation:**
   - After partial fill, update position quantity in database
   - Risk Monitor sees actual filled quantity, not intended quantity

**Recommendation for MVP:** Paper trading only (instant fills). Add partial fill logic when implementing live trading in Phase 2.

## Build Order and Dependencies

### Phase Dependency Graph

```
Phase 1: Agent Execution Infrastructure
    └──> Output: Agent Manager, agents start/stop via lifespan
    └──> Dependency: None (foundational)

Phase 2: Market Data Integration
    └──> Output: Market Analyst wired to WebSocket, publishes insights
    └──> Dependency: Phase 1 (agents must run first)

Phase 3: Trading Decision Loop
    └──> Output: Orchestrator generates signals, Trade Executor executes
    └──> Dependency: Phase 2 (needs market data)

Phase 4: Risk Management
    └──> Output: Risk Monitor enforces limits, circuit breakers
    └──> Dependency: Phase 3 (needs trading active)

Phase 5: State Persistence & Recovery
    └──> Output: Position checkpointing, restart reconciliation
    └──> Dependency: Phase 3 (needs positions to persist)

Phase 6: Live Trading (Optional)
    └──> Output: Switch to Kraken API, order management, partial fills
    └──> Dependency: Phases 1-5 (paper trading battle-tested)
```

### Component Build Order Within Each Phase

**Phase 1 Example:**
1. Create `AgentManager` class
2. Wire to FastAPI lifespan
3. Start Orchestrator only (test message queue)
4. Add remaining agents one by one
5. Add health check endpoint (`/api/agents/status`)

**Phase 2 Example:**
1. Market Analyst subscribes to WebSocket callbacks
2. Market Analyst analyzes ticker data (basic: price change, volume)
3. Market Analyst publishes to `Channels.AI_DECISIONS`
4. Verify Orchestrator receives insights

**Phase 3 Example:**
1. Create `TradeExecutorAgent` class
2. Subscribe to `Channels.TRADE_SIGNALS`
3. Route to Paper Trading Engine
4. Verify trades execute and persist
5. Add Trade Executor to Agent Manager

## Integration Points

### FastAPI ↔ Agents

| Endpoint | Interacts With | Purpose |
|----------|---------------|---------|
| `GET /api/agents/status` | Agent Manager | Check which agents are running |
| `POST /api/agents/start` | Agent Manager | Start all agents (manual trigger) |
| `POST /api/agents/stop` | Agent Manager | Stop all agents (emergency stop) |
| `POST /api/trading/pause` | Trading Control | Pause autonomous trading |
| `POST /api/trading/resume` | Trading Control | Resume autonomous trading |
| `GET /api/positions/paper` | Paper Trading Engine | Current virtual positions |
| `GET /api/trades/paper` | Database | Historical paper trades |
| `POST /api/chat` | Orchestrator (via message queue) | AI chat interface |

### Celery ↔ Agents

| Task | Triggered By | Purpose |
|------|-------------|---------|
| `log_system_event` | Any agent | Async logging to database |
| `sync_manual_trades` | Celery Beat (every 5 min) | Import manual Kraken trades |
| `cleanup_expired_sessions` | Celery Beat (hourly) | Database maintenance |
| `reconcile_positions` | Agent Manager (on startup) | Load positions from DB |

**Note:** Agents run in FastAPI process (asyncio), not in Celery workers. Celery is only for background tasks.

### Redis ↔ Agents

| Use Case | How |
|----------|-----|
| Message Queue | Pub/Sub channels for agent communication |
| Decision Cooldown | Store `symbol:timestamp` with TTL=120s |
| Agent Health | Heartbeat keys with TTL=30s |
| Market Data Cache | Store recent price candles |

## Patterns to Follow

### Pattern 1: Agent Lifecycle Hook

**What:** Use `on_start()` and `on_stop()` for setup/teardown.

**When:** Every agent needs initialization (subscribe to channels, load config) and cleanup (unsubscribe, checkpoint state).

**Example:**
```python
class MarketAnalystAgent(BaseAgent):
    async def on_start(self):
        # Subscribe to message queue
        await message_queue.subscribe(
            Channels.MARKET_DATA,
            self._handle_market_data
        )

        # Register WebSocket callback
        kraken_ws.subscribe_ticker(
            pairs=["BTC/USD", "ETH/USD"],
            callback=self._on_ticker_update
        )

        logger.info("Market Analyst started")

    async def on_stop(self):
        # Unsubscribe
        await message_queue.unsubscribe(Channels.MARKET_DATA)

        # Checkpoint analysis state
        await self._save_state()

        logger.info("Market Analyst stopped")
```

### Pattern 2: Circuit Breaker for External Services

**What:** Prevent cascading failures when external service (Kraken API, Redis) is down.

**When:** Any code that calls external APIs.

**Example:**
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = "closed"  # closed | open | half_open

    def is_open(self):
        if self.state == "open":
            # Try recovery after timeout
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half_open"
                return False
            return True
        return False

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "open"
            logger.warning("Circuit breaker opened")

    def record_success(self):
        self.failures = 0
        if self.state == "half_open":
            self.state = "closed"
            logger.info("Circuit breaker closed")
```

### Pattern 3: Graceful Degradation

**What:** System continues operating with reduced functionality when component fails.

**When:** Non-critical components (sentiment analysis, chat) fail but trading should continue.

**Example:**
```python
# In Orchestrator
async def _maybe_add_sentiment(self, context: Dict[str, Any]):
    """Add sentiment data if available, skip if service down."""
    try:
        sentiment = await self._fetch_sentiment_score()
        context["sentiment"] = sentiment
    except SentimentServiceUnavailable:
        logger.warning("Sentiment service unavailable, continuing without it")
        # Trading decision proceeds without sentiment data
```

### Pattern 4: Idempotent Message Handling

**What:** Handling the same message multiple times produces same result.

**When:** Redis pub/sub may deliver messages more than once.

**Example:**
```python
async def _handle_trade_signal(self, signal: Dict[str, Any]):
    """Execute trade signal idempotently."""
    signal_id = signal.get("signal_id")

    # Check if already processed
    if await self._is_signal_processed(signal_id):
        logger.debug(f"Signal {signal_id} already processed, skipping")
        return

    # Execute trade
    result = await self._execute_trade(signal)

    # Mark as processed
    await self._mark_signal_processed(signal_id)
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Tight Coupling Between Agents

**What:** Agent A directly calls Agent B's methods instead of using message queue.

**Why bad:** Creates hidden dependencies, makes agents non-replaceable, breaks async boundaries.

**Instead:**
```python
# BAD
class OrchestratorAgent:
    def __init__(self):
        self.market_analyst = MarketAnalystAgent()

    async def run(self):
        insight = self.market_analyst.get_latest_insight()  # Direct call

# GOOD
class OrchestratorAgent:
    async def on_start(self):
        await message_queue.subscribe(
            Channels.AI_DECISIONS,
            self._handle_agent_decision
        )

    async def _handle_agent_decision(self, payload: Dict[str, Any]):
        # Receive insight via message queue
```

### Anti-Pattern 2: Blocking I/O in Async Context

**What:** Using synchronous DB calls, requests, or time.sleep() in async functions.

**Why bad:** Blocks event loop, prevents other agents from running.

**Instead:**
```python
# BAD
async def run(self):
    time.sleep(10)  # Blocks entire event loop!
    db = SessionLocal()
    trades = db.query(Trade).all()  # Sync DB call in async context

# GOOD
async def run(self):
    await asyncio.sleep(10)  # Non-blocking
    trades = await asyncio.to_thread(self._get_trades)  # Offload to thread

def _get_trades(self):
    db = SessionLocal()
    return db.query(Trade).all()
```

### Anti-Pattern 3: Unbounded In-Memory State

**What:** Caching all price history, all trade signals, all insights in memory forever.

**Why bad:** Memory grows unbounded, crashes on long-running instances.

**Instead:**
```python
# BAD
class MarketAnalystAgent:
    def __init__(self):
        self.price_history = []  # Grows forever

    async def _on_ticker_update(self, ticker):
        self.price_history.append(ticker.last)

# GOOD
class MarketAnalystAgent:
    def __init__(self):
        # Limited to last 200 prices
        self.price_history = deque(maxlen=200)

    async def _on_ticker_update(self, ticker):
        self.price_history.append(ticker.last)
```

### Anti-Pattern 4: Silent Failure in Async Tasks

**What:** Creating background tasks with `asyncio.create_task()` and not awaiting them or handling exceptions.

**Why bad:** Errors get swallowed, tasks die silently, system state becomes inconsistent.

**Instead:**
```python
# BAD
asyncio.create_task(self._background_job())  # Fire and forget

# GOOD
self._task = asyncio.create_task(self._background_job())

# In on_stop():
if self._task:
    self._task.cancel()
    try:
        await self._task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Background task failed: {e}")
```

### Anti-Pattern 5: Hardcoded Configuration

**What:** Magic numbers (cooldown=120, position_limit=5) scattered throughout code.

**Why bad:** Hard to tune, hard to test with different configs.

**Instead:**
```python
# BAD
if (now - last_decision) < 120:  # What is 120?
    return

# GOOD
class OrchestratorConfig:
    DECISION_COOLDOWN_SECONDS = 120
    MAX_POSITIONS_PER_SYMBOL = 5
    POSITION_SIZE_PCT = 1.0

config = OrchestratorConfig()

if (now - last_decision) < config.DECISION_COOLDOWN_SECONDS:
    return
```

## Recommended Build Order

Based on component dependencies:

1. **Phase 1: Agent Infrastructure** (Week 1)
   - Create Agent Manager
   - Wire to FastAPI lifespan
   - Add `/api/agents/status` endpoint
   - Test with Orchestrator only

2. **Phase 2: Market Data Flow** (Week 1-2)
   - Implement Market Analyst agent
   - Subscribe to WebSocket callbacks
   - Publish insights to message queue
   - Verify Orchestrator receives

3. **Phase 3: Trade Execution** (Week 2)
   - Implement Trade Executor agent
   - Subscribe to trade signals
   - Execute via Paper Trading Engine
   - Persist to database

4. **Phase 4: Risk Management** (Week 3)
   - Implement Risk Monitor agent
   - Define risk limits (position size, exposure, drawdown)
   - Enforce limits via circuit breaker
   - Add pause/resume logic

5. **Phase 5: State Persistence** (Week 3-4)
   - Add positions table to DB
   - Checkpoint positions on trade
   - Reconcile on startup
   - Test full restart cycle

6. **Phase 6: Additional Agents** (Week 4+)
   - Strategy Optimizer (scheduled optimization)
   - Sentiment Agent (news/social data)
   - Wire to Orchestrator

7. **Phase 7: Live Trading** (Optional, Week 5+)
   - Add Kraken order management
   - Implement partial fill handling
   - Add live trading safety checks
   - Manual approval workflow

## Sources

**Existing Codebase Analysis:**
- `/home/packnation82/projects/CryptoTrader/backend/agents/base.py` - Agent base class architecture
- `/home/packnation82/projects/CryptoTrader/backend/agents/orchestrator.py` - Orchestrator implementation (message queue, decision logic)
- `/home/packnation82/projects/CryptoTrader/backend/core/message_queue.py` - Redis pub/sub implementation
- `/home/packnation82/projects/CryptoTrader/backend/core/paper_trading.py` - Paper trading engine with state management
- `/home/packnation82/projects/CryptoTrader/backend/services/kraken_ws.py` - WebSocket with auto-reconnection
- `/home/packnation82/projects/CryptoTrader/backend/core/celery_app.py` - Background task configuration

**Architecture Patterns (Training Data - Medium Confidence):**
- Event-driven architecture for real-time trading systems
- Circuit breaker pattern for external service failures
- Pub/sub messaging for agent coordination
- State reconciliation on restart
- Hybrid scheduled + event-driven execution loops

**Confidence Assessment:**
- Existing codebase analysis: HIGH (directly inspected files)
- Autonomous loop architecture: MEDIUM (derived from patterns, not verified with current tools)
- Exchange failure handling: MEDIUM (standard patterns, but Kraken-specific details unverified)
- Multi-agent coordination: MEDIUM (based on message queue patterns)

**Gaps:**
- Specific Kraken API error codes and rate limits (need official docs)
- Optimal decision cooldown timing (need backtesting)
- Redis performance under high message volume (need load testing)
