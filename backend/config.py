from __future__ import annotations

from binascii import Error as BinasciiError
from functools import lru_cache
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEVELOPMENT_AUTH_SECRET = "development-only-change-this-auth-secret-key"
DEVELOPMENT_CREDENTIAL_ENCRYPTION_KEY = (
    "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LLM Evaluation Platform"
    app_version: str = "0.34.0"
    environment: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
    )
    log_format: Literal["json", "text"] = Field(
        default="json",
        validation_alias="LOG_FORMAT",
    )
    tracing_enabled: bool = Field(
        default=False,
        validation_alias="TRACING_ENABLED",
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="http://127.0.0.1:4318/v1/traces",
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    otel_export_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=30,
        validation_alias="OTEL_EXPORT_TIMEOUT_SECONDS",
    )
    otel_trace_sample_ratio: float = Field(
        default=1.0,
        ge=0,
        le=1,
        validation_alias="OTEL_TRACE_SAMPLE_RATIO",
    )
    sentry_enabled: bool = Field(
        default=False,
        validation_alias="SENTRY_ENABLED",
    )
    sentry_dsn: str | None = Field(
        default=None,
        validation_alias="SENTRY_DSN",
    )
    sentry_error_sample_rate: float = Field(
        default=1.0,
        ge=0,
        le=1,
        validation_alias="SENTRY_ERROR_SAMPLE_RATE",
    )
    database_url: str = Field(
        default=(
            "postgresql+asyncpg://postgres:postgres@localhost:5432/"
            "llm_evaluation"
        ),
        validation_alias="DATABASE_URL",
    )
    database_echo: bool = Field(
        default=False,
        validation_alias="DATABASE_ECHO",
    )
    task_backend: Literal["inprocess", "celery"] = Field(
        default="inprocess",
        validation_alias="TASK_BACKEND",
    )
    celery_broker_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="CELERY_BROKER_URL",
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/1",
        validation_alias="CELERY_RESULT_BACKEND",
    )
    readiness_timeout_seconds: float = Field(
        default=1.0,
        gt=0,
        le=10,
        validation_alias="READINESS_TIMEOUT_SECONDS",
    )
    celery_metrics_enabled: bool = Field(
        default=True,
        validation_alias="CELERY_METRICS_ENABLED",
    )
    celery_metrics_host: str = Field(
        default="127.0.0.1",
        validation_alias="CELERY_METRICS_HOST",
    )
    celery_metrics_port: int = Field(
        default=9808,
        ge=1,
        le=65535,
        validation_alias="CELERY_METRICS_PORT",
    )
    auth_secret_key: str = Field(
        default=DEVELOPMENT_AUTH_SECRET,
        min_length=32,
        validation_alias="AUTH_SECRET_KEY",
    )
    credential_encryption_key: SecretStr = Field(
        default=DEVELOPMENT_CREDENTIAL_ENCRYPTION_KEY,
        validation_alias="CREDENTIAL_ENCRYPTION_KEY",
    )
    model_catalog_timeout_seconds: float = Field(
        default=10,
        gt=0,
        le=30,
        validation_alias="MODEL_CATALOG_TIMEOUT_SECONDS",
    )
    model_catalog_cache_ttl_seconds: int = Field(
        default=300,
        ge=0,
        le=3600,
        validation_alias="MODEL_CATALOG_CACHE_TTL_SECONDS",
    )
    access_token_expire_minutes: int = Field(
        default=15,
        ge=1,
        validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expire_days: int = Field(
        default=30,
        ge=1,
        le=365,
        validation_alias="REFRESH_TOKEN_EXPIRE_DAYS",
    )
    refresh_cookie_name: str = Field(
        default="evalflow_refresh_token",
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_-]+$",
        validation_alias="REFRESH_COOKIE_NAME",
    )
    refresh_cookie_secure: bool = Field(
        default=False,
        validation_alias="REFRESH_COOKIE_SECURE",
    )
    refresh_cookie_samesite: Literal["lax", "strict"] = Field(
        default="lax",
        validation_alias="REFRESH_COOKIE_SAMESITE",
    )
    auth_rate_limit_backend: Literal["memory", "redis"] = Field(
        default="memory",
        validation_alias="AUTH_RATE_LIMIT_BACKEND",
    )
    auth_rate_limit_attempts: int = Field(
        default=5,
        ge=1,
        le=100,
        validation_alias="AUTH_RATE_LIMIT_ATTEMPTS",
    )
    auth_rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        le=3600,
        validation_alias="AUTH_RATE_LIMIT_WINDOW_SECONDS",
    )
    require_email_verification: bool = Field(
        default=True,
        validation_alias="REQUIRE_EMAIL_VERIFICATION",
    )
    email_verification_expire_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        validation_alias="EMAIL_VERIFICATION_EXPIRE_HOURS",
    )
    password_reset_expire_minutes: int = Field(
        default=30,
        ge=5,
        le=1440,
        validation_alias="PASSWORD_RESET_EXPIRE_MINUTES",
    )
    email_backend: Literal["console", "smtp"] = Field(
        default="console",
        validation_alias="EMAIL_BACKEND",
    )
    frontend_public_url: str = Field(
        default="http://localhost:3000",
        validation_alias="FRONTEND_PUBLIC_URL",
    )
    email_from_address: str = Field(
        default="no-reply@evalflow.local",
        validation_alias="EMAIL_FROM_ADDRESS",
    )
    smtp_host: str = Field(default="localhost", validation_alias="SMTP_HOST")
    smtp_port: int = Field(
        default=587,
        ge=1,
        le=65535,
        validation_alias="SMTP_PORT",
    )
    smtp_username: str | None = Field(
        default=None,
        validation_alias="SMTP_USERNAME",
    )
    smtp_password: SecretStr = Field(
        default="",
        validation_alias="SMTP_PASSWORD",
    )
    smtp_starttls: bool = Field(
        default=True,
        validation_alias="SMTP_STARTTLS",
    )
    smtp_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        le=60,
        validation_alias="SMTP_TIMEOUT_SECONDS",
    )
    cors_origins: str = Field(
        default=(
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:5173,http://127.0.0.1:5173"
        ),
        validation_alias="CORS_ORIGINS",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @field_validator("credential_encryption_key")
    @classmethod
    def validate_credential_encryption_key(cls, value: SecretStr) -> SecretStr:
        try:
            Fernet(value.get_secret_value().encode("ascii"))
        except (BinasciiError, TypeError, UnicodeError, ValueError) as exc:
            raise ValueError(
                "CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key"
            ) from exc
        return value

    @model_validator(mode="after")
    def require_production_auth_secret(self) -> Settings:
        if (
            self.environment.lower() == "production"
            and self.auth_secret_key == DEVELOPMENT_AUTH_SECRET
        ):
            raise ValueError("AUTH_SECRET_KEY must be changed in production")
        if (
            self.environment.lower() == "production"
            and self.credential_encryption_key.get_secret_value()
            == DEVELOPMENT_CREDENTIAL_ENCRYPTION_KEY
        ):
            raise ValueError(
                "CREDENTIAL_ENCRYPTION_KEY must be changed in production"
            )
        if self.sentry_enabled and not (
            self.sentry_dsn and self.sentry_dsn.strip()
        ):
            raise ValueError("SENTRY_DSN is required when SENTRY_ENABLED=true")
        if not self.frontend_public_url.startswith(("http://", "https://")):
            raise ValueError(
                "FRONTEND_PUBLIC_URL must be an absolute http:// or https:// URL"
            )
        if self.email_backend == "smtp" and not self.smtp_host.strip():
            raise ValueError("SMTP_HOST is required when EMAIL_BACKEND=smtp")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
