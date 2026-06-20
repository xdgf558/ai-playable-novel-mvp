from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    app_name: str = "AI Playable Novel API"
    app_version: str = "0.1.0"
    database_url: str = "sqlite:///./playable_novel.db"
    daily_turn_limit: int = 50

    llm_fake_mode: bool = True
    llm_provider: str = "fake"
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = Field(default=None, repr=False)
    llm_model_fast: str = "fake-fast"
    llm_model_quality: str = "fake-quality"
    llm_timeout_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
