---
phase: 02-autonomous-agent-loop
plan: 02
subsystem: messaging
tags: [redis, streams, reliability, priority-queues]
requires:
  - "Redis server with Streams support"
  - "Existing MessageQueue pub/sub infrastructure"
provides:
  - "At-least-once delivery for trade signals via Redis Streams"
  - "Priority queue support (0=critical, 1=high, 2=normal)"
  - "Consumer groups for reliable message acknowledgment"
  - "Queue backlog management with MAX_QUEUE_DEPTH trimming"
affects:
  - "02-03: Signal distribution endpoint can use publish_reliable()"
  - "02-04: Agent decision loop can consume_reliable() with ack"
  - "Future monitoring: get_queue_depth() enables queue metrics"
tech-stack:
  added:
    - "Redis Streams (xadd, xreadgroup, xack, xtrim)"
  patterns:
    - "Consumer groups for at-least-once delivery"
    - "Priority-based stream separation"
    - "Backlog trimming with audit logging"
key-files:
  created: []
  modified:
    - backend/core/message_queue.py
decisions:
  - id: "redis-streams-priority-separation"
    decision: "Use separate streams per priority level (stream:{channel}:p{N})"
    rationale: "Enables priority-based consumption without complex ordering logic"
    alternatives: "Single stream with priority field (requires sorting on read)"
  - id: "max-queue-depth-100"
    decision: "Trim queues at MAX_QUEUE_DEPTH=100 with oldest-first eviction"
    rationale: "User decision: prevent unbounded memory growth, drop old signals if backed up"
    alternatives: "Block publishers or use Redis maxmemory policy"
  - id: "fallback-to-local"
    decision: "publish_reliable() falls back to _local_publish() when Redis unavailable"
    rationale: "Maintains agent communication during Redis outages (best-effort)"
    alternatives: "Fail hard and require Redis availability"
metrics:
  duration: "~2 minutes"
  completed: "2026-02-06"
---

# Phase 2 Plan 02: Redis Streams for Reliable Messaging Summary

**One-liner:** Redis Streams with consumer groups provide at-least-once trade signal delivery using priority queues (0=critical, 1=high, 2=normal)

## What Was Built

Upgraded MessageQueue class from pure pub/sub to hybrid architecture:
- Pub/sub for fire-and-forget market insights (existing)
- Redis Streams for reliable trade signal delivery (new)

New capabilities:
1. **publish_reliable()**: Publishes to Redis Streams with xadd, priority support, and backlog management
2. **consume_reliable()**: Consumes with consumer groups using xreadgroup, automatic redelivery on failure
3. **get_queue_depth()**: Returns queue depths per priority (p0/p1/p2/total) for monitoring
4. **stop_consumers()**: Graceful shutdown by setting _running=False

Key design decisions:
- Priority levels: 0=critical (halt signals), 1=high (rebalance), 2=normal (insights)
- Separate streams per priority: `stream:trade_signals:p0`, `stream:trade_signals:p1`, `stream:trade_signals:p2`
- MAX_QUEUE_DEPTH=100: trims oldest messages when exceeded, logs dropped count for audit
- Consumer groups ensure at-least-once delivery: messages stay unacked until callback succeeds
- Fallback to local publish when Redis unavailable (maintains agent communication)

## Task Commits

| Task | Description | Commit | Files Modified |
|------|-------------|--------|----------------|
| 1 | Add Redis Streams methods to MessageQueue | a7cb6de4 | backend/core/message_queue.py |
| 2 | Add stream channel constants | e1ef9e78 | backend/core/message_queue.py |

## Deviations from Plan

None - plan executed exactly as written.

## Testing Evidence

**Verification results:**
```
✓ MessageQueue imports without errors
✓ New methods (publish_reliable, consume_reliable, get_queue_depth) exist
✓ MAX_QUEUE_DEPTH constant is 100
✓ Channels class has stream channel constants
✓ Existing pub/sub functionality unchanged

All verification checks passed!
```

**Success criteria confirmed:**
- ✓ publish_reliable() uses Redis Streams with xadd
- ✓ consume_reliable() uses xreadgroup with consumer groups
- ✓ Priority support via separate streams (p0, p1, p2)
- ✓ Queue backlog management trims at MAX_QUEUE_DEPTH=100
- ✓ Dropped messages logged for audit
- ✓ All existing pub/sub methods still work

## Decisions Made

### Redis Streams Priority Separation
**Decision:** Use separate streams per priority level (`stream:{channel}:p{N}`)
**Rationale:** Enables priority-based consumption without complex ordering logic. Consumer can read p0 first, then p1, then p2.
**Alternatives:** Single stream with priority field (requires client-side sorting, less efficient)

### MAX_QUEUE_DEPTH=100
**Decision:** Trim queues when exceeding 100 messages, dropping oldest first
**Rationale:** Per user decision: prevent unbounded memory growth. Old trade signals become stale, better to drop than process late.
**Alternatives:** Block publishers (creates backpressure), use Redis maxmemory policy (affects all keys)

### Fallback to Local Publish
**Decision:** publish_reliable() falls back to _local_publish() when Redis unavailable
**Rationale:** Maintains agent communication during Redis outages (best-effort mode). Better than complete failure.
**Alternatives:** Fail hard and require Redis (breaks local development without Redis)
**Trade-off:** Messages during Redis outage won't persist, lost on restart. Acceptable for development.

## What's Next

**Immediate:**
- 02-03: Signal distribution endpoint will use publish_reliable() for trade signals
- 02-04: Agent decision loop will consume_reliable() with acknowledgment

**Near-term:**
- Wire consume_reliable() to agent loop for continuous processing
- Add monitoring dashboard for get_queue_depth() metrics
- Add integration tests with real Redis Streams

**Open questions:**
- Should we add dead-letter queue for messages that fail repeatedly?
- What retry policy for consumer callback failures (currently: infinite redelivery)?
- Should we expose pending message count (XPENDING) for monitoring?

## Next Phase Readiness

**Blockers:** None

**Prerequisites for next plan:**
- Redis server must be running (development or production)
- Agents must exist to consume messages (already exist)

**Concerns:**
- Redis Streams consumer group state persists across restarts - need reset strategy for development
- No message TTL configured - very old messages could accumulate in streams
- Consumer naming strategy undefined - agents need unique consumer IDs within groups

## Self-Check: PASSED
