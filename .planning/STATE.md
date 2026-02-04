# Project State: CryptoTrader

**Last Updated:** 2026-02-04
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

**Phase:** Phase 1 - Infrastructure Hardening
**Plan:** Not yet created
**Status:** Planning
**Progress:** █░░░░░░░░░ 0%

**What's happening:**
- Roadmap created with 11 phases covering 63 v1 requirements
- Next step: Create execution plan for Phase 1 (infrastructure fixes)

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
- Rate limiter fails open when Redis down
- Async routes use sync DB queries (blocks event loop)
- No pagination on list endpoints
- Dashboard shows placeholder data
- AI chat doesn't reference trading state

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

### Active Todos

- [ ] Create Phase 1 execution plan (infrastructure fixes)
- [ ] Verify async DB migration path (AsyncSession vs asyncio.to_thread)
- [ ] Document paper trading schema (positions, portfolio_snapshots tables)
- [ ] Identify pagination candidates (trades, strategies, alerts endpoints)

### Blockers

None currently.

### Recent Changes

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
- Rate limiting fails open (INFRA-02)
- Sync DB queries in async routes (INFRA-03)
- No pagination (INFRA-06)
- Bare exception handling (INFRA-04)
- Paper trading state not persisted (INFRA-01)
- Partial fills not handled (POS-05)
- Slippage/fees not modeled (SAFE-03)
- Stop-loss not enforced (RISK-02)

## Session Continuity

**For next session:**
1. Read this STATE.md for current position
2. Read ROADMAP.md for phase structure
3. Create execution plan for Phase 1 via `/gsd:plan-phase 1`

**Context to carry forward:**
- Depth=comprehensive means 5-10 execution plans per phase
- Parallelization=true means identify independent work streams
- Research phase 6-8 need deeper research (Backtrader, sentiment APIs, Kraken live trading)
- Code exists (~300 files) - modify, don't recreate

**Questions to resolve:**
- Async DB migration: AsyncSession (big change) or asyncio.to_thread (wrapper)? Research during Phase 1 planning.
- Rate limiter fail-closed: Raise exception or return 503? Design during Phase 1.
- Paper trading schema: New tables or extend existing? Design during Phase 1.

---
*State initialized: 2026-02-04*
