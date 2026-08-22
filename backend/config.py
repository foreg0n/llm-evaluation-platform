from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEVELOPMENT_AUTH_SECRET = "development-only-change-this-auth-secret-key"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LLM Evaluation Platform"
    app_version: str = "0.22.0"
    environment: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
    )
    log_format: Literal["json", "text"] = Field(
        default="json",
        validation_alias="LOG_FORMAT",
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
    access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
        validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES",
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

    @model_validator(mode="after")
    def require_production_auth_secret(self) -> Settings:
        if (
            self.environment.lower() == "production"
            and self.auth_secret_key == DEVELOPMENT_AUTH_SECRET
        ):
            raise ValueError("AUTH_SECRET_KEY must be changed in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
