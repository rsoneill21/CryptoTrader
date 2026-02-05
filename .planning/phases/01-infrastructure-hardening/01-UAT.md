---
status: diagnosed
phase: 01-infrastructure-hardening
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md, 01-04-SUMMARY.md, 01-05-SUMMARY.md, 01-06-SUMMARY.md, 01-07-SUMMARY.md, 01-08-SUMMARY.md, 01-09-SUMMARY.md]
started: 2026-02-05T18:10:00Z
updated: 2026-02-05T16:25:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Async Trades API Response
expected: Start the FastAPI server and call GET /api/trades (or another trades endpoint). Response returns promptly with trades data; concurrent requests do not block because AsyncSession is used end-to-end.
result: pass

### 2. Rate Limiter Fail-Closed Behavior
expected: Stop/disable Redis, hit a rate-limited endpoint (e.g., POST /api/auth/login). Response should be HTTP 503 with Retry-After, proving fail-closed logic.
result: pass

### 3. Paper Trading State Persists on Restart
expected: After placing a trade, restart the backend. Paper trading positions, balances, and P&L should restore exactly as before.
result: issue
reported: "Unable to place a paper trade via API. Both POST /api/trades and POST /api/trades/system return 500 Unexpected Error (even on clean uvicorn instance), so there is no state change to validate across restarts."
severity: major

### 4. Paper Trading Session Reset
expected: Trigger the session reset/archive workflow. Previous session is archived, and a new clean session (no positions, default cash) starts.
result: issue
reported: "No API endpoint exposes the session reset/archive functionality. reset_to_clean_state and archive_current_session methods exist in PaperTradingEngine but are not callable via REST API."
severity: major

### 5. Alerts Cursor Pagination
expected: GET /api/alerts?limit=5 returns alerts plus next_cursor + has_more. Using the cursor retrieves the next page with stable ordering even if new alerts arrive.
result: issue
reported: "Cursor pagination is broken. Page 1 returns IDs 8,7,6 with next_cursor. Page 2 using that cursor returns the SAME IDs 8,7,6 instead of the next page (5,4,3). The cursor is not being applied to filter results."
severity: major

### 6. Structured Exception Response
expected: Force an application error (e.g., exceed rate limit). Error payload should follow the structured format with error_code/message/details rather than raw 500.
result: pass

## Summary

total: 6
passed: 3
issues: 3
pending: 0
skipped: 0

## Gaps

- truth: "Paper trading positions persist across backend restarts"
  status: failed
  reason: "User reported: Unable to place a paper trade via API. POST /api/trades and POST /api/trades/system both return 500 Unexpected Error even on a clean uvicorn instance, so no state change can be made to verify persistence."
  severity: major
  test: 3
  root_cause: "POST endpoints don't eagerly load Trade.orders relationship before calling _serialize_trade(). Line 399 accesses trade.orders but relationship isn't loaded."
  artifacts:
    - path: "backend/api/trades.py"
      issue: "create_manual_trade and create_system_trade don't use selectinload(Trade.orders)"
  missing:
    - "After db.refresh(trade), reload trade with selectinload(Trade.orders) before serialization"
  debug_session: ".planning/debug/api-trades-post-500-error.md"

- truth: "User can trigger session reset/archive to start fresh paper trading session"
  status: failed
  reason: "No API endpoint exposes reset_to_clean_state or archive_current_session methods. Functionality exists in PaperTradingEngine but isn't callable via REST API."
  severity: major
  test: 4
  artifacts:
    - path: "backend/core/paper_trading.py"
      issue: "reset_to_clean_state and archive_current_session methods exist but not exposed"
    - path: "backend/api/strategies.py"
      issue: "No route defined for session reset/archive"
  missing:
    - "Add POST /api/paper-trading/reset endpoint"
    - "Add POST /api/paper-trading/archive endpoint"

- truth: "Cursor pagination returns next page when cursor token is provided"
  status: failed
  reason: "Page 1 returns IDs 8,7,6 with next_cursor. Page 2 using that cursor returns SAME IDs 8,7,6 instead of next page 5,4,3. Cursor not being applied as filter."
  severity: major
  test: 5
  root_cause: "apply_cursor_pagination uses `timestamp_column < cursor_timestamp` and `id_column < cursor_id` which is correct for ASC ordering, but alerts are sorted DESC (newest first). For DESC, comparisons should use `>` not `<`."
  artifacts:
    - path: "backend/core/pagination.py"
      issue: "Lines 56-57 use < comparison assuming ASC order, but list endpoints sort DESC"
  missing:
    - "Change line 56 to `timestamp_column > cursor_timestamp`"
    - "Change line 57 to `id_column > cursor_id`"
    - "Or add direction parameter to handle both ASC and DESC ordering"
  debug_session: "inline diagnosis"
