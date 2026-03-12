# Testing Patterns

**Analysis Date:** 2026-02-04

## Test Framework

**Backend:**
- **Runner:** pytest 7.4.4
- **Async Support:** pytest-asyncio 0.23.3
- **Config:** No explicit pytest.ini or pyproject.toml config found
- **Cache:** `.pytest_cache` directory present

**Frontend:**
- **Framework:** Testing libraries available (@testing-library/react, @testing-library/jest-dom)
- **Status:** No test files found in codebase yet

**Run Commands:**
```bash
# Backend - run all tests
pytest /home/packnation82/projects/CryptoTrader/backend/tests/

# Backend - specific test file
pytest /home/packnation82/projects/CryptoTrader/backend/tests/test_auth.py

# Backend - single test
pytest /home/packnation82/projects/CryptoTrader/backend/tests/test_auth.py::test_register_creates_user

# Frontend - not yet configured
npm test
```

## AI-Driven Authenticated Test Workflow (GSD)

Going forward, the AI model performs authenticated smoke tests using credentials from `.env`.

**Required env vars:**
- `AI_USERNAME`
- `AI_PASSWORD`

**Execution order:**
1. Start the full stack with `./init.sh` and wait for the success banner.
2. Run authenticated API checks with `.env` credentials.
3. Run targeted test suites (`pytest` and lint) for the changed scope.

**Reference commands:**
```bash
# Load env vars
set -a; source .env; set +a

# Login using AI credentials from .env
curl -sS -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  --data "{\"email\":\"$AI_USERNAME\",\"password\":\"$AI_PASSWORD\"}"

# Session validation (cookie-based example)
curl -sS -c /tmp/ct.cookies -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  --data "{\"email\":\"$AI_USERNAME\",\"password\":\"$AI_PASSWORD\"}" >/dev/null
curl -sS -b /tmp/ct.cookies http://127.0.0.1:8000/api/auth/session
```

**Policy notes:**
- Do not commit credential values; only reference variable names.
- Do not hardcode alternate test users when `.env` credentials are available.
- If public-domain checks fail but local checks pass, record the infrastructure blocker (DNS/tunnel/proxy) explicitly.

## Test File Organization

**Location:**
- Backend tests co-located in `/home/packnation82/projects/CryptoTrader/backend/tests/` directory
- Separate from source code

**Naming:**
- Pattern: `test_*.py` - e.g., `test_auth.py`, `test_kraken_service.py`, `test_market_api.py`
- One test file per domain/module

**Structure:**
```
backend/tests/
├── test_auth.py              # Authentication tests (25+ async test functions)
├── test_kraken_service.py    # Kraken API integration tests
├── test_market_api.py        # Market endpoints tests
└── verify_kraken.py          # Verification script (not a test)
```

## Test Structure

**Async Test Pattern:**
```python
import pytest

@pytest.mark.asyncio
async def test_register_creates_user(db_session):
    response = await _create_user(db_session)
    assert response.email == VALID_EMAIL

    user_record = db_session.query(User).filter(User.email == VALID_EMAIL).first()
    assert user_record is not None
    assert user_record.email == VALID_EMAIL
```

**Database Setup Pattern:**
```python
@pytest.fixture(autouse=True)
def db_session():
    """Fixture that creates and tears down test database for each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    password_reset_service.tokens.clear()
    email_service.sent_emails.clear()
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
```

**Setup in conftest.py Pattern:**
- Database URL configured via environment variable before imports
- Mock modules injected via `sys.modules` to handle version mismatches
- Database file cleanup in session-scoped fixture
- Path setup for imports: `sys.path.insert(0, str(ROOT_PATH))`

**Test Helpers:**
```python
async def _create_user(db, email: str = VALID_EMAIL, password: str = VALID_PASSWORD):
    """Helper to create test user."""
    return await register(RegisterRequest(email=email, password=password), db=db)

async def _authenticate(db, email: str = VALID_EMAIL, password: str = VALID_PASSWORD):
    """Helper to authenticate test user."""
    return await login(LoginRequest(email=email, password=password), response=Response(), db=db)
```

## Mocking

**Framework:** `unittest.mock` - `MagicMock`, `patch`, `AsyncMock`

**Patterns from test_auth.py:**
```python
from unittest.mock import MagicMock, patch, AsyncMock

# Mock entire modules before import
mock_settings_module = MagicMock()
mock_settings = MagicMock()
mock_settings.session_cookie_name = "cryptotrader_session"
sys.modules["core.settings"] = mock_settings_module

# Mock dependencies in venv
mock_websockets = MagicMock()
sys.modules["websockets"] = mock_websockets
sys.modules["pandas"] = MagicMock()
sys.modules["openai"] = MagicMock()
```

**What to Mock:**
- External dependencies (pandas, numpy, openai, anthropic, websockets)
- Configuration modules with pydantic version mismatches
- Third-party services before they're imported by main code

**What NOT to Mock:**
- Database models and operations - use real SQLite test database
- Core authentication logic - test the actual functions
- FastAPI request/response objects - construct test instances like `Response()`
- Custom WebSocket class - use `DummyWebSocket` test helper

**Test Helper Classes:**
```python
class DummyWebSocket:
    """Mock WebSocket for testing."""
    def __init__(self, cookies=None, headers=None, query_params=None):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.query_params = query_params or {}
```

## Fixtures and Factories

**Test Data Constants:**
```python
VALID_EMAIL = "tester@example.com"
VALID_PASSWORD = "Str0ngPass!"
```

**Database Fixtures:**
- `db_session`: Function-scoped, creates fresh database for each test
- Creates all tables from SQLAlchemy Base metadata
- Clears service state (password_reset_service.tokens, email_service.sent_emails)

**Session-Scoped Cleanup:**
```python
@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db_file():
    """Clean up test database file after all tests."""
    yield
    for candidate in (TEST_DB_PATH, TEST_DB_PATH.with_suffix(...), ...):
        if candidate.exists():
            candidate.unlink()
```

**Location:**
- Fixtures defined in `backend/tests/test_auth.py` and other test files
- No separate conftest.py file yet

## Coverage

**Requirements:** Not enforced

**Current Test Files:**
- `test_auth.py`: ~25+ async tests covering registration, login, password reset, MFA, sessions
- `test_kraken_service.py`: Kraken API integration tests
- `test_market_api.py`: Market endpoints tests

**Test Count by Module:**
- Authentication: 25+ test functions
- Market API: Several tests for market endpoints
- Kraken Service: Integration tests for Kraken exchange

## Test Types

**Unit Tests:**
- Scope: Individual API endpoints and services
- Approach: Test in isolation with mocked dependencies
- Example: `test_register_creates_user` tests registration without external calls

**Integration Tests:**
- Scope: Multi-step flows (registration → login → password reset)
- Approach: Use real database, mock only external services
- Example: `test_password_reset_flow` tests entire reset sequence

**E2E Tests:**
- Status: Not currently implemented
- Would test full user journeys from login to trading

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
async def test_duplicate_registration_fails(db_session):
    await _create_user(db_session)
    with pytest.raises(HTTPException) as exc:
        await _create_user(db_session)
    assert exc.value.status_code == 409
    assert exc.value.detail == "Email already registered"
```

**Database Query Testing:**
```python
async def test_logout_removes_session(db_session):
    await _create_user(db_session)
    await _authenticate(db_session)

    session_record = db_session.query(UserSession).filter(UserSession.user_id == 1).first()
    assert session_record is not None

    await logout(response=Response(), session=session_record, db=db_session)
    remaining = db_session.query(UserSession).filter(UserSession.user_id == 1).count()
    assert remaining == 0
```

**Environment Setup Pattern:**
- Tests set `DATABASE_URL` env var before any imports
- Uses SQLite test database isolated from main database
- Cleans up test database files (including WAL and SHM files)

## Assertion Patterns

**Standard pytest assertions used:**
- `assert value == expected` for equality
- `assert record is not None` for existence checks
- `assert record.field == value` for property checks
- `with pytest.raises(ExceptionType) as exc:` for exception testing
- `exc.value.status_code == code` for HTTP exception details

---

*Testing analysis: 2026-02-04*
