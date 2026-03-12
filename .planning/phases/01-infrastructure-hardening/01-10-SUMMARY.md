---
phase: 01-infrastructure-hardening
plan: 10
subsystem: api
tags: [fastapi, sqlalchemy, trades]

# Dependency graph
requires:
  - phase: 01-01
    provides: Async trades API session + helper utilities
provides:
  - POST /api/trades endpoints reload trades with orders eagerly loaded
  - Paper trading creation no longer throws DetachedInstanceError during serialization
affects: [phase-01-11, phase-02]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Eager relationship reload via selectinload prior to serialization in async routes"

key-files:
  created: []
  modified:
    - backend/api/trades.py

key-decisions:
  - "Re-query created trades with selectinload(Trade.orders) to guarantee relationship access post-commit"

patterns-established:
  - "Async trade endpoints refresh + scalar reload pattern to avoid DetachedInstanceError"

# Metrics
duration: 0 min
completed: 2026-02-05
---

# Phase 1 Plan 10: Trade Creation Orders Reload Summary

**POST trade creation endpoints now eager-load orders to return complete payloads without DetachedInstanceError.**

## Performance

- **Duration:** 0 min
- **Started:** 2026-02-05T16:42:11Z
- **Completed:** 2026-02-05T16:42:41Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Added selectinload-based reload in `create_manual_trade` so `trade.orders` is populated before serialization
- Mirrored the eager reload in `create_system_trade` ensuring both POST endpoints return complete `orders` arrays
- Eliminated DetachedInstanceError surfaced in UAT Test 3, unblocking paper trading persistence verification

## Task Commits

1. **Task 1: Reload trade with orders relationship before serialization** - `0011934` (fix)

**Plan metadata:** _Pending (this file)_

## Files Created/Modified
- `backend/api/trades.py` - Reloads newly created trades with `selectinload(Trade.orders)` after commit/refresh

## Decisions Made
- None - followed plan as specified

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Local FastAPI server was not running in this environment, so the curl-based verification will need to be exercised in QA/staging.

## User Setup Required
None - no external configuration required.

## Next Phase Readiness
- Paper trading trade creation endpoints now return 201 responses with populated orders arrays, enabling UAT Test 3 to proceed and allowing plan 01-11 (session reset/archive API) to build on a working POST baseline.

---
*Phase: 01-infrastructure-hardening*
*Completed: 2026-02-05*
