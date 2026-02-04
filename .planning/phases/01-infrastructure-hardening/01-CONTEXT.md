# Phase 1: Infrastructure Hardening - Context

**Gathered:** 2026-02-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix foundational reliability issues so the system is safe for autonomous operation. Covers: paper trading state persistence, rate limiter fail-closed behavior, async database queries, structured exception handling, and API pagination. No new features — this hardens existing infrastructure.

</domain>

<decisions>
## Implementation Decisions

### State persistence strategy
- Persist ALL paper trading state: open positions, cash balance, trade history, pending orders, P&L snapshots — complete restoration on restart
- Support resettable sessions: user can reset to start fresh, but previous session data is archived for comparison
- On startup with existing state, agents load state but stay paused until user explicitly clicks "Resume" — safer for autonomous system
- Write timing: Claude's discretion on immediate writes vs periodic snapshots — pick what's practical for paper trading reliability

### Failure behavior
- Rate limiter when Redis is down: Claude's discretion — pick the safest default (fail-closed recommended in roadmap)
- Database errors shown to user: typed error with hint (e.g., "Database temporarily unavailable") — no stack traces or internals leaked to client
- Exception type granularity: Claude's discretion — pick the right level between broad categories and fine-grained subtypes
- Unhandled exception strategy: Claude's discretion — pick between top-level catch vs let-it-crash based on what works for a long-running trading server

### API response contracts
- Pagination style: Claude's discretion — pick what fits trading data (cursor vs offset)
- Error response format: standard envelope — every error returns `{"error": {"type": "...", "message": "...", "details": {}}}` for predictable frontend consumption
- Rate limit responses: include Retry-After header and remaining quota so frontend can show countdown or backoff
- Default page size: 25 items for list endpoints

### Logging & observability
- Log format: structured JSON — machine-readable for parsing and future log aggregation
- Exception context: full context — stack trace + request details (user, endpoint, params, body) + system state for maximum debuggability
- Slow query logging: Claude's discretion — decide if threshold-based slow query detection is useful during async DB migration
- Log destination: file + stdout — rotating log files AND console output

### Claude's Discretion
- Write timing for state persistence (immediate vs periodic)
- Rate limiter fail mode (fail-closed recommended)
- Exception type granularity (broad vs fine-grained)
- Unhandled exception strategy (catch-all vs crash)
- Pagination style (cursor vs offset)
- Slow query logging threshold

</decisions>

<specifics>
## Specific Ideas

- Paper trading sessions should be archivable — user starts fresh but can look back at previous session performance
- State loads on startup but agents don't auto-resume — user must confirm before autonomous trading continues
- Error envelope format locked: `{"error": {"type": "...", "message": "...", "details": {}}}`
- Rate limit 429 responses must include Retry-After header

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-infrastructure-hardening*
*Context gathered: 2026-02-04*
