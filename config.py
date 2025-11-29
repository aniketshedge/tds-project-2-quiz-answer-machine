from functools import lru_cache
from typing import Optional

from pydantic import BaseSettings, AnyHttpUrl


class Settings(BaseSettings):
    openai_api_key: str
    openai_base_url: Optional[AnyHttpUrl] = None
    openai_model: str = "gpt-5.1"
    openai_transcription_model: str = "gpt-4o-mini-transcribe"

    student_secret: str

    # Time budget in seconds for a single /run request
    max_run_seconds: int = 170

    # Playwright settings
    browser_timeout_ms: int = 30000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
