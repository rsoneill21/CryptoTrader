"""
Security utilities for password hashing and token generation.
"""

import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional

import bcrypt


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        password: Plain text password to verify
        hashed: Hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def generate_session_token() -> str:
    """
    Generate a secure random session token.

    Returns:
        32-character hex token
    """
    return secrets.token_hex(32)


def generate_reset_token() -> str:
    """
    Generate a secure random password reset token.

    Returns:
        32-character hex token
    """
    return secrets.token_hex(32)


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password meets strength requirements.

    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"

    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"

    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"

    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        return False, "Password must contain at least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)"

    return True, None


def get_session_expiry(timeout_minutes: int = 60) -> datetime:
    """
    Calculate session expiry time.

    Args:
        timeout_minutes: Session timeout in minutes (default 60)

    Returns:
        Datetime when session expires
    """
    return datetime.utcnow() + timedelta(minutes=timeout_minutes)
