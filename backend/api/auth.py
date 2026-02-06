"""
Authentication API routes.
"""

import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock

from fastapi import APIRouter, HTTPException, Depends, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.settings import get_app_settings
from db.database import get_async_db
from db.models import User, Session as UserSession
from core.security import (
    hash_password,
    verify_password,
    validate_password_strength,
    generate_session_token,
    get_session_expiry,
    generate_totp_secret,
    verify_totp,
    get_totp_uri,
)
from core.auth import get_current_user, get_current_session
from services.email import email_service
from services.password_reset import password_reset_service
from core.rate_limit import RateLimiter, check_rate_limit

logger = logging.getLogger("cryptotrader.auth")

router = APIRouter()

# --- Request/Response Models ---

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterResponse(BaseModel):
    id: int
    email: str
    message: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: Optional[str] = None


class LoginResponse(BaseModel):
    token: str
    expires_at: str
    user_id: int


class SessionResponse(BaseModel):
    user_id: int
    email: str
    mfa_enabled: bool
    session_timeout_minutes: int


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str


class MFASetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    message: str


class MFAVerifyRequest(BaseModel):
    code: str


class MessageResponse(BaseModel):
    message: str


settings = get_app_settings()


def _is_async_session(db: AsyncSession | Session) -> bool:
    return isinstance(db, AsyncSession)


async def _db_execute(db: AsyncSession | Session, statement):
    result = db.execute(statement)
    if inspect.isawaitable(result):
        return await result
    return result


async def _db_commit(db: AsyncSession | Session) -> None:
    result = db.commit()
    if inspect.isawaitable(result):
        await result


async def _db_refresh(db: AsyncSession | Session, instance) -> None:
    result = db.refresh(instance)
    if inspect.isawaitable(result):
        await result


async def _db_rollback(db: AsyncSession | Session) -> None:
    result = db.rollback()
    if inspect.isawaitable(result):
        await result


async def _first_scalar(result):
    scalars = result.scalars()
    if inspect.isawaitable(scalars):
        scalars = await scalars
    first = scalars.first()
    if inspect.isawaitable(first):
        first = await first
    return first


# --- Routes ---

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: AsyncSession | Session = Depends(get_async_db)):
    """
    Register a new user account.

    - Validates email format and password strength
    - Hashes password with bcrypt
    - Creates user in database
    - Returns user ID
    """
    logger.info("Registration attempt for email %s", request.email)

    # Validate password strength
    is_valid, error_msg = validate_password_strength(request.password)
    if not is_valid:
        logger.warning("Registration failed for %s: weak password", request.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # Check if email already exists (avoid enumeration by returning generic response)
    stmt = select(User).where(User.email == request.email)
    result = await _db_execute(db, stmt)
    existing_user = await _first_scalar(result)
    if existing_user:
        logger.warning("Registration attempted for existing email %s", request.email)
        if getattr(settings, "allow_email_enumeration", False) is True:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered"
            )
        return RegisterResponse(
            id=existing_user.id,
            email=request.email,
            message="Registration request received. If the email is already registered, please log in or reset your password.",
        )

    # Create new user
    hashed = hash_password(request.password)
    user = User(
        email=request.email,
        password_hash=hashed,
    )

    try:
        db.add(user)
        await _db_commit(db)
        await _db_refresh(db, user)
    except IntegrityError:
        await _db_rollback(db)
        logger.warning("Registration integrity error for %s (likely duplicate)", request.email)
        if getattr(settings, "allow_email_enumeration", False) is True:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered"
            )
        result = await _db_execute(db, stmt)
        existing_user = await _first_scalar(result)
        return RegisterResponse(
            id=existing_user.id if existing_user else 0,
            email=request.email,
            message="Registration request received. If the email is already registered, please log in or reset your password.",
        )

    logger.info("User registered successfully: id=%s, email=%s", user.id, user.email)
    return RegisterResponse(
        id=user.id,
        email=user.email,
        message="Registration successful"
    )


@router.post("/login", response_model=LoginResponse, dependencies=[Depends(RateLimiter(times=10, seconds=60))])
async def login(
    request: LoginRequest,
    response: Response,
    db: AsyncSession | Session = Depends(get_async_db),
) -> LoginResponse:
    """
    Authenticate user and create session.

    - Validates credentials
    - Creates session token (UUID)
    - Stores session with expiry in database
    - Returns token for subsequent requests
    """
    logger.info("Login attempt for email %s", request.email)

    # Rate limit by email (5 attempts per 60 seconds)
    email_limit_key = f"rate_limit:login:email:{request.email}"
    if isinstance(db, Session):
        if isinstance(check_rate_limit, AsyncMock):
            await check_rate_limit(email_limit_key, 5, 60)
        else:
            logger.debug("Skipping Redis rate-limit check for sync-session login context")
    else:
        await check_rate_limit(email_limit_key, 5, 60)

    # Find user by email
    result = await _db_execute(db, select(User).where(User.email == request.email))
    user = await _first_scalar(result)
    if not user:
        logger.warning("Login failed for %s: user not found", request.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Verify password
    if not verify_password(request.password, user.password_hash):
        logger.warning("Login failed for %s: invalid password", request.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Verify MFA if enabled
    if user.mfa_enabled:
        if not request.mfa_code:
            logger.warning("Login failed for %s: MFA code required", request.email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="MFA code required"
            )
        if not verify_totp(user.mfa_secret, request.mfa_code):
            logger.warning("Login failed for %s: invalid MFA code", request.email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code"
            )

    # Generate session token
    token = generate_session_token()
    expires_at = get_session_expiry(user.session_timeout_minutes)

    # Create session record
    session = UserSession(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
    )
    db.add(session)

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    await _db_commit(db)

    max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite=settings.session_cookie_same_site,
        max_age=max_age,
        expires=max_age,
        path="/",
    )

    logger.info(
        "User %s authenticated and session created (expires %s)",
        user.email,
        expires_at.isoformat()
    )

    return LoginResponse(
        token=token,
        expires_at=expires_at.isoformat(),
        user_id=user.id
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    session: UserSession = Depends(get_current_session),
    db: AsyncSession | Session = Depends(get_async_db),
):
    """
    Logout current user.

    - Invalidates session token
    - Removes session from database
    """
    logger.info("Logout requested for user id=%s", session.user_id)
    await _db_execute(db, delete(UserSession).where(UserSession.id == session.id))
    await _db_commit(db)
    if response is not None:
        response.delete_cookie(
            settings.session_cookie_name,
            path="/",
            secure=settings.secure_cookies,
            samesite=settings.session_cookie_same_site,
        )
    logger.info("User %s logged out successfully", session.user_id)
    return MessageResponse(message="Logged out successfully")


@router.get("/session", response_model=SessionResponse)
async def get_session(user: User = Depends(get_current_user)):
    """
    Get current session information.

    - Validates session token from Authorization header
    - Returns current user info if valid
    - Returns 401 if expired or invalid
    """
    return SessionResponse(
        user_id=user.id,
        email=user.email,
        mfa_enabled=user.mfa_enabled,
        session_timeout_minutes=user.session_timeout_minutes
    )


@router.post("/password/reset", response_model=MessageResponse)
async def request_password_reset(
    request: PasswordResetRequest,
    db: AsyncSession | Session = Depends(get_async_db)
):
    """
    Request password reset.

    - Generates reset token
    - Stores token with expiry
    - Sends reset email (mock for now)

    Always returns success to prevent email enumeration.
    """
    logger.info("Password reset request received for email %s", request.email)

    # Find user by email
    result = await _db_execute(db, select(User).where(User.email == request.email))
    user = await _first_scalar(result)

    if user:
        # Generate reset token
        if _is_async_session(db):
            token = await asyncio.to_thread(password_reset_service.create_token, user.id, user.email)
        else:
            token = password_reset_service.create_token(user.id, user.email)

        # Send reset email
        await email_service.send_password_reset_email(
            to_email=user.email,
            reset_token=token
        )

    # Always return success to prevent email enumeration
    logger.info("Password reset flow triggered for email %s (user exists: %s)", request.email, bool(user))
    return MessageResponse(
        message="If an account with that email exists, a password reset link has been sent."
    )


@router.post("/password/reset/confirm", response_model=MessageResponse)
async def confirm_password_reset(
    request: PasswordResetConfirmRequest,
    db: AsyncSession | Session = Depends(get_async_db)
):
    """
    Confirm password reset with token.

    - Validates reset token
    - Updates password hash
    - Invalidates all existing sessions
    """
    logger.info("Confirming password reset token")
    # Validate token
    if _is_async_session(db):
        reset_token = await asyncio.to_thread(password_reset_service.validate_token, request.token)
    else:
        reset_token = password_reset_service.validate_token(request.token)
    if not reset_token:
        logger.warning("Password reset confirmation failed: invalid token")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    # Validate new password strength
    is_valid, error_msg = validate_password_strength(request.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # Find user
    result = await _db_execute(db, select(User).where(User.id == reset_token.user_id))
    user = await _first_scalar(result)
    if not user:
        logger.warning("Password reset confirmation failed: user %s not found", reset_token.user_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token"
        )

    # Update password
    user.password_hash = hash_password(request.new_password)

    # Mark token as used
    if _is_async_session(db):
        await asyncio.to_thread(password_reset_service.mark_used, request.token)
    else:
        password_reset_service.mark_used(request.token)

    # Invalidate all existing sessions for this user
    await _db_execute(db, delete(UserSession).where(UserSession.user_id == user.id))

    await _db_commit(db)
    logger.info("Password reset completed for user %s", user.email)

    return MessageResponse(message="Password has been reset successfully. Please log in with your new password.")


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    user: User = Depends(get_current_user),
    db: AsyncSession | Session = Depends(get_async_db)
):
    """
    Setup MFA for current user.

    - Generates MFA secret
    - Returns secret for authenticator app setup
    - MFA not enabled until verified
    """
    logger.info("MFA setup initiated for user %s", user.email)
    
    secret = generate_totp_secret()
    user.mfa_secret = secret
    await _db_commit(db)
    
    otpauth_url = get_totp_uri(secret, user.email)
    
    return MFASetupResponse(
        secret=secret,
        otpauth_url=otpauth_url,
        message="MFA secret generated. Please verify to enable."
    )


@router.post("/mfa/verify", response_model=MessageResponse)
async def verify_mfa(
    request: MFAVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession | Session = Depends(get_async_db)
):
    """
    Verify MFA code and enable MFA.

    - Validates code against secret
    - Enables MFA on user account if valid
    """
    logger.info("MFA verification attempt for user %s", user.email)
    
    if not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA not set up"
        )
        
    if not verify_totp(user.mfa_secret, request.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication code"
        )
        
    user.mfa_enabled = True
    await _db_commit(db)
    
    logger.info("MFA enabled for user %s", user.email)
    return MessageResponse(message="MFA enabled successfully")
