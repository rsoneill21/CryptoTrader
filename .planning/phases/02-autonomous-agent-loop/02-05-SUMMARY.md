---
phase: 02
plan: 05
subsystem: agent-infrastructure
tags: [agents, monitoring, dashboard, operator-actions]

requires: [02-01, 02-02]
provides:
  - Queue metrics API for dashboard
  - Pipeline event timeline tracking
  - Operator actions for queue management

affects: [02-06, 02-07, 02-08]

tech-stack:
  added: []
  patterns: [event-sourcing, metrics-collection]

key-files:
  created: []
  modified:
    - backend/agents/manager.py

decisions:
  - Pipeline events capped at 100 (deque maxlen)
  - Throughput calculated as messages per minute
  - flush_queue() clears all priority levels
  - retry_signal() re-queues with priority 0

metrics:
  duration: "3 minutes 34 seconds"
  completed: 2026-02-06
---

# Phase 02 Plan 05: Dashboard Observability Hooks Summary

**One-liner:** AgentManager exposes queue metrics, pipeline timeline, and operator actions for dashboard monitoring and control

## What Was Built

Added observability and control capabilities to AgentManager for dashboard integration:

**Queue Metrics:**
- `get_queue_metrics()` - Returns depth (p0/p1/p2/total) for stream channels
- Throughput calculation (messages per minute)
- Per-channel metrics for STREAM_TRADE_SIGNALS and STREAM_RISK_ALERTS

**Pipeline Event Tracking:**
- `PipelineEvent` dataclass for capturing message flow
- `record_pipeline_event()` - Records agent-to-agent communication
- `get_recent_pipeline_events()` - Returns last N events (most recent first)
- Event deque capped at 100 entries
- `reset_throughput_counters()` - Periodic metric reset

**Operator Actions:**
- `flush_queue()` - Clears all messages from a channel (all priority levels)
- `retry_signal()` - Re-publishes failed signals with priority 0

## Task Commits

| Task | Description | Commit | Files Modified |
|------|-------------|--------|----------------|
| 1 | Add queue metrics and pipeline event tracking | 4968dcd1 | backend/agents/manager.py |
| 2 | Add operator action methods | 516665ae | backend/agents/manager.py |

## Decisions Made

**Pipeline Event Storage:**
- Used `collections.deque` with maxlen=100 to automatically cap event history
- Prevents unbounded memory growth while keeping recent timeline

**Throughput Tracking:**
- Track message counts per channel in `_message_counts` dict
- Calculate throughput as `(count * 60 / elapsed_seconds)` for messages/minute
- Requires periodic `reset_throughput_counters()` calls for accurate windowing

**Queue Flush Behavior:**
- Iterates all priority levels (p0, p1, p2) for complete channel flush
- Returns count of messages flushed for audit
- Logs each priority level flush separately

**Signal Retry Priority:**
- Failed signals re-queued with priority 0 (critical)
- Ensures retries process before routine signals
- Accesses trade executor's `_pending_orders` via getattr for loose coupling

## Deviations from Plan

None - plan executed exactly as written.

## Testing Notes

**Manual verification:**
- Methods exist and are callable on AgentManager instance
- Import dependencies (PipelineEvent, Channels, message_queue) resolve correctly
- Type annotations match plan specifications

**Future integration testing needed:**
- Dashboard endpoints calling these methods
- Pipeline event recording during actual agent message flow
- Queue flush + retry signal with live Redis Streams

## Next Phase Readiness

**Unblocks:**
- 02-06: Agent decision loop (can record pipeline events during execution)
- 02-07: Operator dashboard API (endpoints can call these methods)
- 02-08: Real-time monitoring (WebSocket can stream pipeline events)

**Dependencies satisfied:**
- Queue depth metrics available from MessageQueue (02-02)
- AgentManager lifecycle running (02-01)

**Blockers/Concerns:**
None. Dashboard integration can proceed.

## Performance Impact

**Memory:**
- Pipeline events: ~100 events × ~200 bytes = ~20KB max (negligible)
- Message count dict: ~2-10 channels × 4 bytes int = <100 bytes

**CPU:**
- `get_queue_metrics()`: O(N) Redis XLEN calls where N=channels×priorities (~6 calls)
- `get_recent_pipeline_events()`: O(1) deque slice + list comprehension
- `flush_queue()`: O(N) Redis DELETE calls where N=priorities (3 calls)

All operations are lightweight and suitable for dashboard polling.

## Self-Check: PASSED

**Created files:**
None (modifications only)

**Modified files:**
- backend/agents/manager.py ✓

**Commits:**
- 4968dcd1 ✓
- 516665ae ✓

All claimed work verified in git history.
