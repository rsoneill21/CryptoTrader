# Phase 1: Infrastructure Hardening - UAT

**Status:** In Progress
**Phase:** 01
**Date:** 2026-02-05

## Test Plan

### 1. Rate Limiting & Error Handling
- [ ] **TC-01:** Verify rate limiter returns 429 with `Retry-After` header on excessive requests.
- [ ] **TC-02:** Verify Redis failure triggers 503 Service Unavailable (fail-closed behavior).

### 2. Alerts Pagination
- [ ] **TC-03:** Verify `GET /api/alerts` returns `next_cursor` and `has_more` fields instead of page numbers.
- [ ] **TC-04:** Verify fetching with `cursor` parameter returns the next page of results.

### 3. Paper Trading Persistence
- [ ] **TC-05:** Verify paper trading state (positions/balance) is saved to database after trading activity.
- [ ] **TC-06:** Verify state is restored (same session ID and balance) after application restart.

### 4. Async Database API
- [ ] **TC-07:** Verify `GET /api/trades` returns 200 OK (validating async DB connection).

---

## Execution Log

| Test ID | Result | Notes |
|---------|--------|-------|
