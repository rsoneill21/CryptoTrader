---
phase: 04-position-&-order-management
plan: 02
subsystem: api
tags: [orders, lifecycle, reconciliation, fastapi, sqlalchemy, kraken]

# Dependency graph
requires:
  - phase: 04-position-&-order-management
    provides: manual market/limit entry and close contracts from 04-01
provides:
  - shared order lifecycle reconciliation service for pending/partial/final states
  - pending/status trade APIs that refresh lifecycle state before returning UI payloads
  - regression coverage for partial fills, terminal transitions, and outage behavior
affects: [04-03, pos-05, pos-07, live-trading-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Exchange order refresh now routes through a single idempotent reconciliation path
    - Rejection/cancel metadata is persisted and returned as reason_code and reason_message

key-files:
  created:
    - backend/tests/services/test_order_lifecycle_sync.py
    - backend/tests/api/test_trades_order_lifecycle.py
  modified:
    - backend/services/trade_sync.py
    - backend/api/trades.py

key-decisions:
  - "Persist reason_code with reason_message inside Order.error_message to avoid schema changes while keeping machine-readable rejection metadata."
  - "Keep filled_quantity monotonic during refresh so repeated reconciliation cannot regress exposure."

patterns-established:
  - "Order lifecycle state is normalized to pending/partially_filled/filled/rejected/canceled before API serialization."
  - "Pending orders endpoint reconciles exchange-backed rows and excludes terminal statuses from UI payloads."

# Metrics
duration: 2 min
completed: 2026-02-06
---

# Phase 4 Plan 02: Order Lifecycle Reconciliation Summary

**Pending and partially filled orders now reconcile through one idempotent backend path, and rejection outcomes surface structured code+message metadata to both pending and status APIs.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-06T17:26:27Z
- **Completed:** 2026-02-06T17:27:59Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Added `OrderLifecycleSyncService` to normalize exchange statuses, preserve monotonic fills, and persist terminal reason metadata.
- Wired `GET /api/trades/orders/pending` and `GET /api/trades/orders/{order_id}/status` to run reconciliation before serialization and fail closed on exchange outages.
- Added deterministic regression suites for pending/partial/fill/reject transitions, idempotent refresh behavior, and service-unavailable failure paths.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend trade sync service with explicit order lifecycle reconciliation** - `f492250c` (feat)
2. **Task 2: Wire lifecycle refresh into trades API pending and status endpoints** - `562e5872` (feat)
3. **Task 3: Add regression tests for partial fills, terminal transitions, and failure metadata** - `1d76b815` (test)

## Files Created/Modified
- `backend/services/trade_sync.py` - Added lifecycle reconciliation service with deterministic status mapping, monotonic fill persistence, and packed reason metadata.
- `backend/api/trades.py` - Added pending orders endpoint and status refresh integration with typed outage handling and reason field serialization.
- `backend/tests/services/test_order_lifecycle_sync.py` - Added service-level transition tests for pending/partial/fill and rejection/cancel terminal states.
- `backend/tests/api/test_trades_order_lifecycle.py` - Added API-level tests for pending filtering, idempotent status refresh, rejection metadata, and exchange outage safety.

## Decisions Made
- Persist machine-readable rejection reason codes in bracket-prefixed `Order.error_message` (`[code] message`) so existing schema can serve both UI-friendly and machine-friendly consumers.
- Reconciliation keeps `filled_quantity` monotonic (`max(existing, exchange)`) to prevent drift when exchange snapshots briefly lag.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Refreshed pending orders after commit to avoid async MissingGreenlet on expired ORM fields**
- **Found during:** Task 2 verification
- **Issue:** `list_pending_orders` committed reconciled rows and then serialized expired ORM objects, triggering async lazy-load errors.
- **Fix:** Commit only when lifecycle changes occur, then re-query pending rows before response serialization.
- **Files modified:** `backend/api/trades.py`
- **Verification:** `backend/venv/bin/python -m pytest backend/tests/api/test_trades_order_lifecycle.py -k "pending or status or rejection" -q`
- **Committed in:** `562e5872` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Bug fix was required for endpoint correctness; no scope creep.

## Issues Encountered
None.

## Authentication Gates
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 04-03 UI can rely on a lifecycle-consistent pending feed that excludes terminal orders and includes partial fill quantities.
- Rejection/cancel status payloads now contain reason code/message pairs needed for ticket and activity feed messaging.

---
*Phase: 04-position-&-order-management*
*Completed: 2026-02-06*
