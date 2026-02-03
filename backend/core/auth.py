"""
Authentication middleware and dependencies.
"""

from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status, Cookie, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from db.database import get_db
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


def _get_session_by_token(token: Optional[str], db: Session) -> UserSession:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = db.query(UserSession).filter(UserSession.token == token).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if session.expires_at < datetime.utcnow():
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
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user.

    Extracts token from Cookie or Authorization header, validates session,
    and returns the user. Raises 401 if invalid or expired.
    """
    token = session_cookie
    if not token and credentials:
        token = credentials.credentials

    session = _get_session_by_token(token, db)

    user = db.query(User).filter(User.id == session.user_id).first()
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
    db: Session = Depends(get_db)
) -> UserSession:
    """
    Dependency to get the current session.

    Returns the session object for operations like logout.
    """
    token = session_cookie
    if not token and credentials:
        token = credentials.credentials

    return _get_session_by_token(token, db)


async def get_current_session_ws(websocket: WebSocket, db: Session) -> UserSession:
    """Validate a WebSocket connection against the current session token."""
    token = _get_websocket_token(websocket)
    return _get_session_by_token(token, db)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session_cookie: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
    db: Session = Depends(get_db)
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
