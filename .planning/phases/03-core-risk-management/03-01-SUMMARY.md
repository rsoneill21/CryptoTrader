---
phase: 03-core-risk-management
plan: 01
subsystem: risk
tags: [fastapi, sqlalchemy, alembic, risk-service, asyncsession]

# Dependency graph
requires:
  - phase: 02-autonomous-agent-loop
    provides: agent lifecycle, queue orchestration, and operator pause controls
provides:
  - Central RiskService with async trade validation gates
  - Expanded persisted risk settings for exposure, frequency, and stop-loss defaults
  - Risk API models/endpoints that expose and update all new risk fields
affects: [03-02, 03-03, trade-execution, risk-monitor]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Async risk validation uses AsyncSession select/count/sum queries
    - Risk API settings contract maps directly from SQLAlchemy model defaults

key-files:
  created:
    - backend/core/risk.py
    - backend/tests/core/test_risk_service.py
    - backend/tests/api/test_risk_api.py
    - backend/alembic/versions/6f3a2cb7c0c1_add_phase3_risk_settings_columns.py
  modified:
    - backend/db/models.py
    - backend/core/exceptions.py
    - backend/api/risk.py

key-decisions:
  - "RiskService reads latest active paper_trading_states snapshot for balance and falls back to 100000.0 when unavailable."
  - "Risk validation fails closed with RiskException for paused trading, sizing, frequency, and exposure breaches."

patterns-established:
  - "Risk checks centralized in one service callable before order execution."
  - "Risk settings schema and API response fields stay in lockstep via _build_settings_response mapping."

# Metrics
duration: 6 min
completed: 2026-02-06
---

# Phase 3 Plan 01: Core Risk Infrastructure Summary

**Risk guardrails now reject paused/over-limit trades through a centralized async RiskService while new exposure and frequency settings persist and round-trip through the risk API.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-06T15:30:17Z
- **Completed:** 2026-02-06T15:36:53Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- Extended `RiskSettings` with Phase 3 core parameters: asset exposure, trade frequency caps, liquidity threshold, Kraken tier, and default stop-loss percent.
- Added `RiskException` and implemented `RiskService.validate_trade` checks for paused trading, max position sizing, concurrent positions, hourly/day frequency, and per-asset exposure.
- Updated risk settings API schemas/mapping/update flow and added targeted async tests for both service-level rejections and API settings persistence.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend Risk Models and Exceptions** - `ce5813ad` (feat)
2. **Task 2: Implement RiskService Foundation** - `afc5bb87` (feat)
3. **Task 3: Update Risk API Endpoints** - `b9e8e17e` (feat)

Additional deviation fix:

- **Migration compatibility fix** - `a29906ab` (fix)

## Files Created/Modified
- `backend/db/models.py` - Added new persisted `RiskSettings` columns required by Phase 3.
- `backend/core/exceptions.py` - Added `RiskException` (HTTP 400, `risk_limit_exceeded`).
- `backend/core/risk.py` - Implemented centralized async `RiskService` trade-validation logic.
- `backend/api/risk.py` - Expanded settings request/response models and response mapping for new fields.
- `backend/tests/core/test_risk_service.py` - Added paused/frequency/exposure rejection tests.
- `backend/tests/api/test_risk_api.py` - Added risk settings API update/readback tests.
- `backend/alembic/versions/6f3a2cb7c0c1_add_phase3_risk_settings_columns.py` - Added migration for new `risk_settings` columns.

## Decisions Made
- Use latest active `paper_trading_states.state_json` to derive account balance for position-size checks; fallback to `100000.0` when no snapshot exists.
- Keep all trade-risk checks in `RiskService.validate_trade` so execution paths can enforce one consistent fail-closed contract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added missing Alembic migration for new risk columns**
- **Found during:** Overall verification (`get_risk_settings` after `init_db`)
- **Issue:** Runtime query failed with `sqlite3.OperationalError: no such column: risk_settings.max_asset_exposure` on upgraded databases.
- **Fix:** Added migration `6f3a2cb7c0c1` to add all six new `risk_settings` columns with safe defaults.
- **Files modified:** `backend/alembic/versions/6f3a2cb7c0c1_add_phase3_risk_settings_columns.py`
- **Verification:** `init_db` applies migrations successfully and `get_risk_settings` resolves all new fields.
- **Committed in:** `a29906ab`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Migration was required for correctness on existing databases; no scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Risk persistence and core validation infrastructure are ready for 03-02 Kraken rate-limit and liquidity safety work.
- No blockers carried forward.

---
*Phase: 03-core-risk-management*
*Completed: 2026-02-06*
