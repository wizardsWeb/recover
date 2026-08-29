"""The execution adapters, real branch and fallback.

What matters here is that the two branches are distinguishable afterwards. A
demo that cannot say which of its sends were real is a demo whose numbers cannot
be checked, so every test below asserts on the adapter name and the ``simulated``
flag as well as on the payload.
"""

from typing import Any

import pytest

from app.agent.steps.execute import (
    PAYMENT_LINK_PLACEHOLDER,
    _dispatch,
    _substitute_payment_link,
    _was_simulated,
)

CASE: dict[str, Any] = {
    "id": "11111111-2222-3333-4444-555555555555",
    "merchant_id": "merchant-1",
    "playbook": "subscription_failure",
    "amount_at_risk_cents": 299900,
    "customer_name": "Suresh Iyer",
    "customer_phone": "+919812345001",
    "customer_email": "suresh@test.com",
    "metadata": {"subscription_id": "sub_REAL123", "bank": "ICICI", "method": "upi"},
}

DECISION: dict[str, Any] = {"action_params": {"channel": "whatsapp"}}


class FakeLinks:
    """Stands in for ``client.payment_link``."""

    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeSubscriptions:
    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self.response = response

    def pending_update(self, subscription_id: str) -> dict[str, Any]:
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeClient:
    def __init__(
        self,
        link_response: dict[str, Any] | Exception | None = None,
        subscription_response: dict[str, Any] | Exception | None = None,
    ) -> None:
        self.payment_link = FakeLinks(
            link_response
            if link_response is not None
            else {"id": "plink_REAL", "short_url": "https://rzp.io/rzp/AbCdEf", "status": "created"}
        )
        self.subscription = FakeSubscriptions(
            subscription_response if subscription_response is not None else {"status": "active"}
        )


# ─────────────────────────────────────────────────────────────────────
# send_payment_link
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_client_falls_back_to_simulation() -> None:
    """The state a deployment with no Razorpay keys is always in."""
    adapter, result = await _dispatch("send_payment_link", CASE, DECISION, "trace", None)

    assert adapter == "razorpay_payment_links_simulated"
    assert result["response_payload"]["simulated"] is True
    assert result["response_payload"]["short_url"].startswith("https://rzp.io/l/plink_sim_")


@pytest.mark.asyncio
async def test_real_client_mints_a_real_link() -> None:
    client = FakeClient()
    adapter, result = await _dispatch("send_payment_link", CASE, DECISION, "trace", client)

    assert adapter == "razorpay_payment_links"
    assert result["response_payload"]["simulated"] is False
    assert result["response_payload"]["short_url"] == "https://rzp.io/rzp/AbCdEf"

    # reference_id is the case id, which is the join payment.captured uses to
    # find this case. Without it the loop does not close.
    sent = client.payment_link.calls[0]
    assert sent["reference_id"] == CASE["id"]
    assert sent["notes"]["case_id"] == CASE["id"]
    assert sent["amount"] == 299900
    # The agent owns messaging, so Razorpay must not also send its own.
    assert sent["notify"] == {"sms": False, "email": False}
    assert sent["reminder_enable"] is False


@pytest.mark.asyncio
async def test_api_failure_degrades_to_simulation_rather_than_raising() -> None:
    """The adapters run in a background task with nobody to catch an exception."""
    client = FakeClient(link_response=RuntimeError("razorpay 502"))
    adapter, result = await _dispatch("send_payment_link", CASE, DECISION, "trace", client)

    assert adapter == "razorpay_payment_links_simulated"
    assert result["response_payload"]["simulated"] is True
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_zero_amount_never_calls_the_api() -> None:
    """Razorpay rejects a zero-amount link, and a case whose amount failed to
    parse is exactly the case that would produce one."""
    client = FakeClient()
    case = {**CASE, "amount_at_risk_cents": 0}
    adapter, result = await _dispatch("send_payment_link", case, DECISION, "trace", client)

    assert client.payment_link.calls == []
    assert adapter == "razorpay_payment_links_simulated"
    assert result["response_payload"]["simulated"] is True


# ─────────────────────────────────────────────────────────────────────
# retry_charge and mandate_reregister
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_charge_records_real_subscription_state() -> None:
    client = FakeClient(subscription_response={"id": "sub_REAL123", "status": "halted"})
    adapter, result = await _dispatch("retry_charge", CASE, DECISION, "trace", client)

    assert adapter == "razorpay_subscriptions"
    assert result["response_payload"]["simulated"] is False
    assert result["response_payload"]["subscription_state"]["status"] == "halted"
    # The instrument the network aggregator reads off this row.
    assert result["request_payload"]["bank"] == "ICICI"
    assert result["request_payload"]["method"] == "upi"


@pytest.mark.asyncio
async def test_retry_charge_without_a_subscription_id_stays_simulated() -> None:
    client = FakeClient()
    case = {**CASE, "metadata": {"bank": "ICICI"}}
    _, result = await _dispatch("retry_charge", case, DECISION, "trace", client)

    assert result["response_payload"]["simulated"] is True
    assert result["response_payload"]["retry_scheduled"] is False


@pytest.mark.asyncio
async def test_mandate_reregister_is_a_labelled_payment_link() -> None:
    """Re-registration is not an API the merchant can call for the customer, so
    the mechanism is a link that says what it is for."""
    client = FakeClient()
    adapter, result = await _dispatch("mandate_reregister", CASE, DECISION, "trace", client)

    assert adapter == "razorpay_payment_links"
    assert client.payment_link.calls[0]["description"] == "Update your payment method"
    assert result["request_payload"]["purpose"] == "mandate_reregistration"
    assert result["response_payload"]["registration_link"] == "https://rzp.io/rzp/AbCdEf"


# ─────────────────────────────────────────────────────────────────────
# Placeholder substitution
# ─────────────────────────────────────────────────────────────────────


def test_placeholder_is_replaced_with_the_minted_url() -> None:
    result = {
        "request_payload": {"body": f"Hi Suresh, pay here: {PAYMENT_LINK_PLACEHOLDER}"},
        "response_payload": {"short_url": "https://rzp.io/rzp/AbCdEf"},
    }
    _substitute_payment_link(result)

    assert result["request_payload"]["body"] == "Hi Suresh, pay here: https://rzp.io/rzp/AbCdEf"
    assert result["response_payload"]["payment_link_url"] == "https://rzp.io/rzp/AbCdEf"


def test_placeholder_is_dropped_when_no_link_was_minted() -> None:
    """A WhatsApp-only arm mints no link. "pay here: [payment link]" reaching a
    customer is worse than a message that offers no link at all."""
    result = {
        "request_payload": {"body": f"Hi Suresh, pay here: {PAYMENT_LINK_PLACEHOLDER}"},
        "response_payload": {},
    }
    _substitute_payment_link(result)

    assert PAYMENT_LINK_PLACEHOLDER not in result["request_payload"]["body"]
    assert result["request_payload"]["body"] == "Hi Suresh, pay here:"


def test_body_without_a_placeholder_is_untouched() -> None:
    result = {
        "request_payload": {"body": "Hi Suresh, your renewal failed."},
        "response_payload": {"short_url": "https://rzp.io/rzp/AbCdEf"},
    }
    _substitute_payment_link(result)

    assert result["request_payload"]["body"] == "Hi Suresh, your renewal failed."


@pytest.mark.parametrize(
    ("payload", "expected"),
    [({}, True), ({"simulated": True}, True), ({"simulated": False}, False)],
)
def test_missing_flag_reports_simulated(payload: dict[str, Any], expected: bool) -> None:
    """Under-claiming is the safe direction."""
    assert _was_simulated({"response_payload": payload}) is expected
