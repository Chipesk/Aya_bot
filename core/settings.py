"""Environment configuration for Aya."""
from __future__ import annotations

from functools import cached_property
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    TELEGRAM_TOKEN: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None

    OPENWEATHER_API_KEY: Optional[str] = None
    NEWS_API_KEY: Optional[str] = None

    AYA_CITY: str = "Saint Petersburg"
    AYA_TZ: str = "Europe/Moscow"

    LOG_LEVEL: str = "INFO"
    ENV: str = "dev"
    DIAG: int = 0
    POLICY_TRACE: int = 0

    DB_PATH: str = "aya.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @cached_property
    def is_prod(self) -> bool:
        return self.ENV.lower() == "prod"

    @cached_property
    def is_diag(self) -> bool:
        return bool(int(self.DIAG))

    def bot_token(self) -> str:
        token = (self.TELEGRAM_TOKEN or "").strip()
        if token:
            return token
        if self.ENV.lower() in {"dev", "test"}:
            return "TEST:TOKEN"
        raise RuntimeError("TELEGRAM_TOKEN is missing and no dev fallback allowed")


settings = Settings()
