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
**Plan:** 01-11 completed (11 of 15 in phase)
**Status:** In progress (gap-closure follow-ups)
**Last activity:** 2026-02-05 - Completed 01-11-PLAN.md
**Progress:** ███████░░░ 73% (22/30 plans complete; 11/15 in current phase)

**What's happening:**
- Completed 01-01: Async database session factory
- Completed 01-02: Structured exceptions & fail-closed rate limiting
- Completed 01-03: Paper trading state persistence
- Completed 01-04: Cursor-based pagination for alerts
- Completed 01-05: Backend import path fixes and pybreaker dependency
- Completed 01-06: Wire paper trading engine hooks to FastAPI lifespan
- Completed 01-07: AsyncSession migration for alerts, market, strategies, and risk APIs
- Completed 01-08: Shared pagination helper plus cursor-based strategies & trades listings
- Completed 01-09: Structured exception handling and exc_info logging across backend APIs
- Completed 01-10: Trade creation endpoints reload orders before serialization (fixes POST /api/trades 500s)
- Completed 01-11: Paper trading session reset/archive endpoints exposed via FastAPI

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
- Rate limiter fails open when Redis down
- Dashboard shows placeholder data
- AI chat doesn't reference trading state

**Fixed in 01-01:**
- ✓ Trades API endpoints use AsyncSession (non-blocking database queries)
- ✓ Async engine and session factory available for all async routes
- ✓ Relationship eager loading with selectinload for async context

**Fixed in 01-03:**
- ✓ Paper trading state persists to database (positions, cash, P&L, price history)
- ✓ Session survives backend restarts with complete state restoration
- ✓ Session archival provides audit trail for reset operations

**Fixed in 01-04:**
- ✓ Alerts API uses cursor-based pagination for efficient browsing
- ✓ AsyncSession for alerts endpoints (non-blocking queries)
- ✓ Relationship eager loading with selectinload for async context

**Fixed in 01-04:**
- ✓ Alerts list uses cursor-based pagination (stable results during concurrent inserts)
- ✓ Cursor tokens encode timestamp+id for deterministic ordering
- ✓ Alerts endpoint migrated to AsyncSession

**Fixed in 01-05:**
- ✓ All import paths corrected (from backend.X → from X)
- ✓ pybreaker dependency installed for circuit breaker
- ✓ Backend server starts without ModuleNotFoundError
- ✓ API endpoints respond to HTTP requests

**Fixed in 01-07:**
- ✓ Alerts response models updated to ConfigDict to align with AsyncSession serialization
- ✓ Market endpoints removed their final synchronous Session dependency
- ✓ Strategy CRUD and simulation routes now await AsyncSession commits with rollback handling
- ✓ Risk settings helper and endpoints run entirely on AsyncSession/select queries

**Fixed in 01-08:**
- ✓ Extracted cursor encode/decode helpers plus `apply_cursor_pagination` into `backend/core/pagination.py`
- ✓ Strategies list endpoint now exposes `StrategyListResponse` with cursor + limit data
- ✓ Trades API gains a paginated history endpoint ordered by `entry_time` and `id`

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
| AsyncSession for trades API | 2026-02-05 | Use AsyncSession instead of asyncio.to_thread wrapper - native async provides better performance and follows SQLAlchemy 2.0 patterns | All new endpoints must use async_sessionmaker pattern |
| Dual session factories (sync + async) | 2026-02-05 | Keep sync SessionLocal for legacy utilities (logging, backups) during migration period | Allows gradual migration without breaking existing code |
| aiosqlite for development | 2026-02-05 | Thread-pool async bridge sufficient for dev/testing; production will use asyncpg | Development workflow unaffected, production deployment needs asyncpg setup |
| Complete session snapshot for persistence | 2026-02-05 | Store all state (positions, cash, P&L, price history) as JSON for atomic restore | Simpler than incremental updates, ensures consistency on recovery |
| Persist after each trade | 2026-02-05 | Capture every trade immediately via persist hook in execute_signal | Minimal data loss if crash occurs, worth the write overhead for paper trading |
| Session archival instead of deletion | 2026-02-05 | Keep historical sessions for audit trail and performance comparison | Enables "reset to fresh" while preserving past session data |
| Cursor-based pagination for lists | 2026-02-05 | Cursor pagination with timestamp+id composite key ensures stable results when alerts inserted between pages; avoids offset drift | All list endpoints should use cursor pattern for consistency |
| Limit+1 fetch strategy | 2026-02-05 | Fetch limit+1 rows to detect has_more flag; eliminates expensive COUNT(*) queries on large tables | Better performance for pagination, no total count needed |
| Relative imports from backend/ | 2026-02-05 | Use 'from core.X', 'from api.X' pattern when running from backend/ directory; no backend. prefix | All backend code uses consistent import pattern, eliminates ModuleNotFoundError |
| pybreaker for circuit breakers | 2026-02-05 | Install pybreaker>=1.0.0 for CircuitBreaker pattern in rate limiter | Enables fail-closed behavior when Redis unavailable |
| Entry_time anchors trade pagination | 2026-02-05 | Keeps cursor ordering tied to real execution timestamp without new schema | Frontend + agents can consume deterministic trade history tokens |
| DatabaseException for API SQL errors | 2026-02-05 | Encapsulate SQLAlchemyError details without leaking raw traces | Clients receive consistent structured error payloads across backend APIs |
| ServiceUnavailable for GitHub imports | 2026-02-05 | Surface upstream dependency failures with safe messaging | Makes strategy import outages observable without exposing stack traces |
| Paper trading reset requires confirmation with archival option | 2026-02-05 | Prevents accidental destruction of active sessions when hit via API | Maintenance endpoints stay safe for UI/agent callers |

### Active Todos

- [x] ~~Create Phase 1 execution plans (infrastructure fixes)~~ - Completed: 01-01 through 01-04 created
- [x] ~~Execute 01-01: Async DB session factory~~ - Completed: AsyncSession with aiosqlite
- [x] ~~Execute 01-03: Paper trading state persistence~~ - Completed: State persists to DB with archival
- [x] ~~Execute 01-04: Pagination (cursor-based for alerts)~~ - Completed: cursor pagination with AsyncSession
- [x] ~~Execute 01-05: Backend import path fixes~~ - Completed: Fixed all backend.X imports, added pybreaker
- [x] ~~Migrate remaining API endpoints to AsyncSession (market, strategies, alerts, risk)~~ - Completed: 01-07 converted all remaining routes
- [ ] Execute 01-02: Rate limiter fail-closed with circuit breaker (optional - 01-05 was gap closure for UAT blocker)
- [ ] Migrate other list endpoints to cursor pagination (remaining: decisions + future dashboards; strategies/trades done in 01-08)
- [ ] Frontend adaptation: use cursor tokens instead of page numbers for alerts
- [ ] Add composite index on alerts (created_at, id) for pagination performance
- [x] Wire paper trading engine lifecycle hooks into FastAPI startup/shutdown
- [x] ~~Install pybreaker in requirements.txt~~ - Completed in 01-05
- [ ] Install aiosqlite in production requirements.txt
- [ ] Document asyncpg migration for production PostgreSQL

### Blockers

None currently.

### Recent Changes

**2026-02-05 (latest - 01-11):**
- Completed 01-11: Paper trading reset/archive APIs exposed to FastAPI callers
- Reset endpoint enforces confirmation + optional archival; archive endpoint returns timestamped confirmation payload
- Duration: ~2 minutes (2 tasks, 2 commits)

**2026-02-05 (01-10):**
- Completed 01-10: Trade creation endpoints reload orders with selectinload before serialization
- Reloading ensures POST /api/trades and /api/trades/system return orders arrays without DetachedInstanceError
- Duration: <1 minute (1 task, 1 commit)

**2026-02-05 (01-09):**
- Completed 01-09: Structured exception handling across alerts, market, strategies, risk, AI chat, and export endpoints
- Added DatabaseException/ServiceUnavailableException responses plus `exc_info=True` logging for every failure path
- Duration: 5 minutes (3 tasks, 3 commits)

**2026-02-05 (latest - 01-08):**
- Completed 01-08: Shared pagination helper plus cursor-based strategies/trades listings
- Extracted encode/decode helpers + `apply_cursor_pagination` into `backend/core/pagination.py`
- Strategies endpoint now emits `StrategyListResponse` with `next_cursor` and `has_more`
- Trades API gained paginated history feed ordered by entry_time/id
- Duration: 4 minutes (3 tasks, 3 commits)

**2026-02-05 (01-07):**
- Completed 01-07: Async API migration for alerts, market, strategies, and risk routes
- Removed lingering synchronous Session imports and standardized on `get_async_db`
- Added rollback-aware error handling for strategy simulation logging and AsyncSession helper for risk settings
- Refreshed alert response models to use ConfigDict for Pydantic v2 compatibility
- Duration: ~5 minutes (4 tasks, 4 commits)

**2026-02-05 (01-06):**
- Completed 01-06: Wire paper trading engine hooks to FastAPI lifespan
- Imported initialize_paper_trading_engine and shutdown_paper_trading_engine
- Added await calls to lifespan startup and shutdown
- Ensures paper trading state is restored on boot and saved on exit
- Duration: 2 minutes (1 task, 1 commit)

**2026-02-05 (01-05):**
- Completed 01-05: Backend import path fixes and pybreaker dependency
- Fixed all 38 incorrect 'from backend.X' imports to relative paths
- Installed pybreaker>=1.0.0 for circuit breaker support
- Fixed CircuitBreaker parameter: timeout_duration → reset_timeout
- Added missing get_db/Session imports to alerts.py
- Backend server now starts without ModuleNotFoundError
- API endpoints respond correctly to HTTP requests
- Duration: ~5 minutes (3 tasks, 3 commits)

**2026-02-05 (earlier):**
- Completed 01-03: Paper trading state persistence
- Added PaperTradingState model with session_id, state_json, is_active, timestamps
- Created PaperTradingStateService with async load/save/archive methods
- Wired PaperTradingEngine with load_state_from_db, persist_state, archive_current_session, reset_to_clean_state
- Persist after each trade execution and periodically during price updates
- Session archival provides audit trail for performance comparison
- Duration: ~20 minutes (2 tasks, 2 commits)

**2026-02-05 (mid):**
- Completed 01-04: Cursor-based pagination for alerts
- Added encode_cursor/decode_cursor helpers (base64 timestamp|id)
- Converted list_alerts to AsyncSession with cursor navigation
- Replaced offset pagination with cursor tokens (next_cursor/prev_cursor)
- Preserved all filters (severity, status, type, search, since, until)
- Duration: ~2 minutes (2 tasks, 2 commits)

**2026-02-05 (earlier):**
- Completed 01-01: Async database session factory
- Created AsyncEngine and AsyncSessionLocal with aiosqlite driver
- Converted trades API (11 endpoints) to use AsyncSession
- Added get_async_db dependency for FastAPI async routes
- Installed aiosqlite dependency (Rule 3 - blocking fix)
- Converted fetch_decisions_for_trade helper to async (Rule 3 - blocking fix)
- Duration: ~5 minutes (2 tasks, 2 commits)

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
3. ~~**State persistence bugs:** Paper trading state loss invalidates all performance metrics and risks duplicate positions in live trading.~~ - MITIGATED in 01-03 (sessions persist and restore)

**Known tech debt (from PROJECT.md):**
- ~~Sync DB queries in trades API (INFRA-03)~~ - FIXED in 01-01 (AsyncSession for all trades endpoints)
- ~~Paper trading state not persisted (INFRA-01)~~ - FIXED in 01-03 (State persists to DB with archival)
- ~~No pagination (INFRA-06)~~ - PARTIALLY FIXED in 01-04 (alerts have cursor pagination; other endpoints pending)
- Rate limiting fails open (INFRA-02) - PLANNED (01-02)
- Bare exception handling (INFRA-04) - PLANNED (01-02 or separate plan)
- ~~Sync DB in some endpoints (create_alert, get_alert, update_alert)~~ - FIXED in 01-07 (alerts/market/strategies/risk now async)
- Partial fills not handled (POS-05)
- Slippage/fees not modeled (SAFE-03)
- Stop-loss not enforced (RISK-02)

## Session Continuity

**Last session:** 2026-02-05 16:42-16:44 UTC
**Stopped at:** Completed 01-11-PLAN.md (paper trading session reset/archive APIs)
**Resume file:** None

**For next session:**
1. Queue up 01-12-PLAN.md (cursor DESC fix) or revisit optional 01-02 if needed
2. Confirm transition plan for Phase 2 (autonomous agents) using new structured error foundation
3. Carry forward exc_info logging requirements for every new backend endpoint

**Context to carry forward:**
- **Import pattern:** Use 'from core.X', 'from api.X', 'from agents.X', 'from services.X' (no backend. prefix)
- **Dependencies:** pybreaker>=1.0.0 installed for circuit breaker support
- AsyncSession pattern established - use `get_async_db` dependency for all new async routes
- All database operations in async endpoints must be awaited
- Alerts, market, strategies, and risk APIs now exclusively rely on AsyncSession dependencies
- Use `selectinload` for eager loading relationships in async context
- Cursor pagination pattern established - use encode_cursor/decode_cursor for list endpoints
- Shared helper `backend/core/pagination.py` exposes encode/decode/apply_cursor_pagination for reuse
- Fetch limit+1 rows to detect has_more flag without COUNT(*) query
- Order by composite key (timestamp DESC, id DESC) for deterministic pagination
- Paper trading state persists automatically - sessions survive restart
- PaperTradingEngine has load_state_from_db, persist_state, archive_current_session, reset_to_clean_state
- State persists after each trade execution and periodically during price updates
- initialize_paper_trading_engine/shutdown_paper_trading_engine hooks need wiring to FastAPI lifecycle
- aiosqlite installed for development; production needs asyncpg
- Sync SessionLocal still available for legacy utilities (logging, backups)
- All API endpoints now log errors with `exc_info=True` and should raise DatabaseException/ServiceUnavailableException for structured responses

**Questions resolved:**
- ~~Async DB migration: AsyncSession (big change) or asyncio.to_thread (wrapper)?~~ - COMPLETE: AsyncSession with aiosqlite (01-01)
- ~~Pagination style: cursor vs offset?~~ - COMPLETE: Cursor-based with timestamp+id composite key (01-04)
- ~~Cursor format: opaque token vs exposed fields?~~ - COMPLETE: Base64-encoded timestamp|id for opacity (01-04)
- ~~Paper trading schema: New tables or extend existing?~~ - COMPLETE: New paper_trading_states table with JSON state column (01-03)
- ~~State serialization: incremental vs snapshot?~~ - COMPLETE: Complete snapshot for atomic restore (01-03)
- ~~Persistence timing: real-time vs periodic?~~ - COMPLETE: After each trade + periodic throttling on price updates (01-03)
- Rate limiter fail-closed: Raise exception or return 503? - DEFERRED to 01-02

---
*State initialized: 2026-02-04*
