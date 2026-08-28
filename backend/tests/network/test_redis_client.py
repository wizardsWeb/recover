"""The Redis factory.

Nothing on the recovery path depends on Redis — an alert row in Postgres is
what blocks a retry, and it is written before anything is published. What
depends on it is the dashboard being live, so the only property that matters
here is that a missing URL degrades instead of crashing the process at startup.
"""

import pytest

from app.config import get_settings
from app.db import get_redis_client


@pytest.fixture(autouse=True)
def uncached() -> None:
    get_redis_client.cache_clear()


async def test_no_redis_url_yields_a_working_in_process_fake() -> None:
    """A laptop with nothing installed must still boot and still publish."""
    client = get_redis_client()

    assert await client.publish("network:alerts", "{}") == 0


def test_a_configured_url_is_used_rather_than_the_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fake is per-process, so a multi-replica deployment must not get one."""
    monkeypatch.setattr(get_settings(), "REDIS_URL", "redis://localhost:6379/0")

    client = get_redis_client()

    assert type(client).__module__.startswith("redis.")
    assert "fakeredis" not in type(client).__module__
