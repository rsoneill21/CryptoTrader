# Phase 1: Infrastructure Hardening - Research

**Researched:** 2026-02-04
**Domain:** FastAPI infrastructure reliability (async DB, rate limiting, state persistence, error handling, pagination)
**Confidence:** HIGH

## Summary

Infrastructure hardening for a long-running autonomous trading system requires five critical improvements: (1) AsyncSession migration for true async database queries, (2) fail-closed rate limiting with circuit breaker patterns, (3) comprehensive paper trading state persistence using database-backed sessions, (4) structured exception hierarchies with RFC 9457-compliant error envelopes, and (5) cursor-based pagination for real-time trading data.

**Current state analysis:**
- Database layer uses sync `SessionLocal` with `get_db()` dependency — blocks event loop in async routes
- Rate limiter fails open when Redis is down (lines 46-47, 63-64 in `rate_limit.py`) — security vulnerability
- No paper trading state persistence — server restart loses all positions, cash balance, P&L
- Generic exception handling with minimal context — bare `except Exception` blocks throughout
- No pagination on list endpoints — `/api/trades/active` returns unbounded results

**Primary recommendation:** Migrate to AsyncSession with asyncpg (PostgreSQL) or aiosqlite (SQLite development) as priority #1, then implement fail-closed rate limiting, followed by state persistence, structured logging, and cursor pagination in parallel.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlalchemy[asyncio] | 2.0+ | Async ORM with AsyncSession | Industry standard for Python async DB; 3-5x throughput vs sync; native asyncpg support |
| asyncpg | 0.29+ | PostgreSQL async driver | 5x faster than psycopg3; native asyncio implementation; binary protocol for max performance |
| aiosqlite | 0.20+ | SQLite async driver (dev only) | Asyncio bridge for SQLite; thread-pool based; sufficient for development/testing |
| pybreaker | 1.0+ | Circuit breaker pattern | Production-tested circuit breaker with Redis backing; handles distributed systems |
| structlog | 25.x | Structured JSON logging | De facto standard for structured logs; Pydantic v2 integration; context vars support |
| asgi-correlation-id | 4.x | Request ID middleware | Automatic correlation ID generation/propagation; integrates with structlog |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-json-logger | 2.x | JSON log formatter | Alternative to structlog if simpler formatter needed |
| fastapi-problem-details | 0.1.4+ | RFC 9457 error responses | If strict RFC 9457 compliance required (current error.py is custom) |
| redis-py[hiredis] | 5.x | Redis client with C parser | Already in use; add hiredis for 10x parsing speed in circuit breaker |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| AsyncSession | asyncio.to_thread with sync Session | Thread pool overhead; 3-5x slower; defeats asyncio benefits |
| asyncpg | aiopg | aiopg is maintenance-mode; asyncpg is 5x faster and actively developed |
| cursor pagination | offset pagination | Offset breaks with real-time data inserts; O(n) performance degradation |
| pybreaker | Custom circuit breaker | Reinventing complex edge cases (half-open state, distributed coordination) |

**Installation:**
```bash
# Production (PostgreSQL)
pip install 'sqlalchemy[asyncio]>=2.0.0' asyncpg pybreaker structlog asgi-correlation-id 'redis[hiredis]>=5.0.0'

# Development (SQLite)
pip install 'sqlalchemy[asyncio]>=2.0.0' aiosqlite pybreaker structlog asgi-correlation-id 'redis[hiredis]>=5.0.0'
```

## Architecture Patterns

### Recommended Project Structure
```
backend/
├── db/
│   ├── database.py          # Async engine, session factory, Base
│   ├── models.py            # Declarative models with AsyncAttrs
│   └── migrations/          # Alembic migrations (supports async)
├── core/
│   ├── rate_limit.py        # RateLimiter with circuit breaker
│   ├── exceptions.py        # Exception hierarchy (NEW)
│   └── logging_config.py    # Structlog configuration (NEW)
├── api/
│   ├── errors.py            # Already has envelope pattern, enhance
│   └── *.py                 # Routes with async def and AsyncSession
├── services/
│   ├── paper_trading/       # State manager (NEW)
│   │   ├── state.py         # Session state model
│   │   ├── persistence.py   # DB persistence layer
│   │   └── manager.py       # State lifecycle coordinator
│   └── circuit_breakers.py  # Shared circuit breaker instances (NEW)
```

### Pattern 1: AsyncSession with Dependency Injection
**What:** Replace sync `get_db()` with async `get_async_db()` using `async_sessionmaker`
**When to use:** All async routes that query the database
**Example:**
```python
# Source: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# database.py
DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"  # or sqlite+aiosqlite:///./file.db
async_engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Prevent attribute expiration after commit
)

async def get_async_db():
    """Async dependency that provides database session."""
    async with AsyncSessionLocal() as session:
        yield session

# api/trades.py
from sqlalchemy import select
from sqlalchemy.orm import selectinload

@router.get("/active")
async def list_active_trades(
    db: AsyncSession = Depends(get_async_db),  # Changed from Session
) -> List[ActiveTradeResponse]:
    # All DB operations require await
    result = await db.execute(
        select(Trade)
        .options(selectinload(Trade.orders))  # Eager load relationships
        .where(Trade.exit_time.is_(None))
        .order_by(Trade.entry_time.desc())
    )
    trades = result.scalars().all()
    return [_serialize_trade(t) for t in trades]
```

**Critical: Eager loading required** — Lazy loading fails in async context. Use `selectinload()` or `lazy="raise"` on relationships.

### Pattern 2: Fail-Closed Rate Limiter with Circuit Breaker
**What:** Rate limiter raises 503 when Redis is unavailable, preventing bypass of rate limits
**When to use:** Auth endpoints, sensitive operations, high-value API routes
**Example:**
```python
# Source: https://github.com/danielfm/pybreaker + custom integration
from pybreaker import CircuitBreaker
import redis.asyncio as redis

# core/circuit_breakers.py
redis_breaker = CircuitBreaker(
    fail_max=5,           # Open circuit after 5 failures
    timeout_duration=60,  # Try again after 60 seconds
    name="redis"
)

# core/rate_limit.py
async def get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL)
            await redis_breaker.call(redis_client.ping)  # Circuit breaker wrapped
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            # FAIL-CLOSED: return None to trigger 503
            return None
    return _redis_client

async def check_rate_limit(key: str, limit: int, window: int) -> bool:
    r = await get_redis()
    if not r:
        # FAIL-CLOSED: When Redis is down, deny requests
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiting service temporarily unavailable",
            headers={"Retry-After": "60"}  # Tell client when to retry
        )

    try:
        current = await r.incr(key)
        if current == 1:
            await r.expire(key, window)
        return current <= limit
    except Exception as e:
        logger.error(f"Redis error: {e}")
        # On Redis errors (not connection), fail-closed
        raise HTTPException(status_code=503, detail="Rate limiting unavailable")
```

**Why fail-closed:** User decision from CONTEXT.md. Fail-open allows unlimited requests during Redis outage — unacceptable for auth/trading endpoints in autonomous system.

### Pattern 3: Paper Trading State Persistence
**What:** Database-backed session state for paper trading (positions, cash, P&L, orders)
**When to use:** Paper trading mode; archived sessions for comparison
**Example:**
```python
# Source: Distributed cache pattern from https://www.geeksforgeeks.org/load-balancer-session-persistence/
# services/paper_trading/state.py
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, List, Optional

class PaperTradingSession(BaseModel):
    session_id: str
    created_at: datetime
    cash_balance: float
    open_positions: Dict[str, dict]  # symbol -> position details
    pending_orders: List[dict]
    trade_history: List[dict]
    pnl_snapshots: List[dict]
    is_active: bool
    last_updated: datetime

# db/models.py
class PaperTradingState(Base):
    __tablename__ = "paper_trading_states"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(36), unique=True, index=True)
    state_json = Column(JSON, nullable=False)  # Full session state
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    archived_at = Column(DateTime, nullable=True)

# services/paper_trading/manager.py
class PaperTradingManager:
    async def save_state(self, session: PaperTradingSession, db: AsyncSession):
        """Persist current session state to database."""
        result = await db.execute(
            select(PaperTradingState).where(
                PaperTradingState.session_id == session.session_id
            )
        )
        state_record = result.scalar_one_or_none()

        if state_record:
            state_record.state_json = session.model_dump(mode="json")
            state_record.updated_at = datetime.utcnow()
        else:
            state_record = PaperTradingState(
                session_id=session.session_id,
                state_json=session.model_dump(mode="json"),
            )
            db.add(state_record)

        await db.commit()

    async def load_active_session(self, db: AsyncSession) -> Optional[PaperTradingSession]:
        """Load most recent active session on startup."""
        result = await db.execute(
            select(PaperTradingState)
            .where(PaperTradingState.is_active == True)
            .order_by(PaperTradingState.updated_at.desc())
        )
        state_record = result.scalar_one_or_none()

        if state_record:
            return PaperTradingSession.model_validate(state_record.state_json)
        return None

    async def archive_session(self, session_id: str, db: AsyncSession):
        """Archive current session and allow starting fresh."""
        result = await db.execute(
            select(PaperTradingState).where(
                PaperTradingState.session_id == session_id
            )
        )
        state_record = result.scalar_one_or_none()

        if state_record:
            state_record.is_active = False
            state_record.archived_at = datetime.utcnow()
            await db.commit()
```

**Write timing decision:** User deferred to Claude's discretion. Recommendation: Write on every trade execution + periodic snapshots (every 5 minutes) + on shutdown. Paper trading is low-write-volume, so immediate writes are acceptable.

### Pattern 4: Structured Exception Hierarchy with RFC 9457 Envelope
**What:** Custom exception base classes with structured logging and standardized error responses
**When to use:** All API error cases — replace bare `except Exception` blocks
**Example:**
```python
# Source: https://medium.com/@ixbahy/level-up-your-fastapi-exception-handling-done-right-5db862038c7a
# core/exceptions.py
from fastapi import HTTPException
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger()

class BaseAppException(HTTPException):
    """Base exception with structured logging."""
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(status_code=status_code, detail={
            "code": error_code,
            "message": message,
            "details": details
        })

        # Structured log on exception creation
        logger.warning(
            "api_exception",
            error_code=error_code,
            message=message,
            status_code=status_code,
            details=details
        )

class DatabaseException(BaseAppException):
    """Database operation failed."""
    def __init__(self, message: str = "Database operation failed", details: Optional[Dict] = None):
        super().__init__(
            status_code=500,
            error_code="database_error",
            message=message,
            details=details
        )

class RateLimitException(BaseAppException):
    """Rate limit exceeded."""
    def __init__(self, retry_after: int = 60):
        super().__init__(
            status_code=429,
            error_code="rate_limit_exceeded",
            message="Too many requests",
            details={"retry_after": retry_after}
        )
        self.headers = {"Retry-After": str(retry_after)}

class ServiceUnavailableException(BaseAppException):
    """External service temporarily unavailable."""
    def __init__(self, service: str, retry_after: int = 60):
        super().__init__(
            status_code=503,
            error_code="service_unavailable",
            message=f"{service} temporarily unavailable",
            details={"service": service, "retry_after": retry_after}
        )

# api/trades.py example usage
try:
    await db.commit()
except SQLAlchemyError as exc:
    await db.rollback()
    raise DatabaseException(
        message="Failed to create trade",
        details={"trade_id": trade.id, "symbol": trade.symbol}
    ) from exc
```

**Granularity decision:** User deferred to Claude's discretion. Recommendation: 3-level hierarchy (Base -> Category -> Specific). Categories: `DatabaseException`, `RateLimitException`, `ServiceUnavailableException`, `ValidationException`. Specific exceptions inherit from categories.

### Pattern 5: Cursor-Based Pagination for Trading Data
**What:** Use timestamp + ID cursor for consistent pagination of real-time trading data
**When to use:** `/api/trades`, `/api/strategies`, `/api/alerts` list endpoints
**Example:**
```python
# Source: https://www.merge.dev/blog/cursor-pagination
from pydantic import BaseModel
from typing import Optional, List, Generic, TypeVar
from datetime import datetime
import base64
import json

T = TypeVar('T')

class CursorPage(BaseModel, Generic[T]):
    """Cursor-paginated response envelope."""
    items: List[T]
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
    total_count: Optional[int] = None  # Optional: expensive for large tables

def encode_cursor(timestamp: datetime, id: int) -> str:
    """Encode cursor from timestamp + ID."""
    cursor_data = {"ts": timestamp.isoformat(), "id": id}
    return base64.urlsafe_b64encode(json.dumps(cursor_data).encode()).decode()

def decode_cursor(cursor: str) -> tuple[datetime, int]:
    """Decode cursor to timestamp + ID."""
    cursor_data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    return datetime.fromisoformat(cursor_data["ts"]), cursor_data["id"]

@router.get("/trades", response_model=CursorPage[TradeResponse])
async def list_trades(
    cursor: Optional[str] = None,
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    """List trades with cursor pagination."""
    query = select(Trade).order_by(Trade.created_at.desc(), Trade.id.desc())

    if cursor:
        cursor_ts, cursor_id = decode_cursor(cursor)
        # Cursor navigation: (timestamp < cursor_ts) OR (timestamp = cursor_ts AND id < cursor_id)
        query = query.where(
            or_(
                Trade.created_at < cursor_ts,
                and_(Trade.created_at == cursor_ts, Trade.id < cursor_id)
            )
        )

    # Fetch limit + 1 to determine if there's a next page
    result = await db.execute(query.limit(limit + 1))
    trades = result.scalars().all()

    has_next = len(trades) > limit
    items = trades[:limit]

    next_cursor = None
    if has_next and items:
        last = items[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return CursorPage(
        items=[_serialize_trade(t) for t in items],
        next_cursor=next_cursor
    )
```

**Why cursor over offset:** Trading data changes in real-time. Offset pagination causes phantom records (skip items) or duplicates when new trades inserted. Cursor-based is O(1) performance vs O(n) for large offsets. Recommendation from multiple sources for real-time/frequently-changing data.

**User decision:** Pagination style is Claude's discretion. Recommendation: Cursor for trading data; offset acceptable for settings/config endpoints that rarely change.

### Pattern 6: Structured JSON Logging with Correlation IDs
**What:** JSON-formatted logs with automatic request correlation and context propagation
**When to use:** All API requests, background tasks, exception handlers
**Example:**
```python
# Source: https://www.sheshbabu.com/posts/fastapi-structured-json-logging/
# core/logging_config.py
import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI

def configure_logging():
    """Configure structlog for JSON output with correlation IDs."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()  # JSON output for production
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

def setup_middleware(app: FastAPI):
    """Add correlation ID middleware."""
    app.add_middleware(
        CorrelationIdMiddleware,
        header_name="X-Request-ID",
        generator=lambda: str(uuid.uuid4()),
        transformer=lambda id: id,
    )

# Usage in routes
import structlog
logger = structlog.get_logger()

@router.post("/trades")
async def create_trade(request: CreateTradeRequest, db: AsyncSession = Depends(get_async_db)):
    # Correlation ID automatically included in all logs during this request
    logger.info("creating_trade", symbol=request.symbol, quantity=request.quantity)

    try:
        trade = Trade(**request.dict())
        db.add(trade)
        await db.commit()
        logger.info("trade_created", trade_id=trade.id, symbol=trade.symbol)
        return trade
    except Exception as exc:
        logger.error("trade_creation_failed", error=str(exc), exc_info=True)
        raise DatabaseException(message="Failed to create trade") from exc

# Output (JSON):
# {"event": "creating_trade", "symbol": "BTC/USD", "quantity": 0.1, "level": "info", "timestamp": "2026-02-04T15:30:00.123Z", "request_id": "a1b2c3d4-..."}
# {"event": "trade_created", "trade_id": 123, "symbol": "BTC/USD", "level": "info", "timestamp": "2026-02-04T15:30:00.456Z", "request_id": "a1b2c3d4-..."}
```

**Log rotation decision:** User specified file + stdout. Use `RotatingFileHandler` with 10MB max size, 5 backup files. Docker/K8s deployments can rely on stdout only.

### Anti-Patterns to Avoid
- **asyncio.to_thread wrapper for DB**: Defeats async benefits, adds thread pool overhead, 3-5x slower
- **Lazy loading relationships in async**: Fails at runtime — use `selectinload()` or `lazy="raise"`
- **Fail-open rate limiting**: Security vulnerability when Redis down — always fail-closed for sensitive endpoints
- **Offset pagination on trading data**: Causes phantom records/duplicates with real-time inserts
- **Generic `except Exception`**: Hides error types, prevents proper client handling — use exception hierarchy
- **Print statements or string formatting in logs**: Not machine-parseable — use structured JSON logs

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Circuit breaker for Redis | Custom retry logic with backoff | pybreaker with Redis storage | Half-open state transitions, distributed coordination, failure detection window are complex; pybreaker handles edge cases |
| Correlation ID propagation | Manual header parsing/injection | asgi-correlation-id middleware | Context vars cleanup, header extraction/generation, response injection, downstream propagation all automated |
| JSON log formatting | Custom dict -> json.dumps | structlog or python-json-logger | Exception formatting, context merging, sensitive data redaction, performance optimization already solved |
| Cursor encoding/decoding | Base64 encode timestamps | Dedicated pagination library or pattern | Edge cases: null cursors, invalid base64, timezone handling, backward pagination all error-prone |
| Async DB connection pooling | Manual pool management | SQLAlchemy async_engine with pool_pre_ping | Connection health checks, pool sizing, overflow handling, timeout management are error-prone |
| Rate limit key generation | String concatenation | Standardized key builder | Key collision, namespace pollution, expiration tracking, distributed coordination require careful design |

**Key insight:** Infrastructure patterns like circuit breakers and correlation tracing have subtle edge cases that cause production outages. SQLAlchemy's async engine handles connection lifecycle pitfalls (stale connections, pool exhaustion, transaction rollback races). Use battle-tested libraries over custom implementations.

## Common Pitfalls

### Pitfall 1: Mixing Sync and Async Database Code
**What goes wrong:** Calling sync `db.query()` in async route blocks event loop; calling async `await db.execute()` without await raises runtime error
**Why it happens:** SQLAlchemy 2.0 supports both sync and async, but they're incompatible — can't mix Session and AsyncSession
**How to avoid:**
- Use AsyncSession consistently in all async routes
- Add type hints: `db: AsyncSession` forces correct usage
- Enable SQLAlchemy warnings to catch sync calls in async context
**Warning signs:** "RuntimeWarning: coroutine was never awaited", slow response times under load, event loop blocking

### Pitfall 2: Lazy Loading Relationships in AsyncSession
**What goes wrong:** Accessing `trade.orders` on lazy-loaded relationship fails with "greenlet_spawn not called in an async context"
**Why it happens:** Lazy loading requires synchronous query execution, which is forbidden in async context
**How to avoid:**
- Use `selectinload()` or `joinedload()` for all relationship access
- Set `lazy="raise"` on relationships to fail fast during development
- Use `expire_on_commit=False` in session maker to prevent post-commit attribute access
**Warning signs:** "greenlet" errors, "AsyncAttrs" warnings, relationship access raising DetachedInstanceError

### Pitfall 3: Rate Limiter Fail-Open Masking Redis Failures
**What goes wrong:** Redis goes down, rate limiter returns True (allow), attackers bypass all rate limits during outage
**Why it happens:** Default behavior prioritizes availability over security — "fail open" lets traffic through
**How to avoid:**
- Explicitly raise HTTPException(503) when Redis connection fails
- Use circuit breaker to stop hammering dead Redis
- Add monitoring/alerting for Redis failures (don't rely on failed requests as signal)
- Test failure mode: kill Redis, verify endpoints return 503 not 200
**Warning signs:** No rate limit violations during Redis outage, logs show "Redis error" but requests succeed, circuit breaker never opens

### Pitfall 4: Offset Pagination on Real-Time Trading Data
**What goes wrong:** User on page 2 sees duplicates from page 1 (or misses records entirely) when new trades insert
**Why it happens:** Offset 25 means "skip first 25 rows" — but row 26 becomes row 27 when new trade inserts at top
**How to avoid:**
- Use cursor pagination with (timestamp, id) cursor for all trading list endpoints
- Reserve offset pagination for admin/config tables that rarely change
- Add "snapshot" timestamp to offset pagination if cursor not feasible
**Warning signs:** Users report "seeing same trade twice" or "trade disappeared from list", pagination flakiness under load

### Pitfall 5: Missing Database Indexes on Foreign Keys and Timestamps
**What goes wrong:** Queries slow down as data grows; `WHERE user_id = X` or `ORDER BY created_at DESC` performs full table scan
**Why it happens:** SQLAlchemy doesn't auto-index foreign keys (unlike some ORMs); timestamp sorting without index is O(n log n)
**How to avoid:**
- Add `index=True` to all foreign key columns: `user_id = Column(Integer, ForeignKey('users.id'), index=True)`
- Index timestamp columns used in ORDER BY or WHERE: `created_at = Column(DateTime, index=True)`
- Composite index for cursor pagination: `Index('ix_trades_cursor', 'created_at', 'id')`
- Run `EXPLAIN ANALYZE` on production queries to verify index usage
**Warning signs:** Query time increases with table size, database CPU spikes, `EXPLAIN` shows "Seq Scan" instead of "Index Scan"

### Pitfall 6: Paper Trading State Loss on Unexpected Shutdown
**What goes wrong:** Server crashes during trade execution, loses open position and cash balance, restart shows empty portfolio
**Why it happens:** In-memory state not persisted; only writes to DB on clean shutdown (which didn't happen)
**How to avoid:**
- Write state to DB immediately after every trade execution (not just on shutdown)
- Add periodic state snapshots every 5 minutes as backup
- Load last known state on startup and require user confirmation to resume
- Archive old sessions before starting new session (don't overwrite)
**Warning signs:** "Cash balance reset to $10,000 after crash", "lost open position after restart", "P&L doesn't match expected"

### Pitfall 7: Structured Logging Missing Request Context
**What goes wrong:** 20 concurrent requests all log "creating trade", impossible to correlate which logs belong to which request
**Why it happens:** No correlation ID — logs from different requests interleave in chronological order without grouping
**How to avoid:**
- Use `asgi-correlation-id` middleware to inject X-Request-ID header
- Configure structlog with `contextvars.merge_contextvars` processor
- Middleware automatically propagates correlation ID to all logs in request scope
- Include correlation ID in error responses for client-side debugging
**Warning signs:** "Can't trace request flow", "logs from multiple requests mixed together", debugging requires timestamps only

## Code Examples

Verified patterns from official sources:

### Async Database Migration
```python
# Source: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
# OLD: Sync pattern (blocks event loop)
from sqlalchemy.orm import Session

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/trades")
def list_trades(db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(Trade.exit_time.is_(None)).all()  # BLOCKS
    return trades

# NEW: Async pattern (non-blocking)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"
async_engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

async def get_async_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/trades")
async def list_trades(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(
        select(Trade).where(Trade.exit_time.is_(None))
    )
    trades = result.scalars().all()
    return trades
```

### Fail-Closed Rate Limiting
```python
# Source: https://github.com/danielfm/pybreaker
# OLD: Fail-open (security issue)
async def check_rate_limit(key: str, limit: int, window: int) -> bool:
    r = await get_redis()
    if not r:
        return True  # FAIL-OPEN: allows unlimited requests
    # ...

# NEW: Fail-closed with circuit breaker
from pybreaker import CircuitBreaker

redis_breaker = CircuitBreaker(fail_max=5, timeout_duration=60)

async def check_rate_limit(key: str, limit: int, window: int) -> bool:
    try:
        r = await redis_breaker.call(get_redis)
        if not r:
            raise ServiceUnavailableException("rate_limiter", retry_after=60)

        current = await r.incr(key)
        if current == 1:
            await r.expire(key, window)

        if current > limit:
            return False
        return True
    except CircuitBreakerError:
        # Circuit open: Redis repeatedly failing
        raise ServiceUnavailableException("rate_limiter", retry_after=60)
```

### Cursor Pagination
```python
# Source: https://www.merge.dev/blog/cursor-pagination
from datetime import datetime
from typing import Optional
import base64
import json

def encode_cursor(timestamp: datetime, id: int) -> str:
    data = {"ts": timestamp.isoformat(), "id": id}
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()

def decode_cursor(cursor: str) -> tuple[datetime, int]:
    data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    return datetime.fromisoformat(data["ts"]), data["id"]

@router.get("/trades")
async def list_trades(
    cursor: Optional[str] = None,
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db)
):
    query = select(Trade).order_by(Trade.created_at.desc(), Trade.id.desc())

    if cursor:
        cursor_ts, cursor_id = decode_cursor(cursor)
        query = query.where(
            or_(
                Trade.created_at < cursor_ts,
                and_(Trade.created_at == cursor_ts, Trade.id < cursor_id)
            )
        )

    result = await db.execute(query.limit(limit + 1))
    trades = result.scalars().all()

    has_next = len(trades) > limit
    items = trades[:limit]

    return {
        "items": items,
        "next_cursor": encode_cursor(items[-1].created_at, items[-1].id) if has_next else None
    }
```

### Structured Exception Handler
```python
# Source: https://medium.com/@ixbahy/level-up-your-fastapi-exception-handling-done-right-5db862038c7a
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger()

class BaseAppException(Exception):
    def __init__(self, status_code: int, error_code: str, message: str, details: dict = None):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details or {}

async def app_exception_handler(request: Request, exc: BaseAppException):
    logger.error(
        "api_exception",
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
        method=request.method
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": exc.error_code,
                "message": exc.message,
                "details": exc.details
            }
        }
    )

app = FastAPI()
app.add_exception_handler(BaseAppException, app_exception_handler)
```

### Structured JSON Logging
```python
# Source: https://www.sheshbabu.com/posts/fastapi-structured-json-logging/
import structlog
from asgi_correlation_id import CorrelationIdMiddleware

# Configure structlog for JSON output
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,  # Merge context vars (correlation ID)
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(),
)

app.add_middleware(
    CorrelationIdMiddleware,
    header_name="X-Request-ID",
    generator=lambda: str(uuid.uuid4())
)

logger = structlog.get_logger()

@router.post("/trades")
async def create_trade(request: CreateTradeRequest):
    # Correlation ID automatically included
    logger.info("trade_create_start", symbol=request.symbol)
    # ... trade creation ...
    logger.info("trade_create_success", trade_id=123)

# Output:
# {"event": "trade_create_start", "symbol": "BTC/USD", "level": "info", "timestamp": "2026-02-04T15:30:00Z", "request_id": "abc123"}
```

### Database Indexes for Performance
```python
# Source: https://docs.sqlalchemy.org/en/20/core/constraints.html
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # Index on FK
    strategy_id = Column(Integer, ForeignKey("strategies.id"), index=True)
    symbol = Column(String(20), index=True)  # Frequently filtered
    created_at = Column(DateTime, server_default=func.now(), index=True)  # ORDER BY

    # Composite index for cursor pagination
    __table_args__ = (
        Index('ix_trades_cursor', 'created_at', 'id'),  # (timestamp, id) for efficient cursor queries
        Index('ix_trades_user_created', 'user_id', 'created_at'),  # User's recent trades
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sync SQLAlchemy with FastAPI | AsyncSession with asyncpg/aiosqlite | SQLAlchemy 2.0 (2023) | 3-5x throughput; non-blocking DB queries; required for high-concurrency autonomous trading |
| Offset pagination | Cursor pagination for real-time data | 2020s (API best practices evolution) | Eliminates phantom records in real-time feeds; O(1) vs O(n) performance |
| String-formatted logs | Structured JSON logs with correlation IDs | 2020s (observability tooling maturity) | Machine-parseable logs; distributed tracing; log aggregation (ELK/Datadog) integration |
| Fail-open rate limiting | Fail-closed with circuit breakers | Security hardening trend (2022+) | Prevents rate limit bypass during outages; aligns with zero-trust architecture |
| Generic exception handling | Exception hierarchies with RFC 9457 | RFC 9457 published July 2023 | Standardized error contracts; better client error handling; machine-readable error types |
| aiopg for PostgreSQL | asyncpg | aiopg maintenance mode (2021) | 5x faster; native asyncio; active development; binary protocol performance |

**Deprecated/outdated:**
- **aiopg**: Maintenance mode since 2021; use asyncpg instead (5x performance gain)
- **asyncio.to_thread for DB**: SQLAlchemy 2.0 native async makes this obsolete (was a workaround pre-2.0)
- **Offset pagination on trading endpoints**: Use cursor pagination (offset causes phantom records with real-time inserts)
- **Fail-open rate limiting**: Security vulnerability; modern systems fail-closed with circuit breakers
- **String concatenation for log formatting**: Use structured logging libraries (structlog/python-json-logger)

## Open Questions

Things that couldn't be fully resolved:

1. **SQLite async driver limitations for production**
   - What we know: aiosqlite uses thread pool (not true async I/O); sufficient for development; slower than asyncpg
   - What's unclear: At what concurrent request volume does aiosqlite become a bottleneck? Specific benchmarks for trading workload patterns?
   - Recommendation: Use SQLite + aiosqlite for development; PostgreSQL + asyncpg for production. Document migration path in deployment guide.

2. **Alembic migration support for AsyncEngine**
   - What we know: Alembic supports async engines as of 1.7.0 (2021); requires `async_engine` in env.py
   - What's unclear: Does existing Alembic setup in project need modification? Are current migrations compatible with async engine?
   - Recommendation: Test migrations with async engine in development. If issues, use `run_sync()` wrapper or keep migrations sync (migrations are infrequent, blocking is acceptable).

3. **Paper trading state snapshot frequency**
   - What we know: Immediate writes prevent data loss; periodic snapshots reduce write volume
   - What's unclear: Optimal snapshot interval for paper trading? Is every-trade write acceptable or should batch writes?
   - Recommendation: Start with immediate writes (simple, safe). If performance issue, add 5-minute periodic snapshots + shutdown handler. Paper trading is low-write-volume (<1000 trades/day expected).

4. **Circuit breaker thresholds for Redis rate limiter**
   - What we know: fail_max=5 failures opens circuit; timeout_duration=60s before retry
   - What's unclear: Optimal thresholds for Redis in crypto trading context? Too sensitive = false positives; too lenient = slow failure detection
   - Recommendation: Start with conservative defaults (5 failures, 60s timeout). Monitor circuit breaker state in production. Tune based on Redis failure patterns.

## Sources

### Primary (HIGH confidence)
- SQLAlchemy 2.0 Async Documentation - https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html (official docs, AsyncSession patterns)
- RFC 9457 Problem Details - https://datatracker.ietf.org/doc/rfc9457/ (official IETF standard for API error responses)
- pybreaker GitHub - https://github.com/danielfm/pybreaker (official circuit breaker library docs)
- asgi-correlation-id GitHub - https://github.com/snok/asgi-correlation-id (official middleware library)

### Secondary (MEDIUM confidence)
- [Building High-Performance Async APIs with FastAPI, SQLAlchemy 2.0, and Asyncpg](https://leapcell.io/blog/building-high-performance-async-apis-with-fastapi-sqlalchemy-2-0-and-asyncpg) - Performance benchmarks: 3-5x throughput async vs sync
- [Cursor pagination: how it works and its pros and cons](https://www.merge.dev/blog/cursor-pagination) - Cursor vs offset tradeoffs for real-time data
- [Structured JSON Logging using FastAPI](https://www.sheshbabu.com/posts/fastapi-structured-json-logging/) - Structlog integration with FastAPI middleware
- [Exception Handling Best Practices in Python: A FastAPI Perspective](https://medium.com/delivus/exception-handling-best-practices-in-python-a-fastapi-perspective-98ede2256870) - Exception hierarchy patterns
- [Rate Limiting with FastAPI: An In-Depth Guide](https://thedkpatel.medium.com/rate-limiting-with-fastapi-an-in-depth-guide-c4d64a776b83) - Fail-open vs fail-closed discussion
- [PostgreSQL Indexing with SQLAlchemy guide](https://www.opcito.com/blogs/a-guide-to-postgresql-indexing-with-sqlalchemy) - Index types and performance

### Tertiary (LOW confidence - marked for validation)
- Python Asyncio Database Drivers comparison - https://superfastpython.com/asyncio-database-drivers/ (aggregator site, not primary source)
- Various Medium articles on FastAPI patterns (useful examples but not authoritative)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official SQLAlchemy docs, established library versions, verified with official PyPI
- Architecture: HIGH - Patterns from official SQLAlchemy docs, RFC 9457, official library docs
- Pitfalls: MEDIUM-HIGH - Some from documentation, some from community experience (marked sources)

**Research date:** 2026-02-04
**Valid until:** ~60 days (2026-04-04) - Infrastructure patterns stable; library versions change slowly; async patterns unlikely to shift before SQLAlchemy 2.1 release
