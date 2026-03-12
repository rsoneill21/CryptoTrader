---
phase: 01-infrastructure-hardening
plan: 02
subsystem: infra
tags: [exceptions, rate-limiting, error-handling, redis, circuit-breaker, pybreaker, fastapi]

# Dependency graph
requires:
  - phase: 01-infrastructure-hardening
    provides: Research on fail-closed patterns and structured exception hierarchies
provides:
  - Typed exception hierarchy (BaseAppException, RateLimitException, ServiceUnavailableException, DatabaseException)
  - Fail-closed rate limiter with circuit breaker protection
  - RFC9457-style error envelope with header forwarding
affects: [01-03-async-db, 01-04-pagination, all-future-api-development]

# Tech tracking
tech-stack:
  added: [pybreaker]
  patterns: [fail-closed-rate-limiting, structured-exception-hierarchy, rfc9457-error-envelope]

key-files:
  created:
    - backend/core/exceptions.py
  modified:
    - backend/core/rate_limit.py
    - backend/api/errors.py

key-decisions:
  - "Circuit breaker with 5 failures threshold and 60s timeout for Redis"
  - "Rate limiter raises exceptions instead of returning bool to prevent fail-open logic"
  - "BaseAppException registered before HTTPException in handler chain due to inheritance"

patterns-established:
  - "Pattern 1: Structured exceptions with error_code, message, details, and optional headers"
  - "Pattern 2: Fail-closed service dependencies raise ServiceUnavailableException with Retry-After"
  - "Pattern 3: Error handlers extract exception metadata and forward headers to JSONResponse"

# Metrics
duration: 3min
completed: 2026-02-05
---

# Phase 01 Plan 02: Structured Exceptions & Fail-Closed Rate Limiting Summary

**Fail-closed Redis rate limiter with circuit breaker and typed exception hierarchy that surfaces infra failures as RFC9457-style API errors**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-05T16:42:33Z
- **Completed:** 2026-02-05T16:45:16Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Built typed exception hierarchy with BaseAppException, RateLimitException, ServiceUnavailableException, DatabaseException
- Transformed rate limiter from fail-open (security vulnerability) to fail-closed with circuit breaker
- Wired structured exceptions into FastAPI error handlers with header forwarding (Retry-After)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add typed application exceptions** - `ce6cb34` (feat)
2. **Task 2: Fail-closed rate limiter** - `4d03919` (feat)
3. **Task 3: Wire exceptions into error handler** - `0dd4cef` (feat)

## Files Created/Modified
- `backend/core/exceptions.py` - BaseAppException with error_code/message/details/headers; RateLimitException (429), ServiceUnavailableException (503), DatabaseException (500)
- `backend/core/rate_limit.py` - Circuit breaker-protected rate limiter that raises exceptions instead of returning bool; fail-closed on Redis outage
- `backend/api/errors.py` - Added base_app_exception_handler that extracts exception metadata and forwards headers to JSONResponse

## Decisions Made

**Circuit breaker configuration:** 5 failures to open, 60s timeout before retry. Conservative defaults chosen to prevent false positives while detecting genuine Redis failures.

**Exception-based rate limiting:** Changed `check_rate_limit` from returning `bool` to raising exceptions. Eliminates fail-open code paths entirely - callers can't ignore rate limit failures.

**Handler registration order:** BaseAppException registered before HTTPException in FastAPI handler chain. Required because BaseAppException inherits from HTTPException, and FastAPI checks handlers in registration order.

**Structured logging:** Added contextual logging (circuit state, error types, request keys) to all rate limit paths for observability during Redis failures.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all imports, syntax, and integration points worked as expected.

## User Setup Required

**pybreaker dependency:** The fail-closed rate limiter requires the `pybreaker` library for circuit breaker functionality. If not already installed, add to requirements:

```bash
pip install pybreaker
```

Verify installation: `python3 -c "import pybreaker; print('OK')"` should succeed.

No other external service configuration required.

## Next Phase Readiness

**Ready for:**
- Async DB migration (01-03) can use DatabaseException for async query failures
- Pagination (01-04) can use structured exceptions for cursor decode errors
- All future API development has consistent error handling infrastructure

**Blockers:** None

**Concerns:** Circuit breaker thresholds (5 failures, 60s timeout) are conservative defaults. May need tuning in production based on Redis failure patterns. Monitor circuit breaker state in logs to validate thresholds.

**Testing recommendation:** Kill Redis during development and verify endpoints return 503 with Retry-After header, not 200 or 500. Circuit breaker should open after 5 failures.

---
*Phase: 01-infrastructure-hardening*
*Completed: 2026-02-05*
