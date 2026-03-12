# Phase 2: Autonomous Agent Loop - Research

**Researched:** 2026-02-05
**Domain:** AsyncIO agent orchestration with FastAPI lifespan and Redis messaging
**Confidence:** HIGH

## Summary

This phase implements autonomous agent execution where Market Analyst, Orchestrator, and Trade Executor agents run continuously, coordinate via message queues, and recover from failures without manual intervention. The existing codebase already contains complete agent implementations (BaseAgent framework, three concrete agents) and a Redis pub/sub message queue infrastructure. The research focused on production patterns for agent lifecycle management, staggered startup sequencing, failure recovery, priority messaging, and real-time observability.

Key findings:
- FastAPI's lifespan context manager is the standard approach for managing long-running asyncio tasks alongside the web server
- Redis Streams provides better reliability than pub/sub for critical agent coordination (at-least-once delivery, consumer groups, persistence)
- Agent supervision patterns with immediate restart after failure are well-established in asyncio applications
- Heartbeat monitoring via periodic timestamps enables detection of hung agents without external dependencies

**Primary recommendation:** Use FastAPI lifespan to launch an AgentManager that starts agents with health-check delays, supervises failures with immediate restart, and exposes status via existing system APIs. Upgrade message_queue.py to use Redis Streams for trade signals while keeping pub/sub for market insights.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Agent Scheduling & Start/Stop
- Agents should start in a staggered sequence after backend startup health checks (backend → Market Analyst → Orchestrator → Trade Executor).
- Market Analyst runs an always-on loop, while Orchestrator and Trade Executor wake up based on incoming events.
- Operators need admin UI toggles to pause/resume each agent; changing a toggle gracefully stops the agent after it finishes its current work and restarts when toggled back on.
- Deploy one instance of Orchestrator and one Trade Executor; allow multiple Market Analyst instances (configurable) when more data streams are needed.

#### Message Flow & Coordination
- Analyst → Orchestrator → Executor messages should contain the full analysis bundle (raw indicators, sentiment, references) so downstream steps can audit without extra DB lookups.
- Use priority queues so critical/urgent signals bypass routine chatter; priorities should reflect urgency (e.g., halt signals > rebalance > research ideas).

#### Failure Handling & Recovery
- If an agent crashes, restart it immediately; no manual confirmation needed.
- Surface failure/restart state on the dashboard rather than pushing Slack/email alerts.
- When the queue backs up, drop the oldest signals so fresh data continues to flow; log what was discarded for audit.
- When the Trade Executor cannot place an order, apply a fallback strategy automatically (e.g., reduced position size or alternate venue) before marking the signal failed.

#### Observability & Operator Controls
- Operator dashboard must show: (1) agent status grid with heartbeat timestamps, (2) pipeline timeline illustrating recent messages flowing through the loop, and (3) queue metrics (depth, throughput, latency).
- Log agent telemetry through the existing system log API endpoints so the current monitoring tooling can consume it.
- Provide limited safe actions in the dashboard (e.g., flush queue, retry a failed signal) in addition to the pause/resume toggles.

### Claude's Discretion
- Choose the exact messaging backbone/transport implementation that best fits these behaviors.
- Set the message delivery guarantee (e.g., at-least-once vs exactly-once) consistent with the chosen transport.
- Define the heartbeat freshness threshold (user is fine with Claude picking the window).
- Include any additional dashboard insights beyond the three mandated widgets.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.

</user_constraints>

---

## Standard Stack

The established libraries/tools for asyncio agent orchestration with FastAPI:

### Core (Already Installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.109.0 | Web framework with lifespan support | Industry standard for async Python APIs; lifespan context manager is the canonical pattern for managing background tasks |
| asyncio | stdlib | Concurrency runtime | Python's built-in async framework; all agents inherit from BaseAgent and use async/await |
| redis | >=5.0.1 | Message queue transport | Already integrated; supports both pub/sub and Streams |

### Supporting (Need to Add)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| redis.asyncio | Built into redis>=5.0 | Async Redis client | Required for Redis Streams consumer groups |
| aiomonitor | >=0.7.0 (optional) | AsyncIO task monitor | Debugging stuck agents during development |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Redis Streams | Keep pub/sub only | Streams provides persistence + consumer groups but adds 1-2ms latency |
| FastAPI lifespan | Celery Beat scheduler | Celery already installed but adds complexity; lifespan is simpler for in-process agents |
| Custom supervisor | APScheduler | APScheduler better for cron-style jobs; custom supervisor better for continuous agents |

**Installation:**
```bash
# Already installed: fastapi, redis, asyncio (stdlib)
# Optional for debugging:
pip install aiomonitor>=0.7.0
```

---

## Architecture Patterns

### Recommended Project Structure
```
backend/
├── agents/
│   ├── base.py              # BaseAgent, AgentRegistry (exists)
│   ├── market_analyst.py    # MarketAnalystAgent (exists)
│   ├── orchestrator.py      # OrchestratorAgent (exists)
│   ├── trade_executor.py    # TradeExecutorAgent (exists)
│   └── manager.py           # NEW: AgentManager for lifecycle + supervision
├── core/
│   ├── message_queue.py     # MODIFY: Add Redis Streams support
│   └── ...
├── api/
│   └── agents.py            # NEW: Agent control endpoints (pause/resume/status)
└── main.py                  # MODIFY: Wire AgentManager into lifespan
```

### Pattern 1: FastAPI Lifespan for Agent Lifecycle
**What:** Use asynccontextmanager to start/stop agents alongside FastAPI application lifecycle.

**When to use:** Managing long-running asyncio tasks that must exist for the entire application lifetime.

**Example:**
```python
# Source: https://fastapi.tiangolo.com/advanced/events/
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: before yield
    agent_manager = AgentManager()
    await agent_manager.start_all()
    yield
    # Shutdown: after yield
    await agent_manager.stop_all()

app = FastAPI(lifespan=lifespan)
```

**Why this pattern:**
- Replaces deprecated @app.on_event decorators (removed in FastAPI 0.95+)
- Guarantees cleanup runs even if startup fails
- Shares lifespan context across application (store manager in app.state)

### Pattern 2: Staggered Startup with Health Checks
**What:** Start agents sequentially with delays, verifying each is healthy before launching the next.

**When to use:** When agents have dependencies (e.g., Orchestrator needs Market Analyst to be receiving data).

**Example:**
```python
# Pattern derived from user requirements + FastAPI best practices
async def start_with_health_checks(self):
    # 1. Wait for backend health
    await self._wait_for_backend_health()

    # 2. Start Market Analyst
    await self.market_analyst.start()
    await self._wait_for_agent_health(self.market_analyst, timeout=5.0)

    # 3. Start Orchestrator
    await self.orchestrator.start()
    await self._wait_for_agent_health(self.orchestrator, timeout=3.0)

    # 4. Start Trade Executor
    await self.trade_executor.start()
    await self._wait_for_agent_health(self.trade_executor, timeout=3.0)

async def _wait_for_agent_health(self, agent, timeout):
    start = asyncio.get_running_loop().time()
    while True:
        if agent.is_running and agent.get_status()["queue_size"] >= 0:
            return
        if asyncio.get_running_loop().time() - start > timeout:
            raise RuntimeError(f"Agent {agent.name} failed health check")
        await asyncio.sleep(0.1)
```

**Why this pattern:**
- User requirement: "start in a staggered sequence after backend startup health checks"
- Prevents cascading failures from agents starting before dependencies are ready
- Health check validates agent is actually processing, not just started

### Pattern 3: Supervisor with Immediate Restart
**What:** Wrap agent tasks in a supervisor that catches exceptions and immediately restarts the agent.

**When to use:** When agents must stay running despite transient failures (network issues, API errors).

**Example:**
```python
# Source: https://discuss.python.org/t/asyncio-tasks-and-exception-handling-recommended-idioms/23806
async def supervise_agent(self, agent: BaseAgent):
    """Supervisor loop that restarts agent on failure."""
    restart_count = 0
    last_restart = 0.0

    while self._running:
        try:
            await agent.start()
            # Agent stopped gracefully (via agent.stop())
            break
        except asyncio.CancelledError:
            # Supervisor cancelled - clean shutdown
            break
        except Exception as exc:
            restart_count += 1
            now = asyncio.get_running_loop().time()

            # Backoff if restarting too frequently
            if now - last_restart < 5.0 and restart_count > 3:
                logger.error(f"Agent {agent.name} crash-looping, backing off")
                await asyncio.sleep(10.0)

            last_restart = now
            logger.exception(f"Agent {agent.name} crashed, restarting (#{restart_count})")

            # Log to system events for dashboard visibility
            log_system_event.delay(
                "error",
                "agent_manager",
                f"Agent {agent.name} crashed and restarted",
                {"agent": agent.name, "restart_count": restart_count, "error": str(exc)}
            )

            await asyncio.sleep(1.0)  # Brief delay before restart
```

**Why this pattern:**
- User requirement: "If an agent crashes, restart it immediately; no manual confirmation needed"
- Detects crash-loops (rapid repeated failures) and backs off
- Logs all restarts for observability

### Pattern 4: Redis Streams for Reliable Message Delivery
**What:** Use Redis Streams instead of pub/sub for critical agent coordination requiring delivery guarantees.

**When to use:** When messages must not be lost (trade signals, risk alerts) and consumers need to coordinate.

**Example:**
```python
# Source: https://redis.io/docs/latest/develop/data-types/streams/
import redis.asyncio as redis

class MessageQueue:
    async def publish_reliable(self, channel: str, message: dict, priority: int = 0):
        """Publish to Redis Stream with priority."""
        # Streams don't have native priority, use separate streams per priority
        stream_key = f"stream:{channel}:priority{priority}"

        message["_timestamp"] = datetime.utcnow().isoformat()
        message["_priority"] = priority

        await self._redis.xadd(stream_key, message)

    async def consume_reliable(self, channel: str, group: str, consumer: str, callback):
        """Consume from Redis Stream with consumer group."""
        stream_key = f"stream:{channel}:priority*"

        # Create consumer group if not exists
        try:
            await self._redis.xgroup_create(stream_key, group, id="0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        # Read messages
        while self._running:
            messages = await self._redis.xreadgroup(
                group, consumer, {stream_key: ">"}, count=10, block=1000
            )

            for stream, msg_list in messages:
                for msg_id, msg_data in msg_list:
                    try:
                        await callback(msg_data)
                        await self._redis.xack(stream, group, msg_id)
                    except Exception as exc:
                        logger.error(f"Message processing failed: {exc}")
                        # Message stays unacked, will be redelivered
```

**Why this pattern:**
- User requirement: "Use priority queues so critical/urgent signals bypass routine chatter"
- Redis Streams provides at-least-once delivery (messages persist until acked)
- Consumer groups enable multiple Trade Executor instances without duplication
- Priority implemented via separate streams (priority0, priority1, priority2)

### Pattern 5: Heartbeat Monitoring
**What:** Each agent periodically updates a timestamp; monitor detects stale timestamps as hung agents.

**When to use:** When agent supervision needs to detect hung agents (infinite loop, deadlock) vs crashed agents.

**Example:**
```python
# Pattern derived from user requirements + https://cronitor.io/guides/heartbeat-monitoring
class BaseAgent(ABC):
    def __init__(self, name: str, description: str = ""):
        # ... existing init ...
        self._last_heartbeat: float = 0.0
        self._heartbeat_interval = 5.0  # Claude's discretion: 5 seconds

    async def _run_loop(self):
        while self._running:
            # Update heartbeat timestamp
            self._last_heartbeat = asyncio.get_running_loop().time()

            # ... existing run loop logic ...

    def get_status(self) -> Dict[str, Any]:
        return {
            # ... existing status fields ...
            "last_heartbeat": self._last_heartbeat,
            "heartbeat_age_seconds": asyncio.get_running_loop().time() - self._last_heartbeat,
        }

# In AgentManager:
async def check_heartbeats(self):
    """Monitor loop that checks agent heartbeats."""
    STALE_THRESHOLD = 30.0  # Claude's discretion: 30 seconds

    while self._running:
        for agent in self._agents:
            age = asyncio.get_running_loop().time() - agent._last_heartbeat
            if age > STALE_THRESHOLD:
                logger.error(f"Agent {agent.name} heartbeat stale ({age:.1f}s)")
                # Force restart via supervisor
                agent._task.cancel()

        await asyncio.sleep(10.0)  # Check every 10 seconds
```

**Why this pattern:**
- User requirement: "agent status grid with heartbeat timestamps"
- Detects hung agents (infinite loop, blocking call) that don't crash
- Claude's discretion: 5s heartbeat interval, 30s stale threshold (allows 6 missed beats)

### Pattern 6: Queue Backlog Management
**What:** Monitor queue depth; drop oldest messages when backlog exceeds threshold.

**When to use:** When queue throughput can't keep up with production rate and stale data is worse than no data.

**Example:**
```python
# Pattern derived from user requirements
async def monitor_queue_backlog(self):
    """Monitor loop that trims queues when they exceed depth limit."""
    MAX_DEPTH = 100  # Claude's discretion: 100 messages per priority level

    while self._running:
        for channel in ["stream:trade_signals:priority0", "stream:trade_signals:priority1"]:
            length = await self._redis.xlen(channel)

            if length > MAX_DEPTH:
                # Trim oldest messages
                dropped = length - MAX_DEPTH
                await self._redis.xtrim(channel, maxlen=MAX_DEPTH, approximate=False)

                logger.warning(f"Queue {channel} backlog trimmed: dropped {dropped} messages")
                log_system_event.delay(
                    "warning",
                    "message_queue",
                    f"Queue backlog trimmed",
                    {"channel": channel, "dropped": dropped}
                )

        await asyncio.sleep(5.0)  # Check every 5 seconds
```

**Why this pattern:**
- User requirement: "When the queue backs up, drop the oldest signals so fresh data continues to flow"
- Redis Streams XTRIM efficiently removes old messages
- Logs dropped message count for audit trail

### Anti-Patterns to Avoid

**❌ Using @app.on_event("startup") / @app.on_event("shutdown")**
- Deprecated since FastAPI 0.95.0
- No guarantee of cleanup if startup fails
- Use `@asynccontextmanager` with lifespan parameter instead

**❌ Starting agents directly in main.py without supervision**
- Agent crashes silently stop the pipeline
- No visibility into restart events
- Use AgentManager with supervisor pattern

**❌ Using Redis pub/sub for trade signals**
- Messages lost if subscriber offline or processing slow
- No consumer group coordination (multiple executors process same signal)
- Use Redis Streams for reliable delivery

**❌ Storing agent state in FastAPI app.state without thread safety**
- app.state is mutable; concurrent access causes race conditions
- Use asyncio.Lock or immutable references

**❌ Polling agent status synchronously from API endpoints**
- Blocks event loop on slow agents
- Use cached status updated by agents themselves in _run_loop

---

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Agent task exception handling | Custom try/except with restart logic | Supervisor pattern with asyncio.Task.add_done_callback | Edge cases: CancelledError vs Exception, crash loop detection, backoff strategies |
| Message priority queues | Custom sorted list + asyncio.Queue | Redis Streams with separate streams per priority | Edge cases: concurrent producers, consumer group coordination, persistence |
| Heartbeat freshness checks | Manual timestamp comparison | Time-series monitoring pattern with stale detection | Edge cases: clock skew, missed beats during high load, false positives |
| Graceful agent shutdown | agent.stop() with manual cleanup | asyncio.CancelledError propagation + try/finally | Edge cases: in-flight messages, database transactions, Kraken API calls |
| Queue metrics (depth, throughput) | Manual counters | Redis XLEN + XINFO STREAM | Edge cases: memory overhead, distributed counters, sampling strategies |

**Key insight:** AsyncIO agent orchestration has subtle failure modes (crash loops, stuck tasks, missed cancellations). Use proven patterns from Redis, FastAPI, and asyncio documentation rather than custom logic.

---

## Common Pitfalls

### Pitfall 1: Agent Tasks Not Cleaned Up on Shutdown
**What goes wrong:** Agents keep running after FastAPI shutdown, leaving zombie processes or unclosed connections.

**Why it happens:** FastAPI lifespan's after-yield section doesn't automatically cancel asyncio tasks created during startup.

**How to avoid:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = AgentManager()
    await manager.start_all()

    # Store manager in app.state so it can be accessed during runtime
    app.state.agent_manager = manager

    try:
        yield
    finally:
        # Explicit cleanup guarantees agents stop even if yield raises
        await manager.stop_all()
```

**Warning signs:**
- `RuntimeWarning: coroutine was never awaited` after shutdown
- Redis connections in `CLOSE_WAIT` state
- Kraken WebSocket still receiving data after backend stops

### Pitfall 2: Agents Start Before Dependencies Are Ready
**What goes wrong:** Orchestrator subscribes to AI_DECISIONS channel before Market Analyst publishes insights, causing race conditions.

**Why it happens:** asyncio.create_task launches agents concurrently without sequencing.

**How to avoid:** Use staggered startup with health checks (Pattern 2).

**Warning signs:**
- Orchestrator logs "no insights available" immediately after startup
- Trade Executor processes empty trade_signals queue
- Agent status shows `running=True` but `queue_size=0` for extended period

### Pitfall 3: Priority Queues Don't Actually Prioritize
**What goes wrong:** High-priority messages (halt signals) get stuck behind low-priority messages (research ideas).

**Why it happens:** Redis pub/sub and single-stream Streams don't support message priority natively.

**How to avoid:** Use separate Redis Streams per priority level + read from priority0 first, priority1 second, etc.

**Warning signs:**
- Critical risk alerts delayed by seconds/minutes
- Trade signals processed out of urgency order
- Queue backlog clears slowly despite many consumers

### Pitfall 4: Agent Supervisor Doesn't Detect Stuck Agents
**What goes wrong:** Agent enters infinite loop (e.g., waiting for network response) but supervisor thinks it's healthy because exception wasn't raised.

**Why it happens:** Supervisor only catches Exception, doesn't detect hung tasks.

**How to avoid:** Implement heartbeat monitoring (Pattern 5) alongside supervisor pattern.

**Warning signs:**
- Agent status shows `running=True` but no log output for minutes
- Heartbeat timestamp stops updating
- Queue messages pile up unprocessed

### Pitfall 5: Queue Backlog Fills Memory Until Redis OOM
**What goes wrong:** Market Analyst produces insights faster than Orchestrator consumes; Redis memory usage grows until eviction/crash.

**Why it happens:** No backpressure or max-length enforcement on streams.

**How to avoid:** Implement queue backlog monitoring (Pattern 6) with XTRIM to cap stream length.

**Warning signs:**
- Redis memory usage grows continuously
- `OOM command not allowed` errors in Redis logs
- Queue depth metrics show unbounded growth

### Pitfall 6: Paused Agents Don't Finish Current Work
**What goes wrong:** Operator pauses Trade Executor mid-order-placement; order state left inconsistent.

**Why it happens:** Pause implementation sets flag immediately without checking in-flight work.

**How to avoid:**
```python
async def pause(self):
    """Pause agent after finishing current message."""
    if self._running and not self._paused:
        logger.info(f"Pausing agent {self.name} after current work completes")
        self._paused = True
        # Agent run loop will check _paused before processing next message
        # Current message finishes naturally
```

**Warning signs:**
- Partial orders visible in Kraken UI but not in local database
- Agent status shows `paused=True` but logs indicate unfinished work
- Resume operation fails because state is inconsistent

---

## Code Examples

Verified patterns from official sources and project structure:

### Agent Manager Startup Sequence
```python
# Source: User requirements + FastAPI lifespan pattern
from contextlib import asynccontextmanager
from fastapi import FastAPI
from agents.manager import AgentManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: manage agents alongside FastAPI."""
    logger.info("Starting agent manager")

    # Create and start agent manager
    manager = AgentManager()
    await manager.start_all()  # Staggered with health checks

    # Store in app.state for API endpoint access
    app.state.agent_manager = manager

    try:
        yield  # Application runs
    finally:
        # Graceful shutdown
        logger.info("Stopping agent manager")
        await manager.stop_all()

app = FastAPI(lifespan=lifespan)
```

### Agent Control API Endpoints
```python
# Source: User requirements for "admin UI toggles to pause/resume each agent"
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()

class AgentControlRequest(BaseModel):
    action: str  # "pause" | "resume"

@router.post("/agents/{agent_name}/control")
async def control_agent(agent_name: str, request: Request, body: AgentControlRequest):
    """Pause or resume a specific agent."""
    manager = request.app.state.agent_manager
    agent = manager.get_agent(agent_name)

    if not agent:
        raise HTTPException(404, detail=f"Agent {agent_name} not found")

    if body.action == "pause":
        agent.pause()  # Sets flag; agent finishes current work
        return {"status": "paused", "agent": agent_name}
    elif body.action == "resume":
        agent.resume()
        return {"status": "resumed", "agent": agent_name}
    else:
        raise HTTPException(400, detail="Action must be 'pause' or 'resume'")

@router.get("/agents/status")
async def get_agent_status(request: Request):
    """Get status of all agents for dashboard."""
    manager = request.app.state.agent_manager
    return {
        "agents": manager.get_all_status(),
        "queue_metrics": await manager.get_queue_metrics(),
        "pipeline_events": manager.get_recent_pipeline_events(limit=20)
    }
```

### Redis Streams Priority Message Publishing
```python
# Source: https://redis.io/docs/latest/develop/data-types/streams/ + user requirements
async def publish(self, channel: str, message: dict, priority: int = 0) -> bool:
    """
    Publish message with priority support.

    Priority levels:
    - 0: Critical (halt signals, emergency stops)
    - 1: High (rebalance recommendations, risk alerts)
    - 2: Normal (routine insights, research ideas)
    """
    if not self._redis:
        logger.warning("Not connected to Redis")
        return await self._local_publish(channel, message)

    try:
        # Add metadata
        message["_timestamp"] = datetime.utcnow().isoformat()
        message["_channel"] = channel
        message["_priority"] = priority

        # Use separate stream per priority for ordering
        stream_key = f"stream:{channel}:p{priority}"

        # Publish to Redis Stream
        msg_id = await self._redis.xadd(stream_key, message)

        # Check backlog and trim if needed
        length = await self._redis.xlen(stream_key)
        if length > self.MAX_QUEUE_DEPTH:
            dropped = length - self.MAX_QUEUE_DEPTH
            await self._redis.xtrim(stream_key, maxlen=self.MAX_QUEUE_DEPTH)
            logger.warning(f"Trimmed {stream_key}: dropped {dropped} old messages")

        return True
    except Exception as e:
        logger.error(f"Error publishing to {channel}: {e}")
        return False
```

### Agent Supervisor with Restart
```python
# Source: https://discuss.python.org/t/asyncio-tasks-and-exception-handling-recommended-idioms/23806
async def _supervise_agent(self, agent: BaseAgent):
    """Supervisor that restarts agent on failure."""
    restart_count = 0
    last_restart_time = 0.0

    while self._running:
        try:
            # Start agent (blocks until agent stops)
            await agent.start()

            # Agent stopped gracefully - break supervisor loop
            logger.info(f"Agent {agent.name} stopped gracefully")
            break

        except asyncio.CancelledError:
            # Supervisor cancelled - propagate for clean shutdown
            logger.info(f"Agent {agent.name} supervisor cancelled")
            await agent.stop()
            break

        except Exception as exc:
            # Agent crashed - restart immediately
            restart_count += 1
            now = asyncio.get_running_loop().time()

            # Detect crash loops (3+ crashes in 5 seconds)
            if now - last_restart_time < 5.0 and restart_count > 3:
                logger.error(f"Agent {agent.name} crash-looping, backing off")
                await asyncio.sleep(10.0)

            last_restart_time = now

            # Log crash with full traceback
            logger.exception(f"Agent {agent.name} crashed (restart #{restart_count})")

            # Surface to dashboard via system events
            log_system_event.delay(
                "error",
                "agent_manager",
                f"Agent crashed and restarted",
                {
                    "agent": agent.name,
                    "restart_count": restart_count,
                    "error": str(exc),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

            # Brief delay before restart
            await asyncio.sleep(1.0)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| @app.on_event("startup") | @asynccontextmanager with lifespan= | FastAPI 0.95.0 (2023) | Lifespan guarantees cleanup on startup failure; on_event doesn't |
| Redis pub/sub for everything | Redis Streams for critical messages | Redis 5.0+ (2018, mature in 2024+) | Streams add persistence, consumer groups, at-least-once delivery |
| Manual agent restarts | Supervisor pattern with immediate restart | Python asyncio best practices | Agents recover from transient failures without human intervention |
| Celery Beat for scheduling | FastAPI lifespan for in-process tasks | FastAPI 0.109+ with lifespan | Simpler for agents that run continuously; Celery better for cron jobs |
| Polling for agent status | Push-based heartbeats | Microservices observability patterns (2020+) | Lower latency detection of stuck agents; less load on monitoring |

**Deprecated/outdated:**
- **@app.on_event decorators**: Removed in FastAPI 0.95+. Use lifespan context manager.
- **redis-py synchronous client**: Use redis.asyncio for async FastAPI applications.
- **Separate agent startup scripts**: Agents should start with FastAPI, not as separate processes.

---

## Open Questions

Things that couldn't be fully resolved:

1. **Multi-instance deployment strategy**
   - What we know: User wants "multiple Market Analyst instances (configurable) when more data streams are needed"
   - What's unclear: How to coordinate multiple instances (shared Redis consumer group? Separate symbols per instance? Load balancer?)
   - Recommendation: Start with single instance; implement consumer group pattern when scaling needed (Phase 2 follow-up)

2. **Order execution fallback strategy specifics**
   - What we know: User wants "fallback strategy automatically (e.g., reduced position size or alternate venue)"
   - What's unclear: Exact fallback rules (reduce by 50%? 10%? Try market order if limit fails?)
   - Recommendation: Implement simple retry-with-delay first; rich fallback strategies in Phase 4 (Position Management)

3. **Dashboard real-time update mechanism**
   - What we know: Dashboard must show agent status, queue metrics, pipeline timeline
   - What's unclear: Push (WebSocket) vs pull (polling) for dashboard updates?
   - Recommendation: Start with HTTP polling (1 second interval); WebSocket if performance insufficient

---

## Sources

### Primary (HIGH confidence)
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/) - Official FastAPI documentation on lifespan context managers
- [Redis Streams Documentation](https://redis.io/docs/latest/develop/data-types/streams/) - Official Redis docs on Streams, consumer groups, XADD/XREAD
- [Python asyncio Development Guide](https://docs.python.org/3/library/asyncio-dev.html) - Official Python docs on asyncio task exception handling
- Project codebase: `/home/packnation82/projects/CryptoTrader/backend/agents/` - Existing BaseAgent, MarketAnalystAgent, OrchestratorAgent, TradeExecutorAgent implementations
- Project codebase: `/home/packnation82/projects/CryptoTrader/backend/core/message_queue.py` - Existing Redis pub/sub MessageQueue implementation

### Secondary (MEDIUM confidence)
- [Redis Streams vs Pub/Sub Comparison (DEV Community)](https://dev.to/lovestaco/redis-pubsub-vs-redis-streams-a-dev-friendly-comparison-39hm) - Delivery guarantees, reliability tradeoffs
- [FastAPI Lifespan Explained (Medium, Jan 2026)](https://medium.com/algomart/fastapi-lifespan-explained-the-right-way-to-handle-startup-and-shutdown-logic-f825f38dd304) - Recent best practices for lifespan usage
- [AsyncIO Task Exception Handling Discussion (Python.org)](https://discuss.python.org/t/asyncio-tasks-and-exception-handling-recommended-idioms/23806) - Community consensus on supervisor patterns
- [Redis Priority Queues with Sorted Sets (OneUpTime, Jan 2026)](https://oneuptime.com/blog/post/2026-01-21-redis-priority-queues-sorted-sets/view) - Priority queue implementation patterns
- [Agent Retry Strategies (PraisonAI)](https://docs.praison.ai/docs/best-practices/agent-retry-strategies) - Exponential backoff, circuit breaker patterns for AI agents

### Tertiary (LOW confidence)
- [aiomonitor GitHub](https://github.com/aio-libs/aiomonitor) - AsyncIO debugging tool; not used yet but may be helpful
- [AI Agent Monitoring in 2026 (AimMultiple)](https://research.aimultiple.com/agentic-monitoring/) - General observability trends; not specific to implementation

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already installed or standard Python; verified in requirements.txt and project codebase
- Architecture: HIGH - Patterns sourced from official FastAPI, Redis, and Python docs; aligned with existing BaseAgent framework
- Pitfalls: HIGH - Derived from user requirements and known asyncio failure modes (cancellation, stuck tasks, crash loops)

**Research date:** 2026-02-05
**Valid until:** 2026-03-05 (30 days - stable domain, no fast-moving dependencies)
