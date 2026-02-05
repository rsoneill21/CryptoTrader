---
phase: 01-infrastructure-hardening
plan: 16
subsystem: infra
tags: [fastapi, observability, kraken]

# Dependency graph
requires:
  - phase: 01-15
    provides: Structured exception handlers for backend APIs
provides:
  - System health endpoints raise ServiceUnavailableException when Kraken probes fail
  - ServiceUnavailableException exposes endpoint/dependency metadata for monitoring
affects: [01-verification, 02-agent-runtime]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dependency probes log outages via ServiceUnavailableException helpers"

key-files:
  created: []
  modified:
    - backend/api/system.py
    - backend/core/exceptions.py

key-decisions:
  - "Health endpoints fail closed when Kraken outages occur instead of returning degraded payloads"
  - "BaseAppException logs now store an error_message field for structured logging parity"

patterns-established:
  - "_raise_dependency_unavailable centralizes logging + ServiceUnavailableException creation for dependency outages"

# Metrics
duration: 4 min
completed: 2026-02-05
---

# Phase 01 Plan 16: System Health Gap Closure Summary

**Kraken health probes now raise ServiceUnavailableException with endpoint/dependency metadata so monitoring captures outages.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-05T19:20:43Z
- **Completed:** 2026-02-05T19:25:16Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added `_probe_kraken_latency` helper so `/health` and `/connection-status` run a single Kraken ping and raise typed outages with stack traces
- Updated ServiceUnavailableException to merge endpoint/dependency metadata, giving structured payloads to the global error handler
- Verified FastAPI boot via `uvicorn main:app --reload --port 8001` inside the project virtualenv to ensure imports still resolve

## Task Commits

Each task was committed atomically:

1. **Task 1: Instrument system health endpoints with structured logging** - `a9c8ef2` (fix)
2. **Task 2: Ensure ServiceUnavailableException payload covers system diagnostics** - `5fe58db` (feat)

## Files Created/Modified
- `backend/api/system.py` - Adds shared dependency outage helper plus Kraken latency probe for `/health` and `/connection-status`
- `backend/core/exceptions.py` - Extends ServiceUnavailableException/BaseAppException metadata for richer observability payloads

## Decisions Made
- Health endpoints now fail closed on Kraken outages, surfacing ServiceUnavailableException through the global error envelope instead of returning degraded payloads
- BaseAppException log entries now emit `error_message` consistently to align with the structured logging contract used elsewhere in the backend

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Running `uvicorn main:app --reload` outside the repo virtualenv lacked FastAPI; re-ran via `.venv` (`. ../.venv/bin/activate && uvicorn ...`) so verification could complete.

## Next Phase Readiness
- System API now surfaces typed outages, so Phase 1 verification can re-run without `/health` masking Kraken failures.
- Ready to proceed to the remaining infrastructure verification items and close out Phase 1.

---
*Phase: 01-infrastructure-hardening*
*Completed: 2026-02-05*
