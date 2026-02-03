"""Application configuration shared across the backend."""

from __future__ import annotations

import re
import threading
from datetime import datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from pydantic import Field, validator
# Pydantic v2 migration: BaseSettings has been moved to the pydantic-settings package
from pydantic_settings import BaseSettings


class ThemeMode(str, Enum):
    """Theme modes supported by the UI."""

    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"


class AppSettings(BaseSettings):
    """Runtime and security configuration loaded from the environment."""

    app_env: str = Field("development", env="APP_ENV")
    host: str = Field("0.0.0.0", env="APP_HOST")
    port: int = Field(8000, env="APP_PORT")

    frontend_origins: Any = Field(
        default_factory=lambda: ["http://localhost:3000"],
        env="FRONTEND_ORIGINS",
    )

    tls_certfile: str | None = Field(None, env="TLS_CERTFILE")
    tls_keyfile: str | None = Field(None, env="TLS_KEYFILE")
    tls_ca_bundle: str | None = Field(None, env="TLS_CA_BUNDLE")

    hsts_max_age_seconds: int = Field(31536000, env="HSTS_MAX_AGE_SECONDS")
    hsts_include_subdomains: bool = Field(True, env="HSTS_INCLUDE_SUBDOMAINS")
    hsts_preload: bool = Field(True, env="HSTS_PRELOAD")

    session_cookie_name: str = Field("cryptotrader_session", env="SESSION_COOKIE_NAME")
    session_cookie_secure: bool = Field(False, env="SESSION_COOKIE_SECURE")
    allow_insecure_cookies: bool = Field(False, env="ALLOW_INSECURE_COOKIES")
    session_cookie_same_site: str = Field("lax", env="SESSION_COOKIE_SAMESITE")
    allow_email_enumeration: bool = Field(False, env="ALLOW_EMAIL_ENUMERATION")

    session_timeout_seconds: int = Field(1800, env="SESSION_TIMEOUT_SECONDS")
    session_idle_warning_seconds: int = Field(120, env="SESSION_IDLE_WARNING_SECONDS")

    notification_email_enabled: bool = Field(True, env="NOTIFICATION_EMAIL_ENABLED")
    notification_sms_enabled: bool = Field(False, env="NOTIFICATION_SMS_ENABLED")
    notification_webhook_enabled: bool = Field(True, env="NOTIFICATION_WEBHOOK_ENABLED")
    notification_digest_minutes: int = Field(60, env="NOTIFICATION_DIGEST_MINUTES")
    notification_dnd_start: Optional[str] = Field(None, env="NOTIFICATION_DND_START")
    notification_dnd_end: Optional[str] = Field(None, env="NOTIFICATION_DND_END")

    theme_default_mode: ThemeMode = Field(ThemeMode.DARK.value, env="THEME_DEFAULT_MODE")
    theme_high_contrast: bool = Field(False, env="THEME_HIGH_CONTRAST")
    theme_auto_follow_system: bool = Field(True, env="THEME_AUTO_FOLLOW_SYSTEM")

    slack_bot_token: Optional[str] = Field(None, env="SLACK_BOT_TOKEN")
    triad_slack_channel: Optional[str] = Field(None, env="TRIAD_SLACK_CHANNEL")
    kraken_api_key: Optional[str] = Field(None, env="KRAKEN_API_KEY")
    kraken_api_secret: Optional[str] = Field(None, env="KRAKEN_API_SECRET")

    database_backup_enabled: bool = Field(True, env="DATABASE_BACKUP_ENABLED")
    database_backup_dir: Path = Field(Path("./backups"), env="DATABASE_BACKUP_DIR")
    database_backup_prefix: str = Field("cryptotrader", env="DATABASE_BACKUP_PREFIX")
    database_backup_retention_days: int = Field(30, env="DATABASE_BACKUP_RETENTION_DAYS")
    database_restore_enabled: bool = Field(True, env="DATABASE_RESTORE_ENABLED")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @validator("frontend_origins", pre=True)
    def _normalize_frontend_origins(cls, value: Iterable[str] | str) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = [origin.strip() for origin in value.split(",") if origin.strip()]
            return candidates
        return list(value)

    @validator("session_cookie_same_site")
    def _normalize_same_site(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("SESSION_COOKIE_SAMESITE must be one of 'lax', 'strict', or 'none'")
        return normalized

    @validator("session_idle_warning_seconds")
    def _idle_warning_before_timeout(cls, value: int, values: Dict[str, Any]) -> int:
        timeout = values.get("session_timeout_seconds")
        if timeout is not None and value >= timeout:
            raise ValueError("SESSION_IDLE_WARNING_SECONDS must be less than SESSION_TIMEOUT_SECONDS")
        return value

    @validator("notification_digest_minutes")
    def _validate_digest_minutes(cls, value: int) -> int:
        if value < 15 or value > 1440:
            raise ValueError("NOTIFICATION_DIGEST_MINUTES must be between 15 and 1440")
        return value

    @classmethod
    def _validate_time_value(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not re.match(r"^\d{2}:\d{2}$", value):
            raise ValueError("DND time must be in HH:MM format")
        hour, minute = map(int, value.split(":"))
        if hour >= 24 or minute >= 60:
            raise ValueError("DND time values must fall within a 24-hour clock")
        return value

    @validator("notification_dnd_start", "notification_dnd_end", pre=True)
    def _validate_dnd_values(cls, value: Optional[str]) -> Optional[str]:
        return cls._validate_time_value(value)

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cors_origins(self) -> List[str]:
        return self.frontend_origins or ["http://localhost:3000"]

    @property
    def tls_enabled(self) -> bool:
        return bool(self.tls_certfile and self.tls_keyfile)

    @property
    def hsts_header_value(self) -> str | None:
        if self.hsts_max_age_seconds <= 0:
            return None
        directives = [f"max-age={self.hsts_max_age_seconds}"]
        if self.hsts_include_subdomains:
            directives.append("includeSubDomains")
        if self.hsts_preload:
            directives.append("preload")
        return "; ".join(directives)

    @property
    def secure_cookies(self) -> bool:
        if self.allow_insecure_cookies:
            return False
        return self.session_cookie_secure or self.is_production

    @validator("database_backup_retention_days")
    def _validate_backup_retention(cls, value: int) -> int:
        if value < 1:
            raise ValueError("DATABASE_BACKUP_RETENTION_DAYS must be at least 1")
        return value

    @property
    def backup_dir_path(self) -> Path:
        return self.database_backup_dir.expanduser().resolve(strict=False)


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    """Return a cached AppSettings instance."""

    return AppSettings()


class UserSettingsStore:
    """In-memory cache of the configurable user preferences that power the Settings page."""

    def __init__(self, defaults: AppSettings) -> None:
        self._lock = threading.RLock()
        self._session_timeout_seconds = defaults.session_timeout_seconds
        self._idle_warning_seconds = defaults.session_idle_warning_seconds
        self._notification_preferences: Dict[str, Any] = {
            "email_alerts": defaults.notification_email_enabled,
            "sms_alerts": defaults.notification_sms_enabled,
            "webhook_alerts": defaults.notification_webhook_enabled,
            "digest_frequency_minutes": defaults.notification_digest_minutes,
            "do_not_disturb_start": defaults.notification_dnd_start,
            "do_not_disturb_end": defaults.notification_dnd_end,
        }
        self._theme_mode = defaults.theme_default_mode.value
        self._theme_high_contrast = defaults.theme_high_contrast
        self._theme_auto_follow_system = defaults.theme_auto_follow_system
        self._api_keys: Dict[str, Dict[str, Any]] = {}

    def session_snapshot(self) -> Dict[str, int]:
        with self._lock:
            return {
                "timeout_seconds": self._session_timeout_seconds,
                "idle_warning_seconds": self._idle_warning_seconds,
            }

    def update_session(
        self,
        timeout_seconds: Optional[int] = None,
        idle_warning_seconds: Optional[int] = None,
    ) -> Dict[str, int]:
        with self._lock:
            if timeout_seconds is not None:
                self._session_timeout_seconds = timeout_seconds
            if idle_warning_seconds is not None:
                self._idle_warning_seconds = idle_warning_seconds
            return self.session_snapshot()

    def notification_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._notification_preferences)

    def update_notifications(
        self,
        email_alerts: Optional[bool] = None,
        sms_alerts: Optional[bool] = None,
        webhook_alerts: Optional[bool] = None,
        digest_frequency_minutes: Optional[int] = None,
        do_not_disturb_start: Optional[str] = None,
        do_not_disturb_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if email_alerts is not None:
                self._notification_preferences["email_alerts"] = email_alerts
            if sms_alerts is not None:
                self._notification_preferences["sms_alerts"] = sms_alerts
            if webhook_alerts is not None:
                self._notification_preferences["webhook_alerts"] = webhook_alerts
            if digest_frequency_minutes is not None:
                self._notification_preferences["digest_frequency_minutes"] = digest_frequency_minutes
            if do_not_disturb_start is not None:
                self._notification_preferences["do_not_disturb_start"] = do_not_disturb_start
            if do_not_disturb_end is not None:
                self._notification_preferences["do_not_disturb_end"] = do_not_disturb_end
            return self.notification_snapshot()

    def theme_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "mode": self._theme_mode,
                "high_contrast": self._theme_high_contrast,
                "auto_follow_system": self._theme_auto_follow_system,
            }

    def update_theme(
        self,
        mode: Optional[str] = None,
        high_contrast: Optional[bool] = None,
        auto_follow_system: Optional[bool] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if mode is not None:
                self._theme_mode = mode
            if high_contrast is not None:
                self._theme_high_contrast = high_contrast
            if auto_follow_system is not None:
                self._theme_auto_follow_system = auto_follow_system
            return self.theme_snapshot()

    def apply_api_key_updates(self, updates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        with self._lock:
            for update in updates:
                name = update.get("name")
                if not name:
                    continue
                normalized = name.lower()
                now = datetime.utcnow()
                entry = self._api_keys.get(normalized)
                if not entry:
                    entry = {
                        "name": name,
                        "value": update.get("value", ""),
                        "enabled": bool(update.get("enabled", True)),
                        "created_at": now,
                        "updated_at": now,
                    }
                    self._api_keys[normalized] = entry
                else:
                    if update.get("value") is not None:
                        entry["value"] = update["value"]
                    if update.get("enabled") is not None:
                        entry["enabled"] = update["enabled"]
                    entry["updated_at"] = now
                results.append(self._format_api_key_entry(entry))
        return results

    def list_api_keys(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._format_api_key_entry(entry) for entry in self._api_keys.values()]

    def _format_api_key_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": entry["name"],
            "enabled": entry.get("enabled", False),
            "status": "enabled" if entry.get("enabled") else "disabled",
            "masked_value": self._mask_value(entry.get("value", "")),
            "created_at": entry.get("created_at"),
            "last_updated": entry.get("updated_at"),
        }

    @staticmethod
    def _mask_value(value: str) -> str:
        if not value:
            return ""
        if len(value) <= 4:
            return "*" * len(value)
        return "*" * (len(value) - 4) + value[-4:]


_USER_SETTINGS_STORE: Optional[UserSettingsStore] = None


def get_user_settings_store() -> UserSettingsStore:
    """Return a singleton store that holds runtime user preferences."""

    global _USER_SETTINGS_STORE
    if _USER_SETTINGS_STORE is None:
        _USER_SETTINGS_STORE = UserSettingsStore(get_app_settings())
    return _USER_SETTINGS_STORE
