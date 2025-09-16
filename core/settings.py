# core/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    TELEGRAM_TOKEN: str
    DEEPSEEK_API_KEY: str | None = None

    # добавили недостающие ключи (на будущее для мира/новостей)
    OPENWEATHER_API_KEY: str | None = None
    NEWS_API_KEY: str | None = None

    AYA_CITY: str = "Saint Petersburg"
    AYA_TZ: str = "Europe/Moscow"

    LOG_LEVEL: str = "INFO"
    AYA_ENV: str = "dev"

    DB_PATH: str = "aya.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # игнорируем любые незадекларированные ключи в .env
    )

settings = Settings()
