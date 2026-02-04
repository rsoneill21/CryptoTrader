# Testing Patterns

**Analysis Date:** 2026-02-04

## Test Framework

**Runner:**
- pytest 7.4.4
- Config file: None detected (uses default pytest behavior)
- pytest-asyncio 0.23.3 for async test support

**Assertion Library:**
- pytest's built-in assertions (no separate assertion library)

**Run Commands:**
```bash
pytest backend/tests/                    # Run all backend tests
pytest backend/tests/test_auth.py        # Run specific test file
pytest -v                                # Verbose output
pytest -s                                # Show print statements
pytest --tb=short                        # Shorter traceback
```

**Frontend Testing:**
- Testing libraries installed but no tests found in repository
- @testing-library/react, @testing-library/jest-dom available
- Not actively used in current codebase

## Test File Organization

**Location (Backend):**
- Tests located in `backend/tests/` directory
- Separate from source code (not co-located)
- Path setup in each test file:
  ```python
  ROOT_PATH = Path(__file__).resolve().parent.parent
  if str(ROOT_PATH) not in sys.path:
      sys.path.insert(0, str(ROOT_PATH))
  ```

**Naming:**
- Pattern: `test_*.py` (pytest default)
- Example files: `test_auth.py`, `test_kraken_service.py`, `test_market_api.py`

**Structure:**
```
backend/tests/
├── test_auth.py
├── test_kraken_service.py
├── test_market_api.py
└── verify_kraken.py (verification utility)
```

## Test Structure

**Suite Organization:**
Tests use pytest's standard approach with fixtures for setup/teardown.

```python
# From backend/tests/test_auth.py

@pytest.fixture(autouse=True)
def db_session():
    """Database fixture - creates fresh DB for each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    password_reset_service.tokens.clear()
    email_service.sent_emails.clear()
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
```

**Patterns:**

1. **Setup:** Fixtures create test database and clear service state
2. **Execution:** Async test functions using `@pytest.mark.asyncio`
3. **Assertion:** Simple `assert` statements on return values
4. **Teardown:** Automatic cleanup via fixture yield

Example test:
```python
@pytest.mark.asyncio
async def test_register_creates_user(db_session):
    response = await _create_user(db_session)
    assert response.email == VALID_EMAIL

    user_record = db_session.query(User).filter(User.email == VALID_EMAIL).first()
    assert user_record is not None
    assert user_record.email == VALID_EMAIL
```

## Mocking

**Framework:**
- unittest.mock (standard library)
- MagicMock, patch, AsyncMock for mocking

**Patterns:**

1. **Module Mocking (Environment Setup):**
```python
# From test_auth.py - mocking missing dependencies
mock_settings_module = MagicMock()
mock_settings = MagicMock()
mock_settings.session_cookie_name = "cryptotrader_session"
sys.modules["core.settings"] = mock_settings_module

sys.modules["pandas"] = MagicMock()
sys.modules["numpy"] = MagicMock()
sys.modules["ta"] = MagicMock()
```

2. **Function Mocking:**
```python
# From test_kraken_service.py - monkeypatch for dependency injection
@pytest.mark.asyncio
async def test_get_ticker_parses_data(monkeypatch):
    service = KrakenService()

    async def fake_query_public(method, params=None):
        assert method == "Ticker"
        return {"XXBTZUSD": {...}}

    monkeypatch.setattr(service, "_query_public", fake_query_public)
    ticker = await service.get_ticker("BTC/USD")
    assert ticker.symbol == "BTC/USD"
```

3. **Async Mock:**
```python
# From test_auth.py - mocking rate limiter
with patch("api.auth.check_rate_limit", new_callable=AsyncMock) as mock_check:
    mock_check.return_value = False

    with pytest.raises(HTTPException) as exc:
        await login(...)
    assert exc.value.status_code == 429
```

**What to Mock:**
- External API calls (Kraken, email service, password reset tokens)
- Database-dependent operations (via fixtures instead)
- Service dependencies (email, password reset)

**What NOT to Mock:**
- Database models and ORM operations (use test DB)
- Core authentication logic (test with real tokens)
- Pydantic validation (test with real models)

## Fixtures and Factories

**Test Data:**

1. **Constants (Top of File):**
```python
# From test_auth.py
VALID_EMAIL = "tester@example.com"
VALID_PASSWORD = "Str0ngPass!"

class DummyWebSocket:
    def __init__(self, cookies=None, headers=None, query_params=None):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.query_params = query_params or {}
```

2. **Helper Functions:**
```python
# From test_auth.py
async def _create_user(db, email: str = VALID_EMAIL, password: str = VALID_PASSWORD):
    return await register(RegisterRequest(email=email, password=password), db=db)

async def _authenticate(db, email: str = VALID_EMAIL, password: str = VALID_PASSWORD):
    return await login(LoginRequest(email=email, password=password), response=Response(), db=db)
```

**Location:**
- Helper functions defined at module level in test files
- Constants at top of test module

## Coverage

**Requirements:**
- Not enforced (no pytest-cov configuration detected)
- No coverage reports in repository

**View Coverage:**
```bash
pytest --cov=backend backend/tests/
pytest --cov=backend --cov-report=html backend/tests/
```

## Test Types

**Unit Tests:**
- Scope: Individual functions and classes
- Approach: Direct async function calls with mocked dependencies
- Example: `test_register_creates_user` - tests registration endpoint with in-memory database
- Coverage: API endpoints, business logic, authentication flows

**Integration Tests:**
- Scope: Multiple functions working together
- Approach: Full request/response cycle through API
- Example: `test_password_reset_flow` - tests multi-step password reset process
- Database: Real test SQLite database created per test
- Services: In-memory implementations (email service stores in `sent_emails` list)

**E2E Tests:**
- Framework: Not present in codebase
- Would need: Selenium, Playwright, or Cypress
- Frontend integration: No automated tests configured

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_login_returns_session_token(db_session):
    await _create_user(db_session)
    login_response = await _authenticate(db_session)
    assert login_response.token
    assert login_response.user_id > 0
    assert login_response.expires_at
```

**Error Testing:**
```python
@pytest.mark.asyncio
async def test_login_with_invalid_credentials(db_session):
    await _create_user(db_session)
    with pytest.raises(HTTPException):
        await login(LoginRequest(email=VALID_EMAIL, password="badPass1!"), response=Response(), db=db_session)

@pytest.mark.asyncio
async def test_login_rejects_nonexistent_email(db_session):
    with pytest.raises(HTTPException):
        await login(LoginRequest(email="nobody@example.com", password="irrelevant"), response=Response(), db=db_session)
```

**Database State Testing:**
```python
@pytest.mark.asyncio
async def test_logout_removes_session(db_session):
    await _create_user(db_session)
    await _authenticate(db_session)

    session_record = db_session.query(UserSession).filter(UserSession.user_id == 1).first()
    assert session_record is not None

    await logout(response=Response(), session=session_record, db=db_session)
    remaining = db_session.query(UserSession).filter(UserSession.user_id == 1).count()
    assert remaining == 0
```

**Multi-step Flow Testing:**
```python
@pytest.mark.asyncio
async def test_password_reset_flow(db_session):
    await _create_user(db_session, email="reset@example.com")
    user = db_session.query(User).filter(User.email == "reset@example.com").first()
    assert user is not None

    await request_password_reset(PasswordResetRequest(email=user.email), db=db_session)
    token_candidates = [
        token for token in password_reset_service.tokens.values()
        if token.user_id == user.id and not token.used
    ]
    assert token_candidates
    reset_token = token_candidates[0].token

    await confirm_password_reset(
        PasswordResetConfirmRequest(token=reset_token, new_password="NewPassw0rd!"),
        db=db_session,
    )

    login_response = await login(LoginRequest(email=user.email, password="NewPassw0rd!"), response=Response(), db=db_session)
    assert login_response.token
```

## Validation Testing

**Password Strength:**
```python
@pytest.mark.asyncio
async def test_register_rejects_short_password(db_session):
    with pytest.raises(HTTPException):
        await register(RegisterRequest(email="short@example.com", password="Ab1!"), db=db_session)

@pytest.mark.asyncio
async def test_register_rejects_password_without_uppercase(db_session):
    with pytest.raises(HTTPException):
        await register(RegisterRequest(email="lower@example.com", password="lowercase1!"), db=db_session)
```

## WebSocket Testing

```python
@pytest.mark.asyncio
async def test_websocket_auth_accepts_cookie_session(db_session):
    await _create_user(db_session)
    login_response = await _authenticate(db_session)

    ws = DummyWebSocket(cookies={mock_settings.session_cookie_name: login_response.token})
    session = await get_current_session_ws(ws, db_session)
    assert session.user_id == 1

@pytest.mark.asyncio
async def test_websocket_auth_rejects_missing_token(db_session):
    await _create_user(db_session)
    ws = DummyWebSocket()
    with pytest.raises(HTTPException) as exc:
        await get_current_session_ws(ws, db_session)
    assert exc.value.status_code == 401
```

## Test Database Management

**Initialization:**
```python
@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db_file():
    """Session-level cleanup of test database files."""
    yield
    for candidate in (
        TEST_DB_PATH,
        TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
        TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
    ):
        if candidate.exists():
            candidate.unlink()
```

**Reset Per Test:**
- Each test creates fresh database from schema
- All tables dropped and recreated
- Service state (tokens, emails) cleared
- Ensures test isolation

## Known Testing Gaps

**Frontend:**
- No component tests (testing libraries installed but unused)
- No integration tests for React components
- No E2E tests for user workflows

**Backend:**
- Limited endpoint tests (only auth endpoints tested)
- No tests for: market API, strategies, trades, AI endpoints
- No database schema migration tests
- No Kraken API integration tests (uses mocks)

---

*Testing analysis: 2026-02-04*
