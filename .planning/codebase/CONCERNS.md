# Codebase Concerns

**Analysis Date:** 2026-02-04

## Tech Debt

**Deprecated NPM Dependencies:**
- Issue: Frontend has 21 npm vulnerabilities (15 moderate, 6 high) and deprecated packages including `rollup-plugin-terser`, `source-map@0.8.0-beta.0`, `svgo@1.3.2`, `eslint@8.57.1`, Babel plugins, and Workbox modules
- Files: `frontend/package.json`
- Impact: Security vulnerabilities in production, build process fragility, dependency maintenance burden
- Fix approach: Run `npm audit fix`, upgrade deprecated packages to modern equivalents (e.g., `@rollup/plugin-terser`, modern ESLint v9+), test thoroughly after upgrades

**Fetch Interceptor Monkeypatching:**
- Issue: `AIChat.js` patches `window.fetch` globally at runtime to inject chat tone and alert context into requests
- Files: `frontend/src/pages/AIChat.js` (lines 57-127)
- Impact: Fragile, non-standard approach; breaks with native fetch API updates; makes debugging harder; side effects across entire app
- Fix approach: Replace with proper request middleware in axios interceptor or custom hook context; avoid global state pollution

**AI Provider Hardcoding:**
- Issue: AI model provider selection logic is spread across multiple files with fallback to OpenAI if env vars are invalid
- Files: `backend/api/ai.py` (lines 72-78), `backend/services/strategy_ai.py` (lines 28-33)
- Impact: Configuration validation happens at runtime; invalid provider configs silently degrade instead of failing fast
- Fix approach: Validate provider at startup in settings initialization; raise error instead of silent fallback

**Exception Swallowing:**
- Issue: Multiple places catch broad `Exception` and log warnings without re-raising, masking real problems
- Files: `backend/main.py` (line 53), `backend/services/strategy_ai.py` (lines 178-181, 234-236)
- Impact: Silent failures in error persistence, strategy recommendations, and promotion logic; hard to debug production issues
- Fix approach: Distinguish between recoverable errors (log and continue) and fatal errors (raise); use specific exception types

**Unvalidated Return None/Empty Patterns:**
- Issue: Functions return `None` or `[]` without clear contract or caller handling
- Files: `backend/db/database.py`, `backend/agents/sentiment_agent.py`, `backend/core/paper_trading.py`, `backend/api/ai.py`
- Impact: Callers must handle both valid results and empty/None returns; no schema validation; easy to introduce None-safety bugs
- Fix approach: Use Optional[] types consistently; validate at boundaries; consider raising exceptions for truly exceptional cases

## Database

**SQLite in Production Context:**
- Issue: Using SQLite as primary database for what appears to be a trading platform
- Files: `backend/db/database.py` (line 21), `.env`
- Impact: SQLite has limitations on concurrent writes, not ideal for high-frequency trading operations; single-file database vulnerable to data loss
- Fix approach: Document SQLite use cases clearly; plan migration path to PostgreSQL for production; ensure proper backups

**Missing Transaction Management:**
- Issue: Several database operations don't use explicit transactions for related updates
- Files: `backend/db/database.py`, `backend/core/paper_trading.py`
- Impact: Race conditions possible between related record updates (e.g., trade + position updates); data consistency not guaranteed under concurrent access
- Fix approach: Wrap related updates in transaction context; use pessimistic locking for critical sections

**Migration Versioning Gap:**
- Issue: Only 2 migration files exist for a mature schema; migrations appear incomplete
- Files: `backend/alembic/versions/0001_initial_schema.py` (13KB), `backend/alembic/versions/150f429d1db6_add_ai_provider_columns.py` (769B)
- Impact: Schema drift risk; missing documented history of column additions (AI provider columns added but not tracked clearly)
- Fix approach: Review recent code changes for schema modifications not captured in migrations; enforce migration requirement in CI/CD

## Security

**API Key Storage in Environment Variables:**
- Issue: Kraken API credentials stored in plain `.env` file
- Files: `backend/core/settings.py` (lines 69-70), `.env`
- Impact: If `.env` is accidentally committed or exposed, trading account is compromised
- Fix approach: Use secrets manager (AWS Secrets Manager, HashiCorp Vault); implement key rotation; audit .gitignore

**Missing CSRF Protection:**
- Issue: Forms and state-changing operations don't validate CSRF tokens
- Files: `backend/main.py` - no CSRF middleware registered
- Impact: Cross-site request forgery attacks possible; attacker can trigger trades from external site
- Fix approach: Implement FastAPI CsrfProtectMiddleware; require CSRF tokens in POST/PUT/DELETE requests

**localStorage for Auth Token (Deprecated):**
- Issue: Comments indicate "auth token interceptor" but actual code uses HttpOnly cookies
- Files: `frontend/src/services/api.js` (lines 33-48), `frontend/src/pages/AIChat.js` (lines 38-48)
- Impact: Inconsistent auth strategy; if code reverts to localStorage, creates XSS vulnerability
- Fix approach: Remove localStorage auth code completely; enforce HttpOnly cookie-only auth; document this choice

**WebSocket Connection Lacks Authentication:**
- Issue: WebSocket connections to Kraken feed don't validate client identity
- Files: `backend/services/kraken_ws.py` - public/unauthenticated feed
- Impact: Any client can connect to market data stream; monitor for DoS risk
- Fix approach: Add authentication to private WebSocket endpoints; rate limit public feeds

**SQL Injection Via ilike Patterns:**
- Issue: Search patterns built with string formatting before being passed to ilike
- Files: `backend/api/ai.py` (lines 234-242) - `f"%{search}%"` pattern
- Impact: User input goes through `ilike()` which should be parameterized; should verify SQLAlchemy handles properly
- Fix approach: Audit all ilike/filter patterns; ensure parameterization; add input validation tests

## Performance

**N+1 Queries in Chat History:**
- Issue: No eager loading of related records in chat history queries
- Files: `backend/api/ai.py` (lines 279-315)
- Impact: Fetching 25+ alerts/activities triggers separate queries for related data; slowdown with scale
- Fix approach: Use SQLAlchemy `joinedload()` for related models; profile query performance

**WebSocket Message Processing:**
- Issue: Each Kraken WebSocket message is processed in message loop with potential for backlogs
- Files: `backend/services/kraken_ws.py` (lines 243-270)
- Impact: If message processing is slow, queue builds up; high-frequency tickers could overflow
- Fix approach: Profile message processing time; consider separate queue for fast path items

**In-Memory Alert Cache Without Bounds:**
- Issue: Alert data structure grows with each alert but no eviction policy visible
- Files: `frontend/src/hooks/useAlerts.js` - `alertStore.alerts` array grows unbounded
- Impact: Memory leak in browser over long sessions; potential slowdown with hundreds of alerts
- Fix approach: Implement max size for in-memory alert cache; implement pagination properly; clean up old alerts

**Database Backup Overhead:**
- Issue: Database backup runs at startup with no concurrency controls
- Files: `backend/db/database.py` (backup functions)
- Impact: If database is large, backup at startup could block application initialization
- Fix approach: Move backups to background task; implement incremental backups; add backup duration timeout

## Error Handling & Reliability

**Missing Error Recovery in Kraken WS:**
- Issue: Reconnection uses fixed exponential backoff without jitter
- Files: `backend/services/kraken_ws.py` (line 232)
- Impact: All clients reconnect simultaneously after outage, causing thundering herd
- Fix approach: Add jitter to reconnect delays; implement exponential backoff with randomization

**Chat History Truncation Silent Failure:**
- Issue: If chat history query fails, endpoint returns partial response without indicating error
- Files: `backend/api/ai.py` (lines 262-320)
- Impact: Frontend may display incomplete chat history without user awareness
- Fix approach: Make query failures explicit in response; log query failures with context

**No Timeout on AI Model Calls:**
- Issue: OpenAI/Claude API calls don't have explicit timeout configuration
- Files: `backend/services/strategy_ai.py` (lines 222-236), `backend/api/ai.py` (lines 200+)
- Impact: Requests could hang indefinitely; resource exhaustion if many hanging requests pile up
- Fix approach: Add timeout parameter to all AI client calls; implement circuit breaker pattern

**Uncaught Errors in Async Tasks:**
- Issue: `asyncio.create_task()` calls without exception handlers
- Files: `backend/main.py` (line 69), `backend/services/kraken_ws.py` (lines 175, 178)
- Impact: Task failures are logged but don't propagate; can fail silently
- Fix approach: Wrap create_task with error callback; monitor task exceptions; implement task death detection

## Missing Validation

**Credential Edge Cases:**
- Issue: Password reset tokens and session tokens don't validate length or format on creation
- Files: `backend/db/models.py` (lines 45-58, 32-42)
- Impact: Tokens could be invalid or empty; validation only happens at validation time
- Fix approach: Add constraints in model; validate token format before storing

**Market Data Inputs:**
- Issue: Decimal values from Kraken stream converted without overflow checks
- Files: `backend/services/kraken_ws.py` (lines 35-60)
- Impact: Extreme price values could cause calculation errors; no bounds checking
- Fix approach: Add min/max validation; implement circuit breaker for anomalous prices

**JSON Configuration Fields:**
- Issue: JSON fields in models (`rules_json`, `ai_modifications_json`, `preferences_json`) stored without schema validation
- Files: `backend/db/models.py` (multiple JSON fields)
- Impact: Invalid JSON structure could break strategy execution; no schema enforcement
- Fix approach: Implement JSON schema validation before insert/update; document expected structures

## Testing Gaps

**No Tests for WebSocket Reconnection:**
- Issue: Critical reconnection logic in `kraken_ws.py` lacks automated tests
- Files: `backend/services/kraken_ws.py` (lines 213-241)
- Impact: Reconnection bugs could cause trading signal delays without detection
- Fix approach: Add unit tests for reconnect logic with mocked websockets; test exponential backoff

**Missing Integration Tests for AI Providers:**
- Issue: AI provider fallback logic tested manually if at all
- Files: `backend/api/ai.py`, `backend/services/strategy_ai.py`
- Impact: Provider switch bugs (e.g., invalid credentials) not caught until runtime
- Fix approach: Add integration tests with mocked AI providers; test fallback paths

**Frontend Auth Tests Incomplete:**
- Issue: Session timeout, MFA flows not tested in frontend
- Files: `frontend/src/` - no obvious test files for auth flows
- Impact: Auth vulnerabilities not caught until production
- Fix approach: Add test coverage for login, session timeout, MFA; test protected route access control

**No Load Testing:**
- Issue: High-frequency trading scenarios not tested
- Files: Entire backend
- Impact: Performance bottlenecks discovered in production under real trading load
- Fix approach: Implement load tests for WebSocket throughput; profile alert generation at scale

## Fragile Areas

**Kraken API Rate Limiting:**
- Files: `backend/services/kraken.py` (rate limiting queue)
- Why fragile: Rate limit handling is custom-built; Kraken API rate limit changes not automatically handled
- Safe modification: Change only via queuing mechanism; add integration tests before modifying
- Test coverage: Rate limit tests missing

**Paper Trading Execution:**
- Files: `backend/core/paper_trading.py`
- Why fragile: Paper and live trading paths not unified; execution logic duplicated
- Safe modification: Refactor to single execution path with paper trading flag
- Test coverage: Limited coverage of edge cases (gap fills, slippage calculations)

**Market Data Stream Synchronization:**
- Files: `backend/services/kraken_ws.py`, `backend/services/market_data.py`
- Why fragile: Two separate data sources (REST API and WebSocket) without conflict resolution
- Safe modification: Add explicit sync logic when switching sources; handle gaps
- Test coverage: No tests for REST/WebSocket data consistency

## Scaling Limits

**SQLite Concurrent Write Limit:**
- Current capacity: Single writer, multiple readers
- Limit: Breaks under concurrent trade execution
- Scaling path: Migrate to PostgreSQL with connection pooling; implement per-strategy sharding

**WebSocket Broadcast Limit:**
- Current capacity: All clients receive all updates (ticker, trades)
- Limit: Broadcast overhead grows with client count
- Scaling path: Implement per-client subscription filtering at broker level; use Redis pub/sub

**AI Provider Rate Limits:**
- Current capacity: No built-in rate limit handling for OpenAI/Claude
- Limit: API calls get rate limited without backoff
- Scaling path: Implement token bucket rate limiter; queue AI requests with priority

## Dependencies at Risk

**Anthropic SDK Version Constraint:**
- Risk: `anthropic>=0.15.0` is very loose; future major versions could break
- Impact: Breaking changes in Claude API handling
- Migration plan: Pin major version; maintain compatibility wrapper for version transitions

**Krakenex Library Maintenance:**
- Risk: Krakenex 2.2.1 may not track Kraken API updates quickly
- Impact: New Kraken features/changes not available; hidden API deprecations
- Migration plan: Monitor krakenex releases; have plan to switch to direct httpx calls if unmaintained

**Old Pydantic Validator Pattern:**
- Risk: Code uses `@validator` decorator (Pydantic v1 style) - may not work with v2
- Impact: Validation logic could silently fail in Pydantic v2
- Migration plan: Migrate all `@validator` to `@field_validator` for v2 compatibility

## Missing Critical Features

**Hot-Reload Configuration:**
- Problem: Settings changes require application restart
- Blocks: Cannot change API keys, notification settings without downtime
- Solution: Implement configuration change endpoint with safe reload; invalidate affected caches

**Audit Trail for Trades:**
- Problem: No immutable log of who initiated each trade (human vs AI)
- Blocks: Regulatory compliance, debugging trade issues, accountability
- Solution: Add audit log table; log every trade with user/agent ID and decision context

**Circuit Breaker for External APIs:**
- Problem: Cascade failures when Kraken or AI APIs are down
- Blocks: Can't degrade gracefully; affects all users
- Solution: Implement circuit breaker pattern; fallback to cached data; notify users of degradation

---

*Concerns audit: 2026-02-04*
