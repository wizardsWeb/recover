"""Integration status, and the one thing it must never do.

Every assertion below is about the boundary: the endpoint reports whether keys
exist and never what they are. The masking test is the important one — a key id
is public, but an endpoint that returns configuration in full is an endpoint that
will one day be asked to return the secret too.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.integrations import _mask, _mode
from app.config import get_settings
from app.deps import get_current_user_id
from app.main import app
from tests.simulator.conftest import MERCHANT_ID

TEST_KEY = "rzp_test_AbCdEf123456"
SECRET = "super-secret-value"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("RAZORPAY_TEST_API_KEY", TEST_KEY)
    monkeypatch.setenv("RAZORPAY_TEST_KEY_SECRET", SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whsec")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_requires_authentication(client: TestClient) -> None:
    app.dependency_overrides.clear()
    assert client.get("/api/integrations/razorpay").status_code == 401


def test_reports_unconfigured_when_no_keys(client: TestClient) -> None:
    """The suite runs with Razorpay switched off, which is this state."""
    body = client.get("/api/integrations/razorpay").json()

    assert body["apiConfigured"] is False
    assert body["webhookVerified"] is False
    assert body["mode"] == "unconfigured"
    assert body["keyIdMasked"] == ""
    assert body["liveAdapters"] == []


@pytest.mark.usefixtures("configured")
def test_reports_configured_without_leaking_the_secret(client: TestClient) -> None:
    response = client.get("/api/integrations/razorpay")
    body = response.json()

    assert body["apiConfigured"] is True
    assert body["webhookVerified"] is True
    assert body["mode"] == "test"
    assert body["liveAdapters"] == ["Payment Links", "Subscriptions", "Payment fetch"]

    # The whole point of the endpoint's shape.
    assert SECRET not in response.text
    assert TEST_KEY not in response.text


@pytest.mark.usefixtures("configured")
def test_key_id_is_masked_to_its_last_four(client: TestClient) -> None:
    body = client.get("/api/integrations/razorpay").json()
    assert body["keyIdMasked"] == "rzp_test_••••3456"


def test_messaging_adapters_are_never_listed_as_live() -> None:
    """WhatsApp, SMS and email have no provider wired. Listing them would let
    the settings screen imply a real send."""
    from app.api.integrations import _RAZORPAY_ADAPTERS

    joined = " ".join(_RAZORPAY_ADAPTERS).lower()
    assert "whatsapp" not in joined
    assert "sms" not in joined
    assert "email" not in joined


@pytest.mark.parametrize(
    ("key_id", "expected"),
    [
        ("rzp_test_abc123", "test"),
        ("rzp_live_abc123", "live"),
        ("", "unconfigured"),
        ("garbage", "unconfigured"),
    ],
)
def test_mode_reads_the_key_prefix(key_id: str, expected: str) -> None:
    """Read from the key, not the deployment environment — those two disagreeing
    is exactly what is worth surfacing."""
    assert _mode(key_id) == expected


def test_mask_handles_a_key_with_no_separator() -> None:
    assert _mask("abcdef1234") == "••••1234"
    assert _mask("") == ""
