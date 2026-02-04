# Technology Stack - Autonomous Trading Components

**Project:** CryptoTrader Autonomous Trading Engine
**Researched:** 2026-02-04
**Confidence:** MEDIUM (based on training data through Jan 2025, needs verification with current docs)

## Executive Summary

Your existing stack (FastAPI, React, Celery+Redis, krakenex, SQLAlchemy/SQLite) provides the foundation. To make the trading bot actually autonomous, you need:

1. **Scheduling/Orchestration**: APScheduler or Celery Beat for continuous agent execution
2. **Backtesting**: Backtrader or vectorbt for strategy validation
3. **Paper Trading**: Custom engine using your existing krakenex wrapper
4. **Order Management**: Python state machine library (transitions or python-statemachine)
5. **Technical Analysis**: TA-Lib or pandas-ta for signal generation
6. **Position Tracking**: SQLAlchemy models + real-time calculation engine
7. **Risk Management**: Custom logic + numpy for portfolio math

## Additional Stack Components

### Scheduling & Orchestration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **APScheduler** | 3.10+ | Agent execution scheduler | Lightweight, supports cron-like scheduling, runs in-process with FastAPI. Better than Celery Beat for this use case because trading agents need sub-minute granularity and APScheduler integrates cleanly with FastAPI lifecycle. |
| Celery Beat | 5.3+ | Alternative scheduler | Already have Celery/Redis. Use if you want distributed scheduling. More complex but handles failure recovery better. |

**Recommendation: APScheduler** for initial implementation. Easier to reason about, runs alongside FastAPI, supports:
- Interval-based triggers (every 30 seconds)
- Cron-like schedules (market open/close)
- One-off delayed tasks (stop-loss triggers)

**Installation:**
```bash
pip install apscheduler==3.10.4
```

**Rationale:** Trading bots need tight execution loops (sub-minute). APScheduler's BackgroundScheduler integrates with FastAPI's startup/shutdown events, giving you precise control. Celery Beat adds unnecessary complexity unless you need distributed workers.

**Confidence:** HIGH (APScheduler is mature and well-documented)

---

### Backtesting Frameworks

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **Backtrader** | 1.9.78+ | Strategy backtesting | Industry standard for Python algo trading. Event-driven architecture matches your live trading loop. Supports multiple data feeds, commission models, slippage simulation. |
| vectorbt | 0.26+ | Vectorized backtesting | Fast for simple strategies using numpy operations. Less flexible than Backtrader but 10-100x faster for certain use cases. |
| Zipline | 3.0+ | Algorithmic trading library | Quantopian legacy, less active development. Avoid unless you need specific features. |

**Recommendation: Backtrader** as primary framework because:
- Event-driven architecture mirrors live trading
- Supports complex multi-timeframe strategies
- Built-in position sizing and risk management
- Easy to translate backtest code to live execution

**Use vectorbt for:** Fast parameter optimization sweeps before running full Backtrader validation.

**Installation:**
```bash
pip install backtrader==1.9.78.123
pip install vectorbt==0.26.0  # optional, for fast optimization
```

**Rationale:** Your AI agents will generate trading signals based on market analysis. Backtrader lets you validate those strategies against historical data before risking capital. The framework's Cerebro engine and Strategy classes provide a clean separation between signal generation and execution logic.

**Confidence:** HIGH (Backtrader is well-established in algo trading community)

---

### Technical Analysis / Signal Processing

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **TA-Lib** | 0.4.28+ | Technical indicators (RSI, MACD, Bollinger Bands) | When you need battle-tested, C-optimized indicators. Requires system-level install. |
| **pandas-ta** | 0.3.14b | Pure Python indicators | Easier to install, slower but sufficient for crypto trading frequencies. No system dependencies. |
| **numpy** | 1.26+ | Custom calculations | Already have it. Use for custom signal math. |

**Recommendation: pandas-ta** because:
- No system dependencies (TA-Lib requires C libs)
- Active development, crypto-friendly
- Pure Python makes debugging easier
- Performance is fine for 1-minute crypto bars

**Installation:**
```bash
pip install pandas-ta==0.3.14b0
```

**Rationale:** Your AI agents need numeric signals (RSI, moving averages, volume indicators) to make decisions. pandas-ta provides 130+ indicators and integrates seamlessly with pandas DataFrames from your Kraken API.

**Confidence:** MEDIUM (pandas-ta is actively maintained but less battle-tested than TA-Lib)

---

### Paper Trading Engine

| Approach | Complexity | Why |
|----------|-----------|-----|
| **Custom simulation using krakenex** | Low | Recommended. Use your existing krakenex wrapper to fetch prices, simulate fills, track virtual positions in database. |
| ccxt paper trading mode | Medium | CCXT has unified API across exchanges but adds dependency. Overkill if you're only supporting Kraken. |
| Backtrader live paper mode | Medium | Reuse Backtrader for both backtest and paper trading. Cleaner but requires learning Backtrader's broker abstraction. |

**Recommendation: Custom simulation engine** because:
- You already have krakenex integration
- Full control over fill simulation logic
- Easier to transition to live trading (same code paths)
- SQLAlchemy models track paper positions alongside real ones

**Implementation strategy:**
```python
# Shared order execution logic
class OrderExecutor:
    def __init__(self, mode: str):  # 'paper' or 'live'
        self.mode = mode

    async def execute_order(self, order):
        if self.mode == 'paper':
            return await self._simulate_fill(order)
        else:
            return await self._execute_live(order)
```

Store paper trades in same `trades` table with `is_paper: bool` flag.

**Confidence:** HIGH (custom approach gives you maximum control)

---

### Order Management & State Machines

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| **transitions** | 0.9.0+ | Finite state machines | Clean DSL for order lifecycle (pending → submitted → filled → closed). Supports async, callbacks, and state validation. |
| python-statemachine | 2.1+ | Alternative FSM library | More Pythonic API but less mature than transitions. |

**Recommendation: transitions** for order state management because:
- Orders have complex lifecycles: `new → validated → submitted → partial_fill → filled → settled`
- Prevents invalid state transitions (can't cancel a filled order)
- Triggers callbacks on state changes (update database, notify WebSocket)

**Installation:**
```bash
pip install transitions==0.9.0
```

**Example usage:**
```python
from transitions import Machine

class OrderStateMachine:
    states = ['new', 'validated', 'submitted', 'partial_fill', 'filled', 'cancelled', 'rejected']

    transitions = [
        {'trigger': 'validate', 'source': 'new', 'dest': 'validated'},
        {'trigger': 'submit', 'source': 'validated', 'dest': 'submitted'},
        {'trigger': 'fill', 'source': ['submitted', 'partial_fill'], 'dest': 'filled'},
        # ... more transitions
    ]
```

**Rationale:** Trading orders are stateful entities. A state machine prevents bugs like trying to modify a filled order or double-submitting. The callbacks integrate cleanly with your SQLAlchemy models and WebSocket notifications.

**Confidence:** HIGH (transitions is mature and widely used)

---

### Position & Portfolio Tracking

| Component | Implementation | Purpose |
|-----------|---------------|---------|
| **Real-time calculations** | Custom service using SQLAlchemy + numpy | Track open positions, P&L, margin, portfolio value |
| **Database models** | Extend existing SQLAlchemy schema | `positions`, `portfolio_snapshots`, `trades` tables |
| **WebSocket updates** | Use existing WebSocket infrastructure | Push position updates to frontend in real-time |

**Recommendation: Custom portfolio service** because:
- Your requirements are specific (crypto, Kraken, AI agents)
- SQLAlchemy + numpy gives you full control
- Reuse existing database and WebSocket infrastructure

**Key calculations needed:**
```python
class PortfolioService:
    def get_current_positions(self) -> List[Position]:
        """Aggregate trades into open positions"""

    def calculate_unrealized_pnl(self, position: Position, current_price: float) -> float:
        """Mark-to-market P&L"""

    def calculate_portfolio_value(self) -> float:
        """Cash + position values"""

    def check_margin_requirements(self) -> bool:
        """Prevent over-leveraging"""
```

**Dependencies:**
```bash
# Already have these
pip install sqlalchemy numpy pandas
```

**Confidence:** HIGH (standard approach for trading systems)

---

### Risk Management

| Component | Library | Purpose |
|-----------|---------|---------|
| **Position sizing** | Custom logic + numpy | Kelly criterion, fixed fractional, volatility-based sizing |
| **Risk limits** | Python business logic | Max position size, max daily loss, correlation limits |
| **Volatility calculation** | pandas-ta | ATR, standard deviation, Bollinger width |

**Recommendation: Custom risk management module** because:
- Risk rules are business-critical and specific to your strategy
- Library abstractions add complexity without value
- Direct implementation makes testing easier

**Implementation structure:**
```python
class RiskManager:
    def __init__(self, config: RiskConfig):
        self.max_position_size = config.max_position_size
        self.max_daily_loss = config.max_daily_loss
        self.max_open_positions = config.max_open_positions

    def validate_order(self, order: Order) -> Tuple[bool, str]:
        """Check if order violates risk limits"""

    def calculate_position_size(self, signal_strength: float, volatility: float) -> float:
        """Dynamic position sizing based on signal and risk"""

    def should_close_positions(self, portfolio: Portfolio) -> bool:
        """Check daily loss limits, margin calls"""
```

**Confidence:** HIGH (risk management must be custom to your requirements)

---

### Data Storage & Time Series

| Technology | Current | Recommendation |
|------------|---------|----------------|
| **SQLite** | In use | Keep for transactional data (orders, trades, accounts) |
| **TimescaleDB** | Not used | Consider for OHLCV data if you store historical bars |
| **Redis** | In use | Use for real-time market data cache |

**Recommendation: Keep SQLite + Redis** for now because:
- SQLite handles transaction volumes fine for single-user trading
- Redis already caches real-time prices from Kraken
- TimescaleDB adds complexity without clear benefit until you're storing millions of bars

**When to upgrade to TimescaleDB:**
- Storing tick data (every trade)
- Running complex time-series queries
- Multi-user deployment

**Confidence:** HIGH (SQLite is proven for this scale)

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Scheduler | APScheduler | Celery Beat | Celery Beat is overkill for single-instance deployment. Use it if you need distributed workers. |
| Backtesting | Backtrader | Zipline | Zipline development has stalled. Backtrader is more active. |
| Technical Analysis | pandas-ta | TA-Lib | TA-Lib requires system dependencies. pandas-ta is pure Python and easier to deploy. |
| Paper Trading | Custom engine | ccxt paper mode | ccxt adds unnecessary dependency when you only support Kraken. |
| State Machines | transitions | python-statemachine | transitions has more GitHub stars and better async support. |
| Time Series DB | SQLite | TimescaleDB | TimescaleDB is overkill until you're storing massive amounts of tick data. |

---

## Installation Script

```bash
# Scheduling
pip install apscheduler==3.10.4

# Backtesting
pip install backtrader==1.9.78.123
pip install vectorbt==0.26.0  # optional

# Technical Analysis
pip install pandas-ta==0.3.14b0

# State Machines
pip install transitions==0.9.0

# Math & Data (likely already installed)
pip install numpy>=1.26.0
pip install pandas>=2.1.0
pip install scipy>=1.11.0

# Testing
pip install pytest-asyncio  # for testing async trading logic
pip install freezegun  # for time-dependent backtests
```

---

## Architecture Integration Points

### How new components fit with existing stack:

**FastAPI Integration:**
```python
# app/main.py
from apscheduler.schedulers.background import BackgroundScheduler

@app.on_event("startup")
async def startup_event():
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_trading_agents, 'interval', seconds=30)
    scheduler.start()
```

**Celery Integration:**
```python
# Alternative: use Celery for heavy backtests
from celery import Celery

@celery.task
def run_backtest(strategy_id: int, start_date: str, end_date: str):
    # Long-running backtest in background worker
```

**SQLAlchemy Models:**
```python
class Position(Base):
    __tablename__ = 'positions'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    quantity = Column(Float)
    entry_price = Column(Float)
    is_paper = Column(Boolean, default=True)

class Trade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True)
    position_id = Column(Integer, ForeignKey('positions.id'))
    executed_at = Column(DateTime)
    is_paper = Column(Boolean, default=True)
```

**WebSocket Updates:**
```python
# Use existing WebSocket infrastructure
async def broadcast_position_update(position: Position):
    await websocket_manager.broadcast({
        'type': 'position_update',
        'data': position.to_dict()
    })
```

---

## Configuration Management

You'll need environment-based config for paper vs live trading:

```python
# config/trading.py
from pydantic import BaseSettings

class TradingConfig(BaseSettings):
    MODE: str = 'paper'  # 'paper' or 'live'
    EXECUTION_INTERVAL_SECONDS: int = 30
    MAX_POSITION_SIZE: float = 1000.0
    MAX_DAILY_LOSS: float = 100.0
    MAX_OPEN_POSITIONS: int = 5

    class Config:
        env_file = '.env'
```

---

## Development Phases

Suggested order to integrate new components:

### Phase 1: Signal Processing (Week 1)
- Install pandas-ta
- Build indicator calculation pipeline
- Test with historical Kraken data

### Phase 2: Backtesting (Week 2)
- Install Backtrader
- Create strategy templates
- Run backtests on sample strategies

### Phase 3: Paper Trading (Week 3)
- Build custom simulation engine
- Add SQLAlchemy models for paper positions
- Integrate with existing krakenex wrapper

### Phase 4: Order State Management (Week 4)
- Install transitions
- Define order state machine
- Add state validation to order flow

### Phase 5: Autonomous Execution (Week 5)
- Install APScheduler
- Create agent execution loop
- Wire up scheduling with FastAPI lifecycle

### Phase 6: Position & Risk Management (Week 6)
- Build portfolio tracking service
- Implement risk limits
- Add real-time P&L calculations

---

## Critical Dependencies

**Hard dependencies** (must install):
- APScheduler (agent scheduling)
- pandas-ta (technical indicators)
- transitions (order state management)

**Recommended dependencies** (should install):
- Backtrader (strategy validation)
- pytest-asyncio (testing async logic)

**Optional dependencies** (install if needed):
- vectorbt (fast optimization)
- TimescaleDB (high-frequency data storage)

---

## Known Issues & Gotchas

### APScheduler + FastAPI
**Issue:** Scheduler runs in background thread, database sessions aren't thread-safe
**Solution:** Use async scheduler or create new SQLAlchemy session per job:
```python
from sqlalchemy.orm import scoped_session

@scheduler.scheduled_job('interval', seconds=30)
def run_agents():
    session = scoped_session(SessionLocal)
    try:
        # trading logic
    finally:
        session.remove()
```

### Backtrader + AsyncIO
**Issue:** Backtrader is synchronous, your FastAPI app is async
**Solution:** Run backtests in Celery workers or use `asyncio.to_thread()`:
```python
result = await asyncio.to_thread(run_backtest, strategy)
```

### Paper Trading Fill Simulation
**Issue:** Naive fill simulation unrealistic (instant fills at exact price)
**Solution:** Add slippage model:
```python
def simulate_fill(order, current_price):
    slippage = 0.001  # 0.1% slippage
    if order.side == 'buy':
        fill_price = current_price * (1 + slippage)
    else:
        fill_price = current_price * (1 - slippage)
    return fill_price
```

### Time Zone Handling
**Issue:** Crypto markets are 24/7 but data timestamps vary
**Solution:** Normalize all timestamps to UTC in database:
```python
from datetime import datetime, timezone

executed_at = datetime.now(timezone.utc)
```

---

## Confidence Assessment

| Component | Confidence | Notes |
|-----------|------------|-------|
| APScheduler | HIGH | Mature library, well-documented |
| Backtrader | HIGH | Industry standard for algo trading |
| pandas-ta | MEDIUM | Less battle-tested than TA-Lib but actively maintained |
| transitions | HIGH | Mature FSM library |
| Custom paper trading | HIGH | Standard approach, full control |
| Custom risk management | HIGH | Must be custom to requirements |
| SQLite for positions | HIGH | Proven at this scale |

**Overall confidence: MEDIUM-HIGH**

Most recommendations are based on established patterns in the algo trading community. Main uncertainty is around pandas-ta (newer than TA-Lib) and specific version numbers (need to verify current releases).

---

## Verification Checklist

Before implementing, verify:

- [ ] APScheduler current version and async support
- [ ] Backtrader compatibility with Python 3.12
- [ ] pandas-ta latest stable release
- [ ] transitions async capabilities
- [ ] Kraken API rate limits for paper trading simulation
- [ ] SQLAlchemy async support for scheduler jobs

---

## Sources

**Note:** This research is based on training data through January 2025. Specific version numbers and library capabilities should be verified with:

- APScheduler: https://apscheduler.readthedocs.io/
- Backtrader: https://www.backtrader.com/docu/
- pandas-ta: https://github.com/twopirllc/pandas-ta
- transitions: https://github.com/pytransitions/transitions

**Confidence level:** MEDIUM (needs current documentation verification before implementation)
