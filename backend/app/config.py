"""Application settings, loaded once from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed configuration.

    Values come from the process environment, falling back to a local ``.env``
    file. Everything Supabase-related is required — the service cannot answer a
    single authenticated request without it, so failing at import time is the
    honest behaviour.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_KEY: str
    SUPABASE_JWT_SECRET: str

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "local"
    VERSION: str = "0.1.0"

    ALLOWED_ORIGINS: str = "http://localhost:3000"

    @property
    def allowed_origins(self) -> list[str]:
        """``ALLOWED_ORIGINS`` as a list, so it can be a comma-separated env var."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()  # type: ignore[call-arg]
