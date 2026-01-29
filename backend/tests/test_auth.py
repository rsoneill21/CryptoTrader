import os
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

TEST_DB_PATH = Path("/tmp/cryptotrader_auth_test.db")
for candidate in (
    TEST_DB_PATH,
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
    TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
):
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

import pytest
from fastapi import HTTPException

from api.auth import (
    register,
    login,
    logout,
    get_session as session_info,
    request_password_reset,
    confirm_password_reset,
    RegisterRequest,
    LoginRequest,
    PasswordResetRequest,
    PasswordResetConfirmRequest,
)
from db.database import Base, engine, SessionLocal
from db.models import User, Session as UserSession
from services.password_reset import password_reset_service
from services.email import email_service

VALID_EMAIL = "tester@example.com"
VALID_PASSWORD = "Str0ngPass!"


@pytest.fixture(autouse=True)
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    password_reset_service.tokens.clear()
    email_service.sent_emails.clear()
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db_file():
    yield
    for candidate in (
        TEST_DB_PATH,
        TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-wal"),
        TEST_DB_PATH.with_suffix(TEST_DB_PATH.suffix + "-shm"),
    ):
        if candidate.exists():
            candidate.unlink()


async def _create_user(db, email: str = VALID_EMAIL, password: str = VALID_PASSWORD):
    return await register(RegisterRequest(email=email, password=password), db=db)


async def _authenticate(db, email: str = VALID_EMAIL, password: str = VALID_PASSWORD):
    return await login(LoginRequest(email=email, password=password), db=db)


@pytest.mark.asyncio
async def test_register_creates_user(db_session):
    response = await _create_user(db_session)
    assert response.email == VALID_EMAIL

    user_record = db_session.query(User).filter(User.email == VALID_EMAIL).first()
    assert user_record is not None
    assert user_record.email == VALID_EMAIL


@pytest.mark.asyncio
async def test_duplicate_registration_fails(db_session):
    await _create_user(db_session)
    with pytest.raises(HTTPException) as exc:
        await _create_user(db_session)
    assert exc.value.status_code == 409
    assert exc.value.detail == "Email already registered"


@pytest.mark.asyncio
async def test_login_returns_session_token(db_session):
    await _create_user(db_session)
    login_response = await _authenticate(db_session)
    assert login_response.token
    assert login_response.user_id > 0
    assert login_response.expires_at


@pytest.mark.asyncio
async def test_login_with_invalid_credentials(db_session):
    await _create_user(db_session)
    with pytest.raises(HTTPException):
        await login(LoginRequest(email=VALID_EMAIL, password="badPass1!"), db=db_session)


@pytest.mark.asyncio
async def test_session_endpoint_returns_user_info(db_session):
    await _create_user(db_session)
    await _authenticate(db_session)

    user_record = db_session.query(User).filter(User.email == VALID_EMAIL).first()
    assert user_record is not None

    session_payload = await session_info(user=user_record)
    assert session_payload.email == VALID_EMAIL
    assert session_payload.user_id == user_record.id


@pytest.mark.asyncio
async def test_logout_removes_session(db_session):
    await _create_user(db_session)
    await _authenticate(db_session)

    session_record = db_session.query(UserSession).filter(UserSession.user_id == 1).first()
    assert session_record is not None

    await logout(session=session_record, db=db_session)
    remaining = db_session.query(UserSession).filter(UserSession.user_id == 1).count()
    assert remaining == 0


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

    login_response = await login(LoginRequest(email=user.email, password="NewPassw0rd!"), db=db_session)
    assert login_response.token


@pytest.mark.asyncio
async def test_password_reset_confirm_rejects_invalid_token(db_session):
    with pytest.raises(HTTPException):
        await confirm_password_reset(
            PasswordResetConfirmRequest(token="invalid", new_password="NewPassw0rd!"),
            db=db_session,
        )


@pytest.mark.asyncio
async def test_password_reset_nonexistent_email_returns_success(db_session):
    response = await request_password_reset(
        PasswordResetRequest(email="ghost@example.com"),
        db=db_session,
    )
    assert "If an account" in response.message


@pytest.mark.asyncio
async def test_password_reset_rejects_weak_new_password(db_session):
    await _create_user(db_session, email="weakreset@example.com")
    user = db_session.query(User).filter(User.email == "weakreset@example.com").first()
    await request_password_reset(PasswordResetRequest(email=user.email), db=db_session)
    token = next(
        token.token for token in password_reset_service.tokens.values()
        if token.user_id == user.id and not token.used
    )
    with pytest.raises(HTTPException):
        await confirm_password_reset(
            PasswordResetConfirmRequest(token=token, new_password="weak"),
            db=db_session,
        )


@pytest.mark.asyncio
async def test_password_reset_invalidates_existing_sessions(db_session):
    await _create_user(db_session, email="sessionreset@example.com")
    user = db_session.query(User).filter(User.email == "sessionreset@example.com").first()
    assert user is not None

    await _authenticate(db_session, email=user.email)
    await _authenticate(db_session, email=user.email)
    assert db_session.query(UserSession).filter(UserSession.user_id == user.id).count() == 2

    await request_password_reset(PasswordResetRequest(email=user.email), db=db_session)
    token = next(
        token.token for token in password_reset_service.tokens.values()
        if token.user_id == user.id and not token.used
    )
    await confirm_password_reset(
        PasswordResetConfirmRequest(token=token, new_password="Another1!"),
        db=db_session,
    )

    assert db_session.query(UserSession).filter(UserSession.user_id == user.id).count() == 0


@pytest.mark.asyncio
async def test_register_rejects_short_password(db_session):
    with pytest.raises(HTTPException):
        await register(RegisterRequest(email="short@example.com", password="Ab1!"), db=db_session)


@pytest.mark.asyncio
async def test_register_rejects_password_without_uppercase(db_session):
    with pytest.raises(HTTPException):
        await register(RegisterRequest(email="lower@example.com", password="lowercase1!"), db=db_session)


@pytest.mark.asyncio
async def test_register_rejects_password_without_lowercase(db_session):
    with pytest.raises(HTTPException):
        await register(RegisterRequest(email="upper@example.com", password="UPPERCASE1!"), db=db_session)


@pytest.mark.asyncio
async def test_register_rejects_password_without_digit(db_session):
    with pytest.raises(HTTPException):
        await register(RegisterRequest(email="nodigit@example.com", password="NoDigits!@"), db=db_session)


@pytest.mark.asyncio
async def test_register_rejects_password_without_special_char(db_session):
    with pytest.raises(HTTPException):
        await register(RegisterRequest(email="nospecial@example.com", password="NoSpecial1a"), db=db_session)


@pytest.mark.asyncio
async def test_login_rejects_nonexistent_email(db_session):
    with pytest.raises(HTTPException):
        await login(LoginRequest(email="nobody@example.com", password="irrelevant"), db=db_session)


@pytest.mark.asyncio
async def test_multiple_sessions_allowed(db_session):
    await _create_user(db_session)
    token1 = (await _authenticate(db_session)).token
    token2 = (await _authenticate(db_session)).token
    assert token1 != token2
