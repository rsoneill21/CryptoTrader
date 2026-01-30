"""Application configuration shared across the backend."""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List

from pydantic import BaseSettings, Field, validator


class AppSettings(BaseSettings):
    """Runtime and security configuration loaded from the environment."""

    app_env: str = Field("development", env="APP_ENV")
    host: str = Field("0.0.0.0", env="APP_HOST")
    port: int = Field(8000, env="APP_PORT")

    frontend_origins: List[str] = Field(
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


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    """Return a cached AppSettings instance."""

    return AppSettings()
