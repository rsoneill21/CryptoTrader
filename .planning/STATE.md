# Project State: CryptoTrader

**Last Updated:** 2026-02-05
**Milestone:** Paper trading with functional autonomous agents

## Project Reference

**Core Value:** AI autonomously makes profitable trading decisions without constant human intervention

**Current Focus:** Transform existing scaffolding into functional autonomous trading system where agents actually run continuously, make decisions, and execute trades.

**Key Context:**
- Brownfield project: ~300 files of scaffolding exist but nothing functional
- All agents exist as classes but don't run autonomously
- Paper trading engine exists but state not persisted
- UI pages render but show placeholder/static data
- Kraken integration exists but not wired to agent decisions
- Known tech debt: fail-open rate limiting, sync DB in async routes, no pagination

## Current Position

**Phase:** Phase 1 - Infrastructure Hardening (1 of 11)
**Plan:** 01-02 completed (2 of 4 in phase)
**Status:** In progress
**Progress:** ██░░░░░░░░ 18% (2/11 phases, 2/4 plans in current phase)

**What's happening:**
- Completed 01-02: Structured exceptions and fail-closed rate limiting
- Next: 01-03 Async DB migration or 01-04 Pagination (can run in parallel)

**What works:**
- FastAPI backend with structured API routes
- React frontend with dark theme and routing
- Authentication (login, register, sessions, MFA)
- Kraken API connection and WebSocket market data feed
- Agent framework with base class and lifecycle methods
- Database schema with migrations
- AI chat with multi-provider support (OpenAI, Claude, Ollama)

**What doesn't work:**
- Agents don't run autonomously on schedule
- Paper trading state lost on restart
- Async routes use sync DB queries (blocks event loop)
- No pagination on list endpoints
- Dashboard shows placeholder data
- AI chat doesn't reference trading state

**Fixed in 01-02:**
- ✓ Rate limiter now fails closed with circuit breaker when Redis down
- ✓ Structured exception hierarchy with RFC9457-style error envelopes
- ✓ Error handlers forward headers (Retry-After) to clients

## Performance Metrics

**Velocity:** N/A (no completed plans yet)
**Quality:** N/A (no completed plans yet)
**Estimates:** N/A (no completed plans yet)

## Accumulated Context

### Key Decisions

| Decision | Date | Rationale | Impact |
|----------|------|-----------|--------|
| 11 phases for comprehensive roadmap | 2026-02-04 | Config depth=comprehensive (8-12 phases); 63 requirements need natural grouping | Allows parallelization while maintaining clear delivery boundaries |
| Infrastructure hardening first | 2026-02-04 | Paper state persistence, rate limiting, async DB are critical bugs that invalidate all testing | Risk of state corruption prevented before agent loop |
| Agent loop in Phase 2 | 2026-02-04 | Can't test anything until agents actually run; core autonomous execution must work first | Unblocks all subsequent phases |
| Risk management before position management | 2026-02-04 | Risk limits must enforce before enabling trades; prevents unsafe testing | Safety by design, not afterthought |
| Exchange abstraction after Kraken proven | 2026-02-04 | Premature abstraction causes over-engineering; extract interface from working implementation | Avoids speculation about future exchanges |
| Circuit breaker for Redis rate limiter | 2026-02-05 | 5 failures to open, 60s timeout - conservative defaults prevent false positives while detecting failures | May need tuning based on production Redis patterns |
| Exception-based rate limiting | 2026-02-05 | Raise exceptions instead of returning bool eliminates all fail-open code paths | Callers cannot ignore rate limit failures |
| BaseAppException handler registration order | 2026-02-05 | Registered before HTTPException due to inheritance - FastAPI checks handlers in order | Ensures typed exceptions use specialized handler |

### Active Todos

- [x] ~~Create Phase 1 execution plans (infrastructure fixes)~~ - Completed: 01-01 through 01-04 created
- [x] ~~Rate limiter fail-closed: Raise exception or return 503?~~ - Completed: Raises ServiceUnavailableException (503) with circuit breaker
- [ ] Execute 01-03: Async DB migration (AsyncSession)
- [ ] Execute 01-04: Pagination (cursor-based for trading data)
- [ ] Verify async DB migration path (AsyncSession vs asyncio.to_thread)
- [ ] Document paper trading schema (positions, portfolio_snapshots tables)
- [ ] Install pybreaker dependency for circuit breaker support

### Blockers

None currently.

### Recent Changes

**2026-02-05:**
- Completed 01-02: Structured exceptions and fail-closed rate limiting
- Created BaseAppException hierarchy (RateLimitException, ServiceUnavailableException, DatabaseException)
- Implemented circuit breaker-protected Redis rate limiter (fail-closed)
- Wired structured exceptions into FastAPI error handlers with header forwarding
- Duration: 3 minutes (3 tasks, 3 commits)

**2026-02-04:**
- Roadmap created with 11 phases
- All 63 v1 requirements mapped to phases
- Success criteria derived for each phase (2-7 observable behaviors)
- Requirements traceability updated
- Phase ordering validated against dependencies

### Warnings & Risks

**Critical risks:**
1. **Paper-to-live transition:** All "good enough for simulation" shortcuts become real-money disasters. Must battle-test paper trading for 30+ days before live.
2. **Exchange integration failures:** WebSocket disconnections, rate limiting, API errors require circuit breakers and fail-closed patterns.
3. **State persistence bugs:** Paper trading state loss invalidates all performance metrics and risks duplicate positions in live trading.

**Known tech debt (from PROJECT.md):**
- ~~Rate limiting fails open (INFRA-02)~~ - FIXED in 01-02
- ~~Bare exception handling (INFRA-04)~~ - FIXED in 01-02 (structured exception hierarchy)
- Sync DB queries in async routes (INFRA-03) - IN PROGRESS (01-03 planned)
- No pagination (INFRA-06) - IN PROGRESS (01-04 planned)
- Paper trading state not persisted (INFRA-01) - PLANNED (01-01 completed async session, state persistence next)
- Partial fills not handled (POS-05)
- Slippage/fees not modeled (SAFE-03)
- Stop-loss not enforced (RISK-02)

## Session Continuity

**Last session:** 2026-02-05 16:42-16:45 UTC
**Stopped at:** Completed 01-02-PLAN.md (structured exceptions and fail-closed rate limiting)
**Resume file:** None (can execute 01-03 or 01-04 in parallel)

**For next session:**
1. Read this STATE.md for current position
2. Execute 01-03-PLAN.md (async DB migration) OR 01-04-PLAN.md (pagination)
3. Both plans are independent and can run in parallel

**Context to carry forward:**
- Plan 01-02 establishes exception patterns - use RateLimitException, ServiceUnavailableException, DatabaseException
- Circuit breaker infrastructure in place for Redis - can extend to other services
- Error handlers forward headers - use Retry-After for service degradation
- pybreaker dependency needs installation before 01-03/01-04 execution

**Questions resolved:**
- ~~Async DB migration: AsyncSession (big change) or asyncio.to_thread (wrapper)?~~ - RESEARCH COMPLETE: AsyncSession with asyncpg/aiosqlite (see 01-RESEARCH.md)
- ~~Rate limiter fail-closed: Raise exception or return 503?~~ - COMPLETE: Raises ServiceUnavailableException (503) with Retry-After header
- Paper trading schema: New tables or extend existing? - DEFERRED to state persistence plan

---
*State initialized: 2026-02-04*
