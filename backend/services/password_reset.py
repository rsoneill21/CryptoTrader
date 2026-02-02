"""
Password reset token management.

Uses in-memory storage for development.
For production, use database table or Redis.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass

from core.security import generate_reset_token


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

        self.tokens[token] = ResetToken(
            token=token,
            user_id=user_id,
            email=email,
            expires_at=expires_at,
        )

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
        reset_token = self.tokens.get(token)

        if not reset_token:
            return None

        if reset_token.used:
            return None

        if reset_token.expires_at < datetime.now(timezone.utc):
            return None

        return reset_token

    def mark_used(self, token: str) -> bool:
        """
        Mark a token as used.

        Args:
            token: The reset token

        Returns:
            True if token was marked, False if not found
        """
        reset_token = self.tokens.get(token)
        if reset_token:
            reset_token.used = True
            return True
        return False

    def _invalidate_user_tokens(self, user_id: int) -> None:
        """Invalidate all tokens for a user."""
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


# Singleton instance
password_reset_service = PasswordResetService()
