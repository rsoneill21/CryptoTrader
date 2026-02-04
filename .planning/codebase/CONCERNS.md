# Codebase Concerns

**Analysis Date:** 2026-02-04

## Tech Debt

**NPM Dependency Vulnerabilities:**
- Issue: Frontend has 21 vulnerabilities reported (15 moderate, 6 high) with deprecated packages
- Files: `frontend/package.json`
- Impact: Security exposure in production; potential XSS or injection vulnerabilities; unmaintained dependencies may lack critical patches
- Deprecated packages: `rollup-plugin-terser`, `sourcemap-codec`, `stable`, `q`, Workbox modules, `whatwg-encoding`, `abab`, `domexception`, `w3c-hr-time`, `inflight`, `glob`, `rimraf`, `eslint@8.57.1`
- Fix approach: Run `npm audit` with `npm audit fix`, upgrade to modern equivalents (e.g., `@rollup/plugin-terser`, newer ESLint), test thoroughly for breaking changes

**Rate Limiting Fail-Open Security Risk:**
- Issue: Rate limiting gracefully degrades to allow all requests if Redis is unavailable
- Files: `backend/core/rate_limit.py` (lines 44-47, 61-64)
- Impact: Critical endpoints become unprotected against brute force/DoS when Redis connection fails (authentication, password reset). Malicious actors can exploit service outages to attack the system
- Current behavior: `if not r: return True` and `except Exception: return True` - fail-open pattern is intentional but dangerous
- Fix approach: Implement stricter failure modes: fail-closed for auth/sensitive endpoints, timeout detection with exponential backoff, health check monitoring, circuit breaker pattern. At minimum, differentiate between endpoint sensitivity

**Raw Exception Handling:**
- Issue: Bare `except Exception` blocks throughout codebase silently swallow errors without logging details
- Files: `backend/core/security.py` (lines 144, 178), `backend/agents/*`, `backend/core/rate_limit.py`, `backend/core/auth.py`
- Impact: Critical failures (auth, payment, trading) become invisible; difficult to debug production issues; silent failures mask security problems
- Examples: `compute_totp()` returns empty string on base32 decode failure (line 145) - invalid codes accepted
- Fix approach: Replace bare `except` with specific exceptions, always log with traceback, return structured error objects with detail codes

**Session Timeout Using UTC Without Timezone Awareness:**
- Issue: Session expiry comparison uses `datetime.utcnow()` without timezone info across the codebase
- Files: `backend/core/auth.py` (line 47), `backend/core/security.py` (line 103, 113), `backend/db/database.py` (line 156), `backend/api/auth.py`
- Impact: Potential timezone-related session validation bugs in environments with non-UTC clocks; inconsistent behavior across servers with different TZ settings
- Fix approach: Standardize on timezone-aware datetime: use `datetime.now(timezone.utc)` consistently, store with UTC timezone info in DB

**Unprotected WebSocket Authentication:**
- Issue: WebSocket fallback authentication accepts `token` query parameter without HTTPS enforcement
- Files: `backend/core/auth.py` (line 66) - `websocket.query_params.get("token")`
- Impact: Token can be logged by proxies, load balancers, and browser history. Violates secure token transmission requirements
- Fix approach: Remove query parameter token support, require tokens in Authorization header only, enforce WSS (secure WebSocket)

## Known Bugs

**TOTP Secret Validation Silent Failure:**
- Symptoms: Invalid TOTP secrets accepted without error during 2FA setup
- Files: `backend/core/security.py` (lines 138-145)
- Trigger: User with malformed `mfa_secret` can call `compute_totp()` which catches exception and returns empty string instead of error
- Workaround: Restart authentication flow (user will be locked out if secret is corrupted)
- Root cause: Defensive coding assumes all secrets are valid base32-encoded strings

**Email Normalization Listener Registration Race Condition:**
- Symptoms: Duplicate email registration succeeds when multiple registrations occur simultaneously
- Files: `backend/db/database.py` (lines 254-299)
- Trigger: Global `_USER_EMAIL_LISTENERS_REGISTERED` flag is not thread-safe; two threads can both see `False` and register listeners twice
- Workaround: Unlikely at typical scale due to SQLAlchemy's GIL protection, but not guaranteed
- Impact: Duplicate email validation bypassed; data integrity violated
- Fix approach: Replace global flag with `threading.Lock()` or use SQLAlchemy event decorators that handle re-registration

**OpenAI Compatibility Layer Memory Leak:**
- Symptoms: AsyncOpenAI client created per request never garbage collected properly
- Files: `backend/api/ai.py` (lines 38-59)
- Trigger: Each call to `_OpenAIChatCompletionCompat.acreate()` creates new client and calls `aclose()`, but exception paths may leak resources
- Impact: Long-running server accumulates open connections to OpenAI API; connection pool exhaustion possible under load
- Fix approach: Use context manager or try/finally, consider connection pooling

## Security Considerations

**API Token in LocalStorage:**
- Risk: Frontend stores auth token in localStorage despite using HttpOnly cookies (redundant and insecure)
- Files: `frontend/src/services/api.js` (lines 28-49)
- Current mitigation: Comment on line 77 indicates tokens now use HttpOnly cookies; localStorage token is unused/legacy
- Recommendations: Remove localStorage token storage completely (`getToken`, `setToken`, `removeToken` functions should be deleted), verify server sets `HttpOnly`, `Secure`, `SameSite` flags on all cookies

**Password Reset Token Exposure:**
- Risk: Reset tokens transmitted in query parameter within password reset flow
- Files: `backend/api/auth.py` (token passed to frontend), `frontend/src/pages/ForgotPassword.js`
- Current mitigation: Token should be short-lived and single-use
- Recommendations: Use POST-only reset endpoints with tokens in request body (not URL), implement token expiry (suggest 15-30 minutes), log failed attempts, rate-limit reset requests per email

**Kraken API Keys Stored Without Encryption:**
- Risk: API keys stored in database as plaintext if user provides them through settings
- Files: `backend/core/settings.py` (line 69-70) - `kraken_api_key`, `kraken_api_secret` loaded from env
- Current mitigation: Environment variables only (not persisted to DB in current code)
- Recommendations: If adding user-provided API key storage, implement encryption at rest using cryptography.Fernet, rotate keys regularly, audit key usage

**Email Enumeration Attack Possible:**
- Risk: Login endpoint can distinguish between registered and unregistered emails via timing/response
- Files: `backend/api/auth.py` (login endpoint)
- Current mitigation: `allow_email_enumeration` setting exists (line 50 in `settings.py`) but unclear if used
- Recommendations: Verify enumeration protection is enforced in login response (same response time/format for invalid email vs invalid password), use timing-safe comparisons

**CSRF Protection Missing:**
- Risk: No CSRF token validation on state-changing operations (POST/PUT/DELETE)
- Files: All API endpoints lack CSRF protection
- Current mitigation: HTTPOnly cookies + CORS origin checking provides some protection for browser-based attacks
- Recommendations: Implement CSRF tokens for non-API clients, ensure SameSite=Strict for sensitive operations

## Performance Bottlenecks

**Large File Size in Core Modules:**
- Problem: Several modules exceed 500 lines, making them difficult to test and reason about
- Files:
  - `backend/api/strategies.py` (930 lines) - strategy CRUD, GitHub import, AI recommendations
  - `backend/services/kraken.py` (877 lines) - exchange API wrapper
  - `backend/api/trades.py` (826 lines) - trade management, paper trading, analysis
  - `backend/api/ai.py` (745 lines) - chat endpoints, provider switching, streaming
- Impact: Long method chains, complex error handling, difficult debugging, high cognitive load for new developers
- Improvement path: Refactor into smaller modules (e.g., split `strategies.py` into `strategy_crud.py`, `strategy_github.py`, `strategy_ai.py`); extract common patterns into utilities

**Synchronous Database Queries in Async Endpoints:**
- Problem: FastAPI async routes still use SQLAlchemy's synchronous ORM extensively
- Files: Most API endpoints in `backend/api/*.py`
- Impact: Thread pool execution of sync queries blocks async event loop; poor concurrency under load
- Example: `backend/api/strategies.py` line 930 - `session.query(Strategy)` in async context
- Improvement path: Migrate to SQLAlchemy 2.0 async ORM (AsyncSession) or use `asyncio.to_thread()` explicitly

**No Pagination on List Endpoints:**
- Problem: Endpoints returning full lists without limit/offset
- Files: `backend/api/strategies.py`, `backend/api/trades.py`, `backend/api/market.py`
- Impact: Large datasets (100k+ records) loaded entirely into memory; slow response times; memory exhaustion
- Improvement path: Add pagination with default limit=50, max limit=1000, implement cursor-based pagination for better performance

**Missing Database Indexes:**
- Problem: No explicit indexes on frequently queried columns
- Files: `backend/db/models.py`
- Impact: Full table scans on user_id, strategy_id, timestamp queries; slow performance as data grows
- Improvement path: Add indexes on foreign keys, timestamps used in filtering, email fields

## Fragile Areas

**Email Listener System Complexity:**
- Files: `backend/db/database.py` (lines 254-299)
- Why fragile: Multiple SQLAlchemy event hooks (`before_insert`, `before_update`, `before_flush`) with interdependent logic; email normalization happens in multiple places; race conditions possible
- Safe modification: Add integration tests for concurrent registrations, use explicit locking, consider moving to database constraints instead
- Test coverage: No tests visible for the listener system; only functional testing of registration endpoint

**Paper Trading Engine State Management:**
- Files: `backend/core/paper_trading.py` (555 lines)
- Why fragile: In-memory state with no persistence; server restart loses all paper trading state; concurrent trade execution without explicit synchronization
- Safe modification: Add explicit locks around state mutations, implement state snapshots to disk, add state recovery on startup
- Test coverage: Gaps in concurrent execution scenarios, edge cases around order timing

**Kraken WebSocket Connection Management:**
- Files: `backend/services/kraken_ws.py` (672 lines)
- Why fragile: Long-running WebSocket connection requires careful error recovery; reconnection logic may hang; heartbeat mechanism could miss stale connections
- Safe modification: Add timeout detection, implement circuit breaker, log all connection state changes, add integration tests with mock Kraken server
- Test coverage: Manual testing only; no unit tests for disconnection/reconnection scenarios

**AI Model Provider Abstraction Leaky:**
- Files: `backend/api/ai.py` (745 lines), `backend/services/ai_models.py`
- Why fragile: Multiple providers (OpenAI, Claude, Ollama) with different response formats; fallback logic not enforced; streaming implementation splits across modules
- Safe modification: Implement strict provider interface contract, add provider-specific test fixtures, validate response format before returning
- Test coverage: Unit tests likely missing for error paths; no chaos testing for provider failures

## Scaling Limits

**Redis Dependency for Rate Limiting:**
- Current capacity: Single Redis instance (localhost:6379 by default)
- Limit: Fails open when Redis unavailable (security risk); no clustering/sentinel support
- Scaling path: Implement Redis Sentinel for HA, add Redis Cluster support for horizontal scaling, implement local fallback cache with eventual consistency

**SQLite Database Single Writer:**
- Current capacity: Works for small-medium deployments (< 10k users)
- Limit: SQLite has global write lock; concurrent writes block each other; cannot run multi-server deployment
- Scaling path: Migrate to PostgreSQL with proper connection pooling (pgBouncer), implement read replicas for analytics queries

**Paper Trading In-Memory State:**
- Current capacity: ~1000 concurrent paper trades before memory exhaustion
- Limit: No persistence layer; all state lost on restart; no multi-server support
- Scaling path: Move to Redis or PostgreSQL for state storage, implement distributed transaction handling

**WebSocket Connection Limit:**
- Current capacity: ~500 concurrent WebSocket connections per server (uvicorn/asyncio default)
- Limit: Single server bottleneck; no connection pooling or message broker
- Scaling path: Implement Redis pub/sub for multi-server broadcast, use connection pooling, add HAProxy/Nginx load balancing with sticky sessions

## Dependencies at Risk

**OpenAI API Client (openai >= 1.9.0):**
- Risk: Frequent breaking changes in OpenAI SDK; multiple major versions in use across projects
- Impact: Incompatible when upgrading; chat completion endpoints change between versions
- Migration plan: Pin to 1.x, migrate to stable OpenAI v1 API when released; implement provider abstraction layer to allow drop-in replacements

**Anthropic SDK (anthropic >= 0.15.0):**
- Risk: Young library with API stability not guaranteed; currently at 0.15 (not 1.0)
- Impact: Behavior changes possible with minor version bumps
- Migration plan: Pin to specific version, monitor release notes, add integration tests for Anthropic responses

**Technical Analysis Library (ta >= 0.11.0):**
- Risk: Unmaintained or slow-moving library; indicators may have bugs
- Impact: Strategy results incorrect; trading decisions based on wrong signal values
- Migration plan: Consider TA-Lib or pandas_ta (more maintained), validate indicator outputs against market data

**Krakenex (krakenex >= 2.2.1):**
- Risk: Kraken may change API without notice; third-party wrapper could lag behind
- Impact: Trading endpoints may break; balance queries may return wrong format
- Migration plan: Monitor Kraken API changelog, add health checks for API compatibility, consider maintaining fork if updates lag

## Missing Critical Features

**Audit Logging:**
- Problem: No audit trail for sensitive operations (trades, strategy changes, account settings)
- Blocks: Regulatory compliance (may be required for financial instruments), forensic analysis of security incidents
- Example: No log of who deleted a strategy and when; no record of settings changes

**Rate Limiting per Endpoint:**
- Problem: Global Redis rate limiter treats all endpoints equally
- Blocks: Cannot implement stricter limits on auth (prevent brute force), login (prevent account enumeration), password reset (prevent email scraping)
- Current: `backend/core/rate_limit.py` applies single rule to all paths

**Distributed Tracing:**
- Problem: No request tracing across services; difficult to debug slow trades or AI decisions
- Blocks: Performance optimization of complex workflows; root cause analysis for failures
- Current: Logging is local per module with no correlation IDs

## Test Coverage Gaps

**Authentication Edge Cases:**
- What's not tested: Session expiry near boundary times, timezone conversion bugs, concurrent login/logout, MFA disabled/enabled transitions, password reset token reuse
- Files: `backend/api/auth.py` (455 lines), `backend/core/auth.py`, `backend/core/security.py`
- Risk: Auth bypass possible; data leakage on failed authentication; session confusion
- Priority: High

**Kraken API Error Handling:**
- What's not tested: Network timeouts, rate limit responses from Kraken, invalid order responses, WebSocket disconnection during trade
- Files: `backend/services/kraken.py` (877 lines), `backend/services/kraken_ws.py` (672 lines)
- Risk: Orders placed twice, trades never confirmed, account state desynchronized with Kraken
- Priority: High

**Concurrent Trade Execution:**
- What's not tested: Multiple trades triggered simultaneously for same symbol, paper trading + live trading mixed, race conditions in position calculations
- Files: `backend/core/paper_trading.py` (555 lines), `backend/agents/trade_executor.py`
- Risk: Margin calls missed, overlapping orders, incorrect P&L calculations
- Priority: High

**AI Model Failover:**
- What's not tested: OpenAI API unavailable, Claude timeout, Ollama model missing, streaming response truncation, token limit exceeded
- Files: `backend/api/ai.py` (745 lines), `backend/services/ai_models.py` (433 lines)
- Risk: Chat becomes unusable, strategy recommendations incorrect, incomplete data persisted
- Priority: Medium

**Frontend API Error Handling:**
- What's not tested: 5xx errors, network timeout recovery, retry behavior on 429, session expiry during async operation
- Files: `frontend/src/services/api.js`
- Risk: Silent failures, stuck loading states, confusing error messages to user
- Priority: Medium

---

*Concerns audit: 2026-02-04*
