---
status: diagnosed
trigger: "Investigate why POST /api/trades and POST /api/trades/system return 500 'Unexpected Error'"
created: 2026-02-05T00:02:00Z
updated: 2026-02-05T00:08:00Z
goal: find_root_cause_only
---

## Current Focus

hypothesis: CONFIRMED - POST endpoints don't use selectinload(Trade.orders) before calling _serialize_trade(), causing relationship access failure
test: compare list_active_trades (line 424) which uses selectinload vs create_manual_trade which doesn't
expecting: list_active_trades works, POST endpoints fail when accessing trade.orders
next_action: confirm root cause and document fix

## Symptoms

expected: POST /api/trades and POST /api/trades/system should accept paper trade requests and return success
actual: Both endpoints return HTTP 500 with {"error":{"code":"server_error","message":"Unexpected error"}}
errors: HTTP 500 "Unexpected error" - generic server error response
reproduction: POST request to /api/trades or /api/trades/system on clean uvicorn instance
started: Unknown - user reports inability to place paper trades via API

## Eliminated

## Evidence

- timestamp: 2026-02-05T00:03:00Z
  checked: backend/api/trades.py POST endpoints (lines 177-260)
  found: |
    Both endpoints are simple and straightforward:
    - create_manual_trade: Creates Trade object, db.add(), commit(), refresh()
    - create_system_trade: Creates Trade object, db.add(), commit(), refresh()
    - Both have try/except blocks that should catch DB errors and return HTTPException with detail message
    - No obvious logic errors or missing imports in endpoint code itself
  implication: Endpoints look correct. Error must be happening at framework level (error handler, middleware, or database connection)

- timestamp: 2026-02-05T00:04:00Z
  checked: backend/api/errors.py error handling (line 218)
  found: |
    generic_exception_handler uses default_code="unexpected_error" (not "server_error")
    User reported error code is "server_error" which doesn't match this handler
    Error format matches: {"error":{"code":"...","message":"Unexpected error"}}
  implication: Either user misreported the code, or there's another error handler, or the code was recently changed

- timestamp: 2026-02-05T00:06:00Z
  checked: _serialize_trade function in trades.py (lines 367-401)
  found: |
    Line 399: orders=[_build_order_summary(order) for order in trade.orders]
    After db.commit() and db.refresh(), _serialize_trade tries to access trade.orders relationship
    If relationship is not loaded and object is detached from session, this will fail
  implication: LIKELY CAUSE - accessing lazy-loaded relationship after session operations

- timestamp: 2026-02-05T00:06:00Z
  checked: database.py AsyncSessionLocal configuration (line 45-49)
  found: |
    expire_on_commit=False is set (line 48)
    This should prevent attributes from expiring after commit
    But relationships might still need explicit loading
  implication: expire_on_commit=False helps but doesn't guarantee relationship loading works

- timestamp: 2026-02-05T00:07:00Z
  checked: Comparison between list_active_trades (line 424) and create_manual_trade (line 204)
  found: |
    list_active_trades:
      select(Trade).options(selectinload(Trade.orders)) <-- LOADS RELATIONSHIP
      Then calls _serialize_trade(trade) - works fine

    create_manual_trade:
      db.add(trade)
      await db.commit()
      await db.refresh(trade)
      return _serialize_trade(trade) <-- FAILS - orders not loaded!

    Same issue in create_system_trade (line 247)
  implication: ROOT CAUSE CONFIRMED - POST endpoints don't eagerly load orders relationship before serialization

## Resolution

root_cause: POST /api/trades and POST /api/trades/system don't eagerly load the Trade.orders relationship before calling _serialize_trade(). When _serialize_trade tries to access trade.orders (line 399), the relationship isn't loaded and causes an exception. list_active_trades works correctly because it uses .options(selectinload(Trade.orders)).

fix: After db.refresh(trade), explicitly load the orders relationship using db.execute with selectinload, or await db.refresh(trade, attribute_names=["orders"]) in SQLAlchemy 2.0+, or initialize trade.orders to empty list before serialization.

verification: Test POST /api/trades and POST /api/trades/system - should return 201 with trade data including empty orders array.

files_changed:
  - backend/api/trades.py (create_manual_trade and create_system_trade functions)
