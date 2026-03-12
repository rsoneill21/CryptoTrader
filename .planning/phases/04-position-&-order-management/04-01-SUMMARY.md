---
phase: 04-position-&-order-management
plan: 01
subsystem: api
tags: [fastapi, orders, positions, risk-service, paper-trading, pytest]

# Dependency graph
requires:
  - phase: 03-core-risk-management
    provides: centralized RiskService validation, liquidity checks, and stop-loss aware paper execution
provides:
  - Manual `/api/trades/orders` entry contract for market and limit intents with lifecycle response fields
  - Risk-based quantity sizing helper derived from account equity and reference price
  - Partial/full close semantics using market execution price and structured close metadata
  - Regression suite for market/limit entry, risk rejections, and partial/full close outcomes
affects: [04-02, 04-03, live-trading-ui, order-lifecycle-reconciliation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Manual order submission always resolves quantity server-side, then gates through RiskService before persistence
    - Close actions return normalized execution metadata and preserve partial-close lifecycle history

key-files:
  created:
    - backend/tests/api/test_trades_order_entry.py
  modified:
    - backend/api/trades.py
    - backend/core/risk.py
    - backend/core/paper_trading.py

key-decisions:
  - "`risk_percent` sizing uses account equity snapshot divided by reference price, enforced server-side only."
  - "Limit submits persist as pending lifecycle orders without immediate fill side effects."
  - "Close requests default to full quantity, but partial requests persist audit metadata and reduce remaining size."

patterns-established:
  - "Manual open/close requests call RiskService gates before recording execution outcomes."
  - "Order and close responses expose UI-ready reason/status fields for ticket and toast mapping."

# Metrics
duration: 13 min
completed: 2026-02-06
---

# Phase 4 Plan 01: Manual Order Entry and Close Contract Summary

**Manual market/limit order entry now runs through server-side risk sizing/gates, and close actions support partial/full market execution with lifecycle-ready response metadata.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-02-06T17:04:58Z
- **Completed:** 2026-02-06T17:17:52Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Added `POST /api/trades/orders` with market/limit intent support, `quantity` xor `risk_percent`, and normalized order lifecycle response fields.
- Extended `RiskService` with reusable account-equity and risk-percent sizing helpers so manual position sizing is enforced server-side.
- Upgraded close flow to support partial quantity requests, market-price execution semantics, close intent metadata, and structured failure reason codes.
- Added focused regression tests covering market/limit submission, risk rejection non-persistence, deterministic risk sizing, and partial/full close behavior.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add risk-gated manual order submit endpoint for market and limit** - `e88d9129` (feat)
2. **Task 2: Add close-position API support for partial quantity and market execution semantics** - `734000df` (feat)
3. **Task 3: Add focused API regression coverage for entry and close contracts** - `f6504ee6` (test)

## Files Created/Modified
- `backend/api/trades.py` - Added manual order submit contract, lifecycle response schema, and partial/full close execution behavior.
- `backend/core/risk.py` - Added account equity accessor, risk-percent sizing helper, and close-risk validation entrypoint.
- `backend/core/paper_trading.py` - Added cached-price accessor for close execution price selection.
- `backend/tests/api/test_trades_order_entry.py` - Added API-level regression suite for market/limit entry, risk sizing/rejection, and close semantics.

## Decisions Made
- Use `risk_percent` as notional-equity allocation (`equity * percent / reference_price`) to avoid client-side quantity math.
- Keep limit order submissions in `pending` state with zero filled quantity so pending orders remain distinct from open positions.
- Record partial-close intent metadata on the source trade while creating explicit closed-trade records for the closed slice.

## Deviations from Plan

None - plan executed exactly as written.

## Authentication Gates

None.

## Issues Encountered
- Close tests initially failed when engine state had no matching open symbol positions; test doubles were updated to isolate API-contract assertions.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Manual entry/close API contracts are in place for lifecycle reconciliation work in 04-02.
- Pending-vs-filled order state is now explicit, enabling downstream reconciliation and UI pending section wiring.

---
*Phase: 04-position-&-order-management*
*Completed: 2026-02-06*
