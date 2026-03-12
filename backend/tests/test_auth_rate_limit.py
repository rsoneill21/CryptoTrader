"""Regression tests for auth rate limiter integration."""

import os
from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response

ROOT_PATH = Path(__file__).resolve().parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_auth_rate_limit_test.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB_PATH}")

# Define mock settings at module level
mock_settings = MagicMock()
mock_settings.session_cookie_name = "cryptotrader_session"
mock_settings.secure_cookies = False
mock_settings.session_cookie_same_site = "lax"
mock_settings.allow_email_enumeration = True

@pytest.fixture(autouse=True, scope="module")
def mock_dependencies():
    """Fixture to mock dependencies and restore them after tests."""
    mocks = {
        "core.settings": MagicMock(),
        "websockets": MagicMock(),
        "websockets.exceptions": MagicMock(),
        "pandas": MagicMock(),
        "numpy": MagicMock(),
        "ta": MagicMock(),
        "openai": MagicMock(),
        "anthropic": MagicMock(),
        "jose": MagicMock(),
        "passlib": MagicMock(),
        "passlib.context": MagicMock(),
    }
    
    mocks["core.settings"].get_app_settings.return_value = mock_settings
    
    original_modules = {}
    for name, m in mocks.items():
        if name in sys.modules:
            original_modules[name] = sys.modules[name]
        sys.modules[name] = m
        
    yield mocks
    
    for name in mocks:
        if name in original_modules:
            sys.modules[name] = original_modules[name]
        else:
            del sys.modules[name]

from api.auth import LoginRequest, login
from core.exceptions import RateLimitException, ServiceUnavailableException
from core.rate_limit import check_rate_limit


@pytest.mark.asyncio
async def test_login_succeeds_under_rate_limit():
    """Login should proceed when rate limit check passes."""

    user = MagicMock()
    user.id = 1
    user.email = "tester@example.com"
    user.password_hash = "hashed"
    user.mfa_enabled = False
    user.session_timeout_minutes = 30

    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = user
    db.execute.return_value = result
    db.add = MagicMock()
    db.commit = AsyncMock()

    response = Response()

    with patch("api.auth.check_rate_limit", new_callable=AsyncMock) as mock_rate_limit:
        mock_rate_limit.return_value = True
        with patch("api.auth.verify_password", return_value=True):
            expires_at = datetime.now(timezone.utc)
            with patch("api.auth.get_session_expiry", return_value=expires_at):
                with patch("api.auth.generate_session_token", return_value="session-token"):
                    login_response = await login(
                        LoginRequest(email=user.email, password="password123!"),
                        response=response,
                        db=db,
                    )

    assert login_response.token == "session-token"
    assert login_response.user_id == user.id
    assert "session-token" in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_login_blocked_when_rate_limit_exceeded():
    """Login should raise when the rate limiter denies the request."""

    db = AsyncMock()
    response = Response()

    with patch("api.auth.check_rate_limit", new_callable=AsyncMock) as mock_rate_limit:
        mock_rate_limit.side_effect = RateLimitException(retry_after=60)

        with pytest.raises(RateLimitException) as exc:
            await login(
                LoginRequest(email="tester@example.com", password="password123!"),
                response=response,
                db=db,
            )

    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_check_rate_limit_raises_on_exceeded():
    """check_rate_limit should raise RateLimitException when the limit is exceeded."""

    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 10  # Over limit
    mock_redis.expire.return_value = True

    with patch("core.rate_limit.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_get_redis.return_value = mock_redis

        with patch("core.rate_limit._using_fake_redis", False):
            with pytest.raises(RateLimitException):
                await check_rate_limit("rate_limit:test", 5, 60)


@pytest.mark.asyncio
async def test_check_rate_limit_passes_under_limit():
    """check_rate_limit should return successfully when under the configured limit."""

    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 3  # Under limit
    mock_redis.expire.return_value = True

    with patch("core.rate_limit.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_get_redis.return_value = mock_redis

        with patch("core.rate_limit._using_fake_redis", False):
            result = await check_rate_limit("rate_limit:test", 5, 60)
            assert result is True


@pytest.mark.asyncio
async def test_check_rate_limit_raises_service_unavailable_when_redis_down():
    """check_rate_limit should raise ServiceUnavailableException when Redis unavailable."""

    with patch("core.rate_limit.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_get_redis.return_value = None

        with patch("core.rate_limit._using_fake_redis", False):
            with pytest.raises(ServiceUnavailableException):
                await check_rate_limit("rate_limit:test", 5, 60)