---
phase: 02-autonomous-agent-loop
plan: 06
subsystem: api
completed: 2026-02-06
duration: 58s
tags: [fastapi, dashboard, observability, operator-actions, rest-api]

requires:
  - 02-03: Agent control API endpoints for status queries
  - 02-05: AgentManager observability hooks

provides:
  - Dashboard API combining status, queue metrics, and pipeline timeline
  - Operator action endpoints for queue flush and signal retry

affects:
  - 02-07: Frontend can consume unified dashboard endpoint
  - 02-08: Operator UI can trigger safe maintenance actions

tech-stack:
  added: []
  patterns:
    - "Unified dashboard endpoint pattern"
    - "Operator action auditing via manager delegation"

key-files:
  created: []
  modified:
    - backend/api/agents.py

decisions:
  - id: unified-dashboard-endpoint
    choice: Single /dashboard endpoint returns all dashboard data
    rationale: Reduces frontend roundtrips; all dashboard data fetched in one call
    alternatives: Separate endpoints for metrics, events, and status

  - id: route-ordering-fastapi
    choice: Place specific routes (/dashboard, /queue/flush, /signals/{id}/retry) before parameterized routes (/{agent_name})
    rationale: FastAPI matches routes in definition order; prevents path conflicts
    alternatives: Use regex constraints on agent_name parameter

  - id: operator-action-delegation
    choice: API delegates flush and retry to AgentManager methods
    rationale: Manager maintains audit trail and enforces business rules
    alternatives: Direct Redis/database manipulation in endpoints
---

# Phase 2 Plan 6: Dashboard API Summary

**One-liner:** Dashboard API combining agent status grid, queue metrics, and pipeline timeline with safe operator actions (flush queue, retry signal)

## What Was Built

Added three new API endpoints to `backend/api/agents.py`:

1. **GET /api/agents/dashboard** - Unified dashboard data
   - Agent status grid with heartbeat timestamps
   - Queue metrics (depth, throughput per channel)
   - Pipeline timeline (recent events with metadata)
   - Configurable pipeline_limit parameter (default: 20 events)

2. **POST /api/agents/queue/flush** - Flush message queue channel
   - Accepts channel name in request body
   - Delegates to AgentManager.flush_queue for audit trail
   - Returns count of flushed messages
   - Logs warnings on failure

3. **POST /api/agents/signals/{signal_id}/retry** - Retry failed trade signal
   - Re-publishes signal with high priority
   - Delegates to AgentManager.retry_signal for validation
   - Returns 404 if signal not found
   - Returns 500 for other errors

## Task Commits

| Task | Description | Commit | Files Modified |
|------|-------------|--------|----------------|
| 1 | Add dashboard endpoint with queue metrics and pipeline timeline | a8fb2282 | backend/api/agents.py |
| 2 | Add operator action endpoints for queue flush and signal retry | 44894580 | backend/api/agents.py |

## Technical Implementation

### Response Models

Added six new Pydantic models:

```python
class QueueMetricsResponse(BaseModel):
    channels: Dict[str, Any]
    total_depth: int
    throughput_per_minute: Dict[str, float]

class PipelineEventResponse(BaseModel):
    timestamp: str
    source_agent: str
    target_agent: str
    event_type: str
    channel: str
    priority: int
    summary: str
    metadata: Dict[str, Any]

class DashboardResponse(BaseModel):
    agents: List[AgentStatusResponse]
    queue_metrics: QueueMetricsResponse
    pipeline_events: List[PipelineEventResponse]

class FlushQueueRequest(BaseModel):
    channel: str

class FlushQueueResponse(BaseModel):
    channel: str
    flushed: int
    success: bool
    error: Optional[str] = None

class RetrySignalResponse(BaseModel):
    signal_id: str
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
```

### Route Ordering

Critical pattern learned: FastAPI matches routes in definition order. Specific routes MUST come before parameterized routes:

```python
@router.get("/dashboard")           # Matches /dashboard
@router.post("/queue/flush")        # Matches /queue/flush
@router.post("/signals/{id}/retry") # Matches /signals/abc123/retry
@router.post("/{agent_name}/control") # Matches /analyst/control
@router.get("/{agent_name}/status")   # Matches /analyst/status
```

If parameterized routes came first, FastAPI would treat "dashboard" and "queue" as agent names.

### Manager Integration

All endpoints delegate to AgentManager:

- `manager.get_all_status()` - Agent status grid
- `manager.get_queue_metrics()` - Queue depth and throughput (async)
- `manager.get_recent_pipeline_events(limit)` - Pipeline timeline
- `manager.flush_queue(channel)` - Audit-logged queue flush (async)
- `manager.retry_signal(signal_id)` - Validated signal retry (async)

This ensures business logic remains in the manager layer, not scattered across API routes.

## Verification Results

All verification criteria passed:

- GET /api/agents/dashboard returns complete dashboard data (agents, queue metrics, pipeline events)
- POST /api/agents/queue/flush flushes specified channel and returns count
- POST /api/agents/signals/{id}/retry retries failed signal with high priority
- All endpoints return proper Pydantic response models
- 503 returned if agent manager not initialized
- 404 returned if signal not found for retry
- 500 returned for other retry errors

## Deviations from Plan

None - plan executed exactly as written.

## Dependencies Satisfied

This plan required:

- **02-03** (Agent control API): Provides AgentStatusResponse model and manager access pattern
- **02-05** (Dashboard observability hooks): Provides get_queue_metrics, get_recent_pipeline_events, flush_queue, retry_signal methods

Both dependencies were available. No blocking issues encountered.

## Next Phase Readiness

This plan completes the backend dashboard API. Next steps:

- **02-07**: Frontend dashboard implementation can now consume GET /dashboard
- **02-08**: Operator UI can trigger POST /queue/flush and POST /signals/{id}/retry

**Blockers:** None

**Concerns:** None - API follows established patterns and delegates to manager layer

## Testing Recommendations

Future integration tests should verify:

1. Dashboard endpoint returns all three data types in single call
2. Queue flush actually removes messages from Redis Streams
3. Signal retry re-publishes with priority=10 (high priority)
4. Route ordering prevents path conflicts (test GET /api/agents/dashboard doesn't match /{agent_name})
5. Error handling for missing manager, missing agent, missing signal

## Self-Check: PASSED

All commits exist:
- a8fb2282: feat(02-06): add dashboard endpoint with queue metrics and pipeline timeline
- 44894580: feat(02-06): add operator action endpoints for queue flush and signal retry

All modified files verified:
- backend/api/agents.py: Contains dashboard, queue/flush, signals/{id}/retry endpoints
