"""
Email service for sending notifications.

Currently uses mock implementation - replace with real SMTP/SendGrid/etc in production.
"""

import logging
from typing import Optional

from core.settings import get_app_settings

logger = logging.getLogger(__name__)
settings = get_app_settings()


class EmailService:
    """Mock email service for development."""

    def __init__(self):
        self.sent_emails: list[dict] = []

    async def send_password_reset_email(
        self,
        to_email: str,
        reset_token: str,
        reset_url_base: str = "http://localhost:3000/reset-password"
    ) -> bool:
        """
        Send password reset email.

        In production, this would send a real email.
        For development, it logs the email and stores it.

        Args:
            to_email: Recipient email address
            reset_token: The password reset token
            reset_url_base: Base URL for reset link

        Returns:
            True if email was "sent" successfully
        """
        reset_url = f"{reset_url_base}?token={reset_token}"

        email_content = {
            "to": to_email,
            "subject": "CryptoTrader - Password Reset Request",
            "body": f"""
You have requested a password reset for your CryptoTrader account.

Click the link below to reset your password:
{reset_url}

This link will expire in 1 hour.

If you did not request this reset, please ignore this email.

- CryptoTrader Team
            """.strip(),
            "reset_token": reset_token,
            "reset_url": reset_url,
        }

        # Log for development (avoid leaking tokens unless explicitly enabled)
        logger.info("[MOCK EMAIL] Password reset email to %s", to_email)
        if settings.mock_email_log_tokens:
            logger.info("[MOCK EMAIL] Reset URL: %s", reset_url)
        else:
            logger.info("[MOCK EMAIL] Reset URL: [REDACTED]")

        # Store for testing
        self.sent_emails.append(email_content)

        # Print to console for easy development access
        print(f"\n{'='*50}")
        print(f"MOCK EMAIL - Password Reset")
        print(f"To: {to_email}")
        if settings.mock_email_log_tokens:
            print(f"Reset URL: {reset_url}")
            print(f"Token: {reset_token}")
        else:
            print("Reset URL: [REDACTED]")
            print("Token: [REDACTED]")
        print(f"{'='*50}\n")

        return True

    async def send_mfa_code_email(
        self,
        to_email: str,
        code: str
    ) -> bool:
        """
        Send MFA verification code email.

        Args:
            to_email: Recipient email address
            code: The MFA code

        Returns:
            True if email was "sent" successfully
        """
        email_content = {
            "to": to_email,
            "subject": "CryptoTrader - Your Verification Code",
            "body": f"""
Your CryptoTrader verification code is: {code}

This code will expire in 10 minutes.

If you did not request this code, please secure your account immediately.

- CryptoTrader Team
            """.strip(),
            "code": code,
        }

        logger.info(f"[MOCK EMAIL] MFA code email to {to_email}: {code}")
        self.sent_emails.append(email_content)

        print(f"\n{'='*50}")
        print(f"MOCK EMAIL - MFA Code")
        print(f"To: {to_email}")
        print(f"Code: {code}")
        print(f"{'='*50}\n")

        return True

    def get_last_email(self) -> Optional[dict]:
        """Get the last sent email (for testing)."""
        return self.sent_emails[-1] if self.sent_emails else None


# Singleton instance
email_service = EmailService()
