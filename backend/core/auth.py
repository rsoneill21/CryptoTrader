"""
Authentication middleware and dependencies.
"""

from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import User, Session as UserSession
from core.settings import get_app_settings

settings = get_app_settings()

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)


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

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Find session by token
    session = db.query(UserSession).filter(UserSession.token == token).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if session is expired
    if session.expires_at < datetime.utcnow():
        # Clean up expired session
        db.delete(session)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user
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
