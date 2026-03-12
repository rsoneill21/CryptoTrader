---
phase: 01-infrastructure-hardening
plan: 17
subsystem: infra
tags: [fastapi, exceptions, monitoring]

# Dependency graph
requires:
  - phase: 01-infrastructure-hardening
    provides: "01-15 structured exception scaffolding"
provides:
  - Market analysis endpoint fails closed when downstream collectors fail
  - Logger exception traces emitted for indicator/insight/sentiment outages
  - Async test harness dependency (aiosqlite) captured in backend requirements
affects: [02-autonomous-agent-loop, monitoring]

# Tech tracking
tech-stack:
  added: [aiosqlite]
  patterns:
    - ServiceUnavailableException emits dependency + operation metadata for observability

key-files:
  created: []
  modified:
    - backend/api/market.py
    - backend/tests/test_market_api.py
    - backend/requirements.txt

key-decisions:
  - "Fail /api/market/analysis entirely when any collector fails to keep dashboards honest"
  - "Codify aiosqlite in requirements so async tests and dev servers bootstrap reliably"

patterns-established:
  - "Logger.exception + ServiceUnavailableException used together for every upstream service outage"

# Metrics
duration: 7 min
completed: 2026-02-05
---

# Phase 01 Plan 17: Market analysis outages Summary

**Market analysis now fails closed with ServiceUnavailableException when indicator, insight, or sentiment collectors break**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-05T17:17:44Z
- **Completed:** 2026-02-05T17:25:27Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Indicator, insight, and sentiment fetches now log stack traces and raise `ServiceUnavailableException` instead of returning partial data silently
- Added pytest coverage ensuring each dependency failure trips the typed error path with dependency metadata
- Recorded `aiosqlite` in backend requirements so async DB layer works in local tests and tooling

## Task Commits

1. **Task 1: Replace warning-only blocks with typed exceptions** - `02d886e` (fix)
2. **Task 2: Ensure degraded-mode responses are explicit when tolerated** - `6b175b4` (test)

## Files Created/Modified
- `backend/api/market.py` - wraps indicator, insights, and sentiment collectors with `logger.exception` + `ServiceUnavailableException`
- `backend/tests/test_market_api.py` - adds regression coverage for dependency failures surfacing typed errors
- `backend/requirements.txt` - lists `aiosqlite` so async sqlite driver installs for dev/tests

## Decisions Made
- Always fail `/api/market/analysis` with 503 when any downstream collector fails; explicit degradations can be reconsidered later but observability takes priority now
- Capture dependency context (dependency + operation) inside `ServiceUnavailableException` details for easier monitoring queries

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added missing aiosqlite dependency**
- **Found during:** Task 2 (Ensure degraded-mode responses are explicit when tolerated)
- **Issue:** Running pytest imported the async DB engine which requires `aiosqlite`, but the dependency was absent from `backend/requirements.txt`, preventing the suite from starting
- **Fix:** Declared `aiosqlite>=0.19.0` in backend requirements so the async SQLite driver is installed when setting up the backend tooling
- **Files modified:** backend/requirements.txt
- **Verification:** Recreated a virtualenv, installed requirements, and reran `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_market_api.py -k analysis --maxfail=1`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Required to unblock pytest and confirm API contract changes; no functional scope creep.

## Issues Encountered
- Local pytest run initially failed because `python3` lacked dependencies; created a throwaway virtualenv, installed backend requirements (now including `aiosqlite`), ran tests, and removed the venv afterward

## Next Phase Readiness
- `/api/market/analysis` now surfaces typed outages for every collector, meeting the gap report requirement and allowing 01-16 (system health) hardening to proceed
- Outstanding work: system health endpoints still need the same typed error treatment (handled by plan 01-16); no new blockers introduced

---
*Phase: 01-infrastructure-hardening*
*Completed: 2026-02-05*
