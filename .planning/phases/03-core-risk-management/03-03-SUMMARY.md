---
phase: 03-core-risk-management
plan: 03
subsystem: risk
tags: [risk-service, trading-control, paper-trading, stop-loss, pytest]

# Dependency graph
requires:
  - phase: 03-core-risk-management
    provides: persisted risk settings and baseline RiskService validation gates from 03-01
provides:
  - Daily halt checks that combine realized and unrealized P&L before accepting new trades
  - Day-bound trading lockouts that deny same-day resume after a daily-loss halt
  - Engine-side stop-loss defaults and automatic stop-triggered exits in paper trading
  - Integration tests proving pause, sizing, frequency, stop-loss, and daily-halt transitions
affects: [03-phase-closeout, trade-execution, position-management, safety-monitoring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - RiskService runs a pre-trade daily halt check using realized plus unrealized P&L
    - TradingControl encodes daily-loss lockouts with halted_until_date and next-day-only resume
    - PaperTradingEngine enforces stop-loss exits directly inside market-price updates

key-files:
  created:
    - backend/tests/core/test_daily_halt.py
    - backend/tests/core/test_paper_stop_loss.py
    - backend/tests/integration/test_risk_flow.py
  modified:
    - backend/core/risk.py
    - backend/core/trading_control.py
    - backend/core/paper_trading.py
    - backend/agents/risk_monitor.py

key-decisions:
  - "Daily halt logic computes today's realized trade P&L plus unrealized open-position P&L from latest market prices."
  - "Daily-loss pauses use a next-day lockout date so same-day resume attempts are always denied."
  - "Paper stop-loss defaults come from RiskSettings.default_stop_loss_pct when a signal omits explicit stop_loss."

patterns-established:
  - "Risk checks can call check_daily_halt first, then fail closed on paused state."
  - "Stop-loss exits are recorded with explicit 'Stop-Loss Triggered' reasoning metadata."

# Metrics
duration: 9 min
completed: 2026-02-06
---

# Phase 3 Plan 03: Active Loss Protection Summary

**Daily loss halts now include unrealized exposure, enforce next-day-only resumes, and paper positions auto-close when stop-loss thresholds are breached.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-06T15:51:06Z
- **Completed:** 2026-02-06T16:00:15Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- Added `RiskService.check_daily_halt` to compute total daily P&L (realized + unrealized) and pause trading when the configured daily loss limit is breached.
- Extended `TradingControl` with `halted_until_date` lockout behavior so same-day resume requests are blocked and next-day resumes are allowed.
- Added paper-engine stop-loss support (`stop_loss`, `stop_loss_price`) with automatic trigger-based exits and explicit stop-loss exit reasoning metadata.
- Added focused and integrated test coverage for daily halt transitions, stop-loss default/trigger behavior, and full risk guardrail flow.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement Daily Total P&L Tracking and Halt** - `7dbd6616` (feat)
2. **Task 2: Add Stop-Loss to Paper Trading Engine** - `944a2fd8` (feat)
3. **Task 3: Integrated Risk Flow Verification** - `432caab5` (test)

Additional stabilization fix:

- **Integration reliability fix** - `a27531ef` (fix)

## Files Created/Modified
- `backend/core/risk.py` - Added daily halt computation and pre-trade halt checks.
- `backend/core/trading_control.py` - Added day-bound halt lockout state and same-day resume blocking.
- `backend/core/paper_trading.py` - Added stop-loss defaults, stop-loss trigger exits, and state serialization support for stop prices.
- `backend/agents/risk_monitor.py` - Added periodic `RiskService.check_daily_halt` invocation.
- `backend/tests/core/test_daily_halt.py` - Added tests for breach pause, same-day resume denial, and next-day resume allowance.
- `backend/tests/core/test_paper_stop_loss.py` - Added tests for default stop-loss derivation and buy/sell trigger exits.
- `backend/tests/integration/test_risk_flow.py` - Added integrated lifecycle coverage across pause, sizing, frequency, stop-loss, and daily-halt behavior.

## Decisions Made
- Daily realized P&L is measured from trades closed today (`Trade.exit_time` in current UTC day), while unrealized P&L is computed from open trades using latest `MarketData` prices.
- Daily-loss pauses use `lock_until_next_day=True` and set `halted_until_date` to the next UTC date, making same-day resume deterministic.
- Stop-loss metadata is persisted in paper trading state snapshots so stop thresholds survive session persistence/restoration.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stabilized integration test against external liquidity variability**
- **Found during:** Final combined verification run
- **Issue:** `test_risk_flow` intermittently failed because `RiskService.validate_trade` also runs live liquidity checks against Kraken order books.
- **Fix:** Mocked `core.risk.kraken_service.get_orderbook` in the integration test to provide deterministic depth and isolate intended risk assertions.
- **Files modified:** `backend/tests/integration/test_risk_flow.py`
- **Verification:** `./venv/bin/python -m pytest tests/core/test_daily_halt.py tests/core/test_paper_stop_loss.py tests/integration/test_risk_flow.py -q`
- **Committed in:** `a27531ef`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Fix removed test flakiness without changing production behavior; no scope creep.

## Issues Encountered
- `pytest` was not available on PATH; verification used `backend/venv/bin/python -m pytest ...` to run tests in the project virtualenv.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Core loss-protection mechanics are now active for both global risk halts and per-position stop-loss exits.
- Phase 3 risk controls are ready for phase closeout/consumption by downstream execution and position-management work.

---
*Phase: 03-core-risk-management*
*Completed: 2026-02-06*
