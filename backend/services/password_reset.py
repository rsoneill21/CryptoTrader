"""
Password reset token management.

Backed by the database for persistence across worker processes.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

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

    def create_token(self, user_id: int, email: str) -> str:
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
        self._invalidate_user_tokens(user_id)

        # Generate new token
        token = generate_reset_token()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.token_lifetime_minutes)

        record = ResetToken(
            token=token,
            user_id=user_id,
            email=email,
            expires_at=expires_at,
        )

        session = SessionLocal()
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
            session.close()

        self.tokens[token] = record

        # Clean up expired tokens
        self._cleanup_expired()

        return token

    def validate_token(self, token: str) -> Optional[ResetToken]:
        """
        Validate a reset token.

        Args:
            token: The reset token to validate

        Returns:
            ResetToken if valid, None if invalid/expired/used
        """
        session = SessionLocal()
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
            if db_token.expires_at < datetime.now(timezone.utc):
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
            session.close()

    def mark_used(self, token: str) -> bool:
        """
        Mark a token as used.

        Args:
            token: The reset token

        Returns:
            True if token was marked, False if not found
        """
        session = SessionLocal()
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
            session.close()

        reset_token = self.tokens.get(token)
        if reset_token:
            reset_token.used = True
        return True

    def _invalidate_user_tokens(self, user_id: int) -> None:
        """Invalidate all tokens for a user."""
        session = SessionLocal()
        try:
            session.query(PasswordResetTokenModel).filter(
                PasswordResetTokenModel.user_id == user_id,
                PasswordResetTokenModel.used == False,  # noqa: E712
            ).update({"used": True})
            session.commit()
        finally:
            session.close()

        for token in self.tokens.values():
            if token.user_id == user_id:
                token.used = True

    def _cleanup_expired(self) -> None:
        """Remove expired tokens from memory."""
        now = datetime.now(timezone.utc)
        expired = [
            token for token, data in self.tokens.items()
            if data.expires_at < now or data.used
        ]
        for token in expired:
            del self.tokens[token]

        session = SessionLocal()
        try:
            session.query(PasswordResetTokenModel).filter(
                or_(
                    PasswordResetTokenModel.expires_at < now,
                    PasswordResetTokenModel.used == True,  # noqa: E712
                )
            ).delete()
            session.commit()
        finally:
            session.close()


# Singleton instance
password_reset_service = PasswordResetService()
