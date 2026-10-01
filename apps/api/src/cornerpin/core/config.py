from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/src/cornerpin/core/config.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[5]


class Settings(BaseSettings):
    """Configuration from the environment; locally from the repo-root .env file."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "local"
    database_url: str = "postgresql+psycopg://cornerpin:cornerpin@localhost:5434/cornerpin"
    smtp_host: str = "localhost"
    smtp_port: int = 1025


@lru_cache
def get_settings() -> Settings:
    return Settings()
