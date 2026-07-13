from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"


class Settings(BaseSettings):
    """Runtime configuration.

    The public deploy runs with ENABLE_LLM=false and no API key, so no financial
    data ever leaves the server. ANTHROPIC_API_KEY is only read locally.
    """

    enable_llm: bool = False
    anthropic_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
