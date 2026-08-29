"""Webhook authentication and envelope normalisation.

The endpoint has two authenticators and they are the security boundary of the
whole integration: without signature verification, anyone who learns the URL can
post ``payment.captured`` and close cases as recovered. These tests cover the
matrix — valid signature, wrong signature, no signature, both — rather than the
happy path alone, because the interesting failures here are the permissive ones.
"""

import hashlib
import hmac
import json

import pytest

from app.integrations.razorpay_webhook import (
    is_razorpay_envelope,
    normalize_razorpay_event,
    verify_razorpay_signature,
)

SECRET = "whsec_test_secret"


def sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ─────────────────────────────────────────────────────────────────────
# Signature verification
# ─────────────────────────────────────────────────────────────────────


def test_valid_signature_verifies() -> None:
    body = b'{"event":"payment.captured"}'
    assert verify_razorpay_signature(body, sign(body), SECRET) is True


def test_tampered_body_fails() -> None:
    """The signature covers the bytes, so changing one rejects the request."""
    body = b'{"event":"payment.captured","amount":100}'
    signature = sign(body)
    tampered = b'{"event":"payment.captured","amount":999999}'
    assert verify_razorpay_signature(tampered, signature, SECRET) is False


def test_wrong_secret_fails() -> None:
    body = b'{"event":"payment.captured"}'
    assert verify_razorpay_signature(body, sign(body, "other-secret"), SECRET) is False


def test_reserialised_body_fails() -> None:
    """Why the endpoint must hash the raw bytes, not a re-dump of the parsed body.

    `json.dumps` of a parsed body is semantically identical and byte-different,
    and the digest is over bytes. This test exists to fail loudly if anyone
    "simplifies" the endpoint to sign `json.dumps(payload)`.
    """
    raw = b'{"event": "payment.captured",  "amount": 100}'
    signature = sign(raw)
    reserialised = json.dumps(json.loads(raw)).encode()
    assert reserialised != raw
    assert verify_razorpay_signature(reserialised, signature, SECRET) is False


@pytest.mark.parametrize(
    ("signature", "secret"),
    [("", SECRET), ("abc", ""), ("", "")],
)
def test_missing_inputs_return_false(signature: str, secret: str) -> None:
    """No secret or no signature is a rejection, never an exception."""
    assert verify_razorpay_signature(b"{}", signature, secret) is False


# ─────────────────────────────────────────────────────────────────────
# Envelope normalisation
# ─────────────────────────────────────────────────────────────────────

PAYMENT_FAILED = {
    "event": "payment.failed",
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_TEST123",
                "amount": 299900,
                "currency": "INR",
                "status": "failed",
                "method": "card",
                "bank": "HDFC",
                "customer_id": "cust_suresh_iyer",
                "email": "suresh@test.com",
                "contact": "+919812345001",
                "error_code": "BAD_REQUEST_ERROR",
                "error_description": "insufficient funds",
                "notes": {"case_id": "case-abc"},
            }
        }
    },
}


def test_flat_simulator_event_passes_through_unchanged() -> None:
    """One code path serves both callers, so the flat shape must be untouched."""
    flat = {"event": "payment.failed", "amount": 100, "customer_id": "cust_x"}
    assert normalize_razorpay_event(flat) == flat
    assert is_razorpay_envelope(flat) is False


def test_envelope_is_flattened_to_the_keys_the_agent_reads() -> None:
    result = normalize_razorpay_event(PAYMENT_FAILED)

    assert result["event"] == "payment.failed"
    # `detect.extract_amount_at_risk` reads exactly this key.
    assert result["amount"] == 299900
    # The case builder and the merchant resolver read exactly this one.
    assert result["customer_id"] == "cust_suresh_iyer"
    # The network aggregator reads these two.
    assert result["bank"] == "HDFC"
    assert result["method"] == "card"
    assert result["payment_id"] == "pay_TEST123"
    assert result["customer_email"] == "suresh@test.com"
    assert result["customer_phone"] == "+919812345001"
    assert result["notes"] == {"case_id": "case-abc"}


def test_original_envelope_is_preserved() -> None:
    """The flat view is lossy by design; the raw body stays available."""
    result = normalize_razorpay_event(PAYMENT_FAILED)
    assert result["razorpay"] == PAYMENT_FAILED
    assert result["source"] == "razorpay_webhook"


def test_normalised_envelope_feeds_the_real_detect_step() -> None:
    """The point of the whole adaptation layer, asserted end to end."""
    from app.agent.steps.detect import detect_playbook, extract_amount_at_risk

    result = normalize_razorpay_event(PAYMENT_FAILED)
    assert detect_playbook(result["event"]) == "failed_payment"
    assert extract_amount_at_risk(result, result["event"]) == 299900


def test_subscription_entity_wins_shared_keys_over_payment() -> None:
    """A subscription webhook carries both entities; the subscription is the
    more specific fact and must own the ids they share."""
    envelope = {
        "event": "subscription.charged",
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_REAL",
                    "customer_id": "cust_from_subscription",
                    "plan_id": "plan_XYZ",
                    "status": "active",
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_REAL",
                    "amount": 299900,
                    "customer_id": "cust_from_payment",
                    "method": "upi",
                }
            },
        },
    }
    result = normalize_razorpay_event(envelope)

    assert result["subscription_id"] == "sub_REAL"
    assert result["payment_id"] == "pay_REAL"
    assert result["customer_id"] == "cust_from_subscription"
    # The payment still contributes what the subscription does not carry.
    assert result["amount"] == 299900
    assert result["method"] == "upi"


# ─────────────────────────────────────────────────────────────────────
# The endpoint's two authenticators
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def webhook_client(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """The app with a webhook secret configured and the database faked.

    `get_service_client` is patched at the module the endpoint imports it into,
    not at its source: the endpoint holds a reference from import time, so
    patching `app.db` would leave the real one in place.
    """
    from collections.abc import Iterator

    from fastapi.testclient import TestClient

    from app.api import events
    from app.main import app
    from tests.simulator.conftest import MERCHANT_ID
    from tests.simulator.fake_supabase import FakeSupabase

    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)

    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_MERCHANT_ID", MERCHANT_ID)
    # Settings are an lru_cache singleton, so the new env only lands if the
    # cache is dropped.
    from app.config import get_settings

    get_settings.cache_clear()

    monkeypatch.setattr(events, "get_service_client", lambda: fake)
    # The agent loop is a background task; these tests are about the gate in
    # front of it, and running it would need every table the loop touches.
    monkeypatch.setattr(events, "process_event", lambda *a, **k: None)

    def _iter() -> "Iterator[tuple[TestClient, FakeSupabase]]":
        with TestClient(app) as test_client:
            yield test_client, fake

    gen = _iter()
    yield next(gen)
    get_settings.cache_clear()


def test_no_token_and_no_signature_is_401(webhook_client) -> None:  # type: ignore[no-untyped-def]
    client, _ = webhook_client
    response = client.post("/api/events/webhook", json=PAYMENT_FAILED)

    assert response.status_code == 401


def test_invalid_signature_is_400(webhook_client) -> None:  # type: ignore[no-untyped-def]
    client, _ = webhook_client
    body = json.dumps(PAYMENT_FAILED).encode()

    response = client.post(
        "/api/events/webhook",
        content=body,
        headers={
            "X-Razorpay-Signature": sign(body, "wrong-secret"),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 400
    assert "signature" in response.json()["error"]["message"].lower()


def test_valid_signature_is_accepted_without_a_token(webhook_client) -> None:  # type: ignore[no-untyped-def]
    """The path a real Razorpay webhook takes. It carries no bearer token."""
    client, fake = webhook_client
    body = json.dumps(PAYMENT_FAILED).encode()

    response = client.post(
        "/api/events/webhook",
        content=body,
        headers={"X-Razorpay-Signature": sign(body), "Content-Type": "application/json"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"

    # Stored flattened, so the agent's steps can read it.
    events_stored = fake.rows("events")
    assert len(events_stored) == 1
    assert events_stored[0]["event_type"] == "payment.failed"
    assert events_stored[0]["payload"]["amount"] == 299900


def test_tampered_body_with_a_valid_signature_for_the_original_is_400(
    webhook_client,  # type: ignore[no-untyped-def]
) -> None:
    """The attack the signature exists to stop: replay a real body with the
    amount changed, or swap `payment.failed` for `payment.captured`."""
    client, fake = webhook_client
    original = json.dumps(PAYMENT_FAILED).encode()
    signature = sign(original)

    forged = json.loads(original)
    forged["event"] = "payment.captured"
    response = client.post(
        "/api/events/webhook",
        content=json.dumps(forged).encode(),
        headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert fake.rows("events") == []
