"""
Password reset token management.

Backed by the database for persistence across worker processes.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import or_

from core.security import generate_reset_token
from db.database import SessionLocal
from db.models import PasswordResetToken as PasswordResetTokenModel


@dataclass
class ResetToken:
    """Password reset token data."""
    token: str
    user_id: int
    email: str
    expires_at: datetime
    used: bool = False


class PasswordResetService:
    """Manages password reset tokens."""

    def __init__(self, token_lifetime_minutes: int = 60):
        self.tokens: dict[str, ResetToken] = {}
        self.token_lifetime_minutes = token_lifetime_minutes

    def create_token(self, user_id: int, email: str, db: Optional[Any] = None) -> str:
        """
        Create a new password reset token.

        Invalidates any existing tokens for this user.

        Args:
            user_id: User ID
            email: User email

        Returns:
            The reset token string
        """
        # Invalidate existing tokens for this user
        self._invalidate_user_tokens(user_id, db=db)

        # Generate new token
        token = generate_reset_token()
        expires_at = datetime.utcnow() + timedelta(minutes=self.token_lifetime_minutes)

        record = ResetToken(
            token=token,
            user_id=user_id,
            email=email,
            expires_at=expires_at,
        )

        session = db or SessionLocal()
        try:
            db_token = PasswordResetTokenModel(
                token=token,
                user_id=user_id,
                email=email,
                expires_at=expires_at,
                used=False,
            )
            session.add(db_token)
            session.commit()
        finally:
            if db is None:
                session.close()

        self.tokens[token] = record

        # Clean up expired tokens
        self._cleanup_expired(db=db)

        return token

    def validate_token(self, token: str, db: Optional[Any] = None) -> Optional[ResetToken]:
        """
        Validate a reset token.

        Args:
            token: The reset token to validate

        Returns:
            ResetToken if valid, None if invalid/expired/used
        """
        session = db or SessionLocal()
        try:
            db_token = (
                session.query(PasswordResetTokenModel)
                .filter(PasswordResetTokenModel.token == token)
                .first()
            )
            if not db_token:
                return None
            if db_token.used:
                return None
            if db_token.expires_at < datetime.utcnow():
                return None

            reset_token = ResetToken(
                token=db_token.token,
                user_id=db_token.user_id,
                email=db_token.email,
                expires_at=db_token.expires_at,
                used=db_token.used,
            )
            self.tokens[token] = reset_token
            return reset_token
        finally:
            if db is None:
                session.close()

    def mark_used(self, token: str, db: Optional[Any] = None) -> bool:
        """
        Mark a token as used.

        Args:
            token: The reset token

        Returns:
            True if token was marked, False if not found
        """
        session = db or SessionLocal()
        try:
            db_token = (
                session.query(PasswordResetTokenModel)
                .filter(PasswordResetTokenModel.token == token)
                .first()
            )
            if not db_token:
                return False
            db_token.used = True
            session.commit()
        finally:
            if db is None:
                session.close()

        reset_token = self.tokens.get(token)
        if reset_token:
            reset_token.used = True
        return True

    def _invalidate_user_tokens(self, user_id: int, db: Optional[Any] = None) -> None:
        """Invalidate all tokens for a user."""
        session = db or SessionLocal()
        try:
            session.query(PasswordResetTokenModel).filter(
                PasswordResetTokenModel.user_id == user_id,
                PasswordResetTokenModel.used == False,  # noqa: E712
            ).update({"used": True})
            session.commit()
        finally:
            if db is None:
                session.close()

        for token in self.tokens.values():
            if token.user_id == user_id:
                token.used = True

    def _cleanup_expired(self, db: Optional[Any] = None) -> None:
        """Remove expired tokens from memory."""
        now = datetime.utcnow()
        expired = [
            token for token, data in self.tokens.items()
            if data.expires_at < now or data.used
        ]
        for token in expired:
            del self.tokens[token]

        session = db or SessionLocal()
        try:
            session.query(PasswordResetTokenModel).filter(
                or_(
                    PasswordResetTokenModel.expires_at < now,
                    PasswordResetTokenModel.used == True,  # noqa: E712
                )
            ).delete()
            session.commit()
        finally:
            if db is None:
                session.close()


# Singleton instance
password_reset_service = PasswordResetService()
