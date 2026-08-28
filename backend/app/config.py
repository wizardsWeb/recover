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

    #: Redis, for the network alert fan-out. Empty falls back to an in-process
    #: `fakeredis` so local development works with nothing installed — see
    #: `get_redis_client`. Production always sets this.
    REDIS_URL: str = ""

    #: Whether the background network poller runs. On in production and local
    #: development; off in tests, where a loop polling a live Supabase project
    #: on every `TestClient` startup would be both slow and non-deterministic.
    NETWORK_POLLER_ENABLED: bool = True

    #: Seconds between network aggregation passes.
    NETWORK_POLL_INTERVAL_SECONDS: int = 60

    @property
    def allowed_origins(self) -> list[str]:
        """``ALLOWED_ORIGINS`` as a list, so it can be a comma-separated env var."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()  # type: ignore[call-arg]
