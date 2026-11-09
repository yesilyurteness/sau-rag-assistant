"""Application settings, loaded from environment variables and an optional .env file.

All configuration lives here so the rest of the code never reads os.environ directly.
Secrets are typed as SecretStr so they are masked in logs and reprs.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application
    app_name: str = "sau-rag-assistant"
    app_env: Environment = "dev"
    log_level: LogLevel = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8501"])

    # --- Datastores
    database_url: PostgresDsn = PostgresDsn("postgresql+asyncpg://rag:rag@localhost:5432/rag")
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")

    # --- Providers (optional until the stage that needs them)
    anthropic_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    cohere_api_key: SecretStr | None = None
    hf_token: SecretStr | None = None

    # --- Observability
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance; use as a FastAPI dependency or call directly."""
    return Settings()
