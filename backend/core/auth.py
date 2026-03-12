"""
Authentication middleware and dependencies.
"""

from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status, Cookie, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession

from db.database import get_async_db
from db.models import User, Session as UserSession
from core.settings import get_app_settings

settings = get_app_settings()

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)


def _extract_bearer_token(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parts = value.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return value.strip()


async def _get_session_by_token(token: Optional[str], db: AsyncSession | SyncSession) -> UserSession:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(UserSession).where(UserSession.token == token)
    if isinstance(db, AsyncSession):
        result = await db.execute(stmt)
    else:
        result = db.execute(stmt)
    session = result.scalars().first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if session.expires_at < datetime.utcnow():
        if isinstance(db, AsyncSession):
            await db.delete(session)
            await db.commit()
        else:
            db.delete(session)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return session


def _get_websocket_token(websocket: WebSocket) -> Optional[str]:
    token = None
    if websocket.cookies:
        token = websocket.cookies.get(settings.session_cookie_name)
    if not token:
        token = _extract_bearer_token(websocket.headers.get("authorization"))
    if not token:
        token = websocket.query_params.get("token")
    return token


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session_cookie: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    """
    Dependency to get the current authenticated user.

    Extracts token from Cookie or Authorization header, validates session,
    and returns the user. Raises 401 if invalid or expired.
    """
    token = session_cookie
    if not token and credentials:
        token = credentials.credentials

    session = await _get_session_by_token(token, db)

    result = await db.execute(select(User).where(User.id == session.user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_session(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session_cookie: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
    db: AsyncSession = Depends(get_async_db)
) -> UserSession:
    """
    Dependency to get the current session.

    Returns the session object for operations like logout.
    """
    token = session_cookie
    if not token and credentials:
        token = credentials.credentials

    return await _get_session_by_token(token, db)


async def get_current_session_ws(websocket: WebSocket, db: AsyncSession | SyncSession) -> UserSession:
    """Validate a WebSocket connection against the current session token."""
    token = _get_websocket_token(websocket)
    return await _get_session_by_token(token, db)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session_cookie: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
    db: AsyncSession = Depends(get_async_db)
) -> Optional[User]:
    """
    Dependency to optionally get the current user.

    Returns None if not authenticated instead of raising an error.
    """
    token = session_cookie
    if not token and credentials:
        token = credentials.credentials

    if not token:
        return None

    try:
        return await get_current_user(credentials, session_cookie, db)
    except HTTPException:
        return None
