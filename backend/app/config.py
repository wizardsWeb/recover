"""Application settings, loaded once from the environment."""

from functools import lru_cache

from pydantic import AliasChoices, Field
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

    # ── Razorpay ─────────────────────────────────────────────────────────
    # All three default to empty, and that is load-bearing: with no keys the
    # execution adapters fall back to simulation and the webhook endpoint keeps
    # accepting the simulator's unsigned calls. A missing key degrades the
    # integration; it never stops the service booting.
    #
    # Each accepts two names. The deployed secrets are RAZORPAY_TEST_API_KEY /
    # RAZORPAY_TEST_KEY_SECRET; RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are the
    # names Razorpay's own docs use, so both resolve rather than leaving a
    # correctly-configured environment looking unconfigured because of a
    # spelling.

    #: ``rzp_test_…`` in test mode, ``rzp_live_…`` in production.
    RAZORPAY_KEY_ID: str = Field(
        default="",
        validation_alias=AliasChoices("RAZORPAY_TEST_API_KEY", "RAZORPAY_KEY_ID"),
    )

    #: Never logged, never returned by an endpoint, never in git.
    RAZORPAY_KEY_SECRET: str = Field(
        default="",
        validation_alias=AliasChoices("RAZORPAY_TEST_KEY_SECRET", "RAZORPAY_KEY_SECRET"),
    )

    #: The webhook signing secret set in the Razorpay dashboard. Separate from
    #: the API secret: it authenticates inbound calls, where the API secret
    #: authenticates outbound ones, and they rotate independently.
    RAZORPAY_WEBHOOK_SECRET: str = ""

    #: Which merchant a signature-verified webhook belongs to when the payload's
    #: customer is not one we already know.
    #:
    #: A real Razorpay webhook carries no bearer token, so the endpoint cannot
    #: read the merchant from a JWT the way the simulator's calls do. It first
    #: tries to resolve the merchant from the customer in the payload; this is
    #: the fallback for the first event about a customer we have never seen.
    #: One Razorpay account maps to one merchant here, which is true of this
    #: deployment and would not be true of a multi-tenant one — that would key
    #: off the account id in the payload instead.
    RAZORPAY_WEBHOOK_MERCHANT_ID: str = ""

    #: The real Razorpay test-mode subscription and customer that scenario S1
    #: should fire against, created by hand in the dashboard.
    #:
    #: Empty falls back to the scripted fixture ids, which is what keeps the six
    #: scenarios runnable with no Razorpay account. Set them and S1 stops being a
    #: simulation: the subscription adapter reads a real subscription's pending
    #: state, and a real ``subscription.charged`` webhook can be matched back to
    #: the case it settled.
    #:
    #: These are ids, not credentials — they identify objects, they do not
    #: authorise anything — which is why they live beside the keys rather than in
    #: them.
    RAZORPAY_DEMO_SUBSCRIPTION_ID: str = ""
    RAZORPAY_DEMO_CUSTOMER_ID: str = ""

    @property
    def razorpay_configured(self) -> bool:
        """Whether outbound Razorpay API calls are possible."""
        return bool(self.RAZORPAY_KEY_ID and self.RAZORPAY_KEY_SECRET)

    @property
    def allowed_origins(self) -> list[str]:
        """``ALLOWED_ORIGINS`` as a list, so it can be a comma-separated env var."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()  # type: ignore[call-arg]
