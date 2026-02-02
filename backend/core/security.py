"""
Security utilities for password hashing and token generation.
"""

import secrets
import hashlib
import hmac
import base64
import struct
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
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
    return datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)


def generate_totp_secret() -> str:
    """
    Generate a random base32 encoded secret string for TOTP.
    
    Returns:
        Base32 encoded secret string (32 chars)
    """
    # 20 bytes = 160 bits, standard for SHA1 TOTP
    return base64.b32encode(secrets.token_bytes(20)).decode('utf-8')


def compute_totp(secret: str, interval: int = 30) -> str:
    """
    Compute current TOTP code for a secret.
    
    Args:
        secret: Base32 encoded secret
        interval: Time step in seconds (default 30)
        
    Returns:
        6-digit TOTP code string
    """
    try:
        # Add padding if needed for base32 decoding
        padding = len(secret) % 8
        if padding != 0:
            secret += "=" * (8 - padding)
        key = base64.b32decode(secret, casefold=True)
    except Exception:
        return ""
    
    timestamp = int(time.time())
    counter = int(timestamp // interval)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[19] & 0xf
    code = (struct.unpack(">I", digest[offset:offset+4])[0] & 0x7fffffff) % 1000000
    return "{:06d}".format(code)


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    """
    Verify a TOTP code against a secret.
    Allows for a time window (default +/- 1 step = 30s).
    
    Args:
        secret: Base32 encoded secret
        code: 6-digit code to verify
        window: Number of intervals to check before/after current
        
    Returns:
        True if code is valid
    """
    if not secret or len(code) != 6 or not code.isdigit():
        return False
        
    try:
        # Add padding if needed
        padding = len(secret) % 8
        if padding != 0:
            secret += "=" * (8 - padding)
        key = base64.b32decode(secret, casefold=True)
    except Exception:
        return False

    timestamp = int(time.time())
    current_counter = int(timestamp // 30)
    
    # Check current, previous, and next windows
    for i in range(-window, window + 1):
        counter = current_counter + i
        msg = struct.pack(">Q", counter)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[19] & 0xf
        calculated = (struct.unpack(">I", digest[offset:offset+4])[0] & 0x7fffffff) % 1000000
        if "{:06d}".format(calculated) == code:
            return True
            
    return False


def get_totp_uri(secret: str, name: str, issuer: str = "CryptoTrader") -> str:
    """
    Generate otpauth URI for QR code.
    
    Args:
        secret: Base32 encoded secret
        name: Account name (e.g. email)
        issuer: Issuer name
        
    Returns:
        otpauth URI string
    """
    # otpauth://totp/Issuer:Account?secret=...&issuer=Issuer
    label = f"{issuer}:{name}"
    params = {
        "secret": secret,
        "issuer": issuer
    }
    return f"otpauth://totp/{urllib.parse.quote(label)}?{urllib.parse.urlencode(params)}"
