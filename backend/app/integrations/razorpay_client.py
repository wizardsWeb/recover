"""Razorpay REST API, wrapped for the agent's execution adapters.

Three things this module is responsible for, and they are the reason it exists
rather than the adapters calling the SDK directly:

**It never raises.** Every call returns a dict, and on any failure that dict is
a simulated response carrying ``simulated: True``. The adapters run inside a
background task with no caller to surface an exception to, and a recovery case
that dies because Razorpay returned a 502 is a case nobody recovers. The
alternative — try/except at nine call sites — is the version where the eighth
one is forgotten.

**It never blocks the event loop.** The official ``razorpay`` SDK is
synchronous: it is ``requests`` underneath, so a payment-link creation is a
blocking socket read of a few hundred milliseconds. Awaiting that on the loop
thread would stall every other request in the process, so each call is handed to
``asyncio.to_thread``. The functions are ``async`` because of that, not because
the SDK is.

**It never logs a secret.** Only the key id — which is public, it ships in
checkout pages — ever reaches a log line. The secret is read from settings and
passed to the SDK, and that is the whole of its travel.

Absent keys are a supported state, not an error. ``get_razorpay_client``
returns ``None``, every adapter takes its simulated branch, and the product
works end to end with no Razorpay account at all.
"""

import asyncio
import uuid
from typing import Any

import razorpay

from app.config import get_settings
from app.logging import get_logger

log = get_logger(__name__)

#: Marks a response this module invented because the real call was impossible.
#: Read by the adapters, which copy it onto ``execution_attempts.simulated`` —
#: which is what keeps a simulated send from being reported as a real one.
SIMULATED = "simulated"


def get_razorpay_client() -> razorpay.Client | None:
    """A configured client, or ``None`` when the keys are not set.

    ``None`` is the signal every adapter branches on. Constructing a client with
    empty credentials would be worse than returning nothing: it would succeed,
    and then fail on the first request with a 401 that reads like a revoked key
    rather than like a missing one.
    """
    settings = get_settings()
    if not settings.razorpay_configured:
        return None
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def _simulated(reason: str, **extra: Any) -> dict[str, Any]:
    """A response shaped like Razorpay's, marked as not being one."""
    return {"status": SIMULATED, SIMULATED: True, "simulated_reason": reason, **extra}


def simulated_payment_link() -> dict[str, Any]:
    """The payment-link response used when no real link could be minted."""
    link_id = f"plink_sim_{uuid.uuid4().hex[:8]}"
    return {
        "id": link_id,
        "short_url": f"https://rzp.io/l/{link_id}",
        "status": SIMULATED,
        SIMULATED: True,
    }


async def create_payment_link(
    client: razorpay.Client,
    *,
    amount_cents: int,
    customer_name: str,
    customer_phone: str | None = None,
    customer_email: str | None = None,
    description: str = "Payment recovery",
    expire_hours: int = 24,
    reference_id: str | None = None,
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a Razorpay Payment Link and return ``{id, short_url, status}``.

    ``amount`` goes to Razorpay in paise, which is what the caller already has —
    every money column in this system is paise, so there is no conversion here
    and therefore no place for a hundred-fold error to enter.

    ``reference_id`` is the case id. It is the join that lets the
    ``payment.captured`` webhook find the case this link was minted for without
    a lookup table, and Razorpay enforces its uniqueness — which makes a
    duplicate link for one case an error from the provider rather than a second
    link the customer might also pay.

    ``notify`` is off and ``reminder_enable`` is false on purpose: the agent owns
    when and on which channel a customer is contacted, and Razorpay's own
    reminders would send messages the guardrail never cleared and the audit trail
    never recorded.
    """
    payload: dict[str, Any] = {
        "amount": int(amount_cents),
        "currency": "INR",
        "description": description[:255],
        "expire_by": _expiry_epoch(expire_hours),
        "reference_id": reference_id or uuid.uuid4().hex,
        "customer": {"name": customer_name or "Customer"},
        # See the docstring: the agent, not Razorpay, decides who gets messaged.
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "notes": notes or {},
    }
    if customer_phone:
        payload["customer"]["contact"] = customer_phone
    if customer_email:
        payload["customer"]["email"] = customer_email

    try:
        response = await asyncio.to_thread(client.payment_link.create, payload)
    except Exception as exc:  # noqa: BLE001 - see the module docstring
        log.warning("razorpay_payment_link_failed", error=str(exc), amount_cents=amount_cents)
        return simulated_payment_link()

    link = {
        "id": str(response.get("id", "")),
        "short_url": str(response.get("short_url", "")),
        "status": str(response.get("status", "created")),
        SIMULATED: False,
    }
    log.info("razorpay_payment_link_created", link_id=link["id"], status=link["status"])
    return link


async def retry_subscription_charge(
    client: razorpay.Client,
    subscription_id: str,
) -> dict[str, Any]:
    """Ask Razorpay what a subscription's next charge looks like.

    This reads ``pending_update`` rather than forcing a charge, and the
    distinction matters. Razorpay's API has no "retry this failed charge now"
    call — a subscription retries on its own schedule — so the honest thing an
    agent can do is inspect the pending state and report it. Claiming to have
    triggered a retry would be the one line in the audit trail that describes an
    API call nobody can make.

    The customer-facing recovery is the payment link the same decision mints;
    this call is what makes the timeline's subscription state real rather than
    invented.
    """
    if not subscription_id or subscription_id.startswith(("sub_unknown", "mand_")):
        return _simulated("no_subscription_id", subscription_id=subscription_id)

    try:
        response = await asyncio.to_thread(client.subscription.pending_update, subscription_id)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "razorpay_subscription_pending_update_failed",
            subscription_id=subscription_id,
            error=str(exc),
        )
        return _simulated("api_error", subscription_id=subscription_id)

    log.info("razorpay_subscription_inspected", subscription_id=subscription_id)
    return {**dict(response), SIMULATED: False}


async def fetch_subscription(client: razorpay.Client, subscription_id: str) -> dict[str, Any]:
    """The subscription's current state — status, charge dates, paid count."""
    try:
        response = await asyncio.to_thread(client.subscription.fetch, subscription_id)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "razorpay_subscription_fetch_failed", subscription_id=subscription_id, error=str(exc)
        )
        return _simulated("api_error", subscription_id=subscription_id)
    return {**dict(response), SIMULATED: False}


async def cancel_subscription(client: razorpay.Client, subscription_id: str) -> dict[str, Any]:
    """Cancel a subscription at the end of its current cycle.

    ``cancel_at_cycle_end`` rather than an immediate cancellation: a customer who
    has paid for this month keeps this month. An agent that cut service the
    moment it read a churn signal would be taking money for a period it then
    refused to serve.
    """
    try:
        response = await asyncio.to_thread(
            client.subscription.cancel, subscription_id, {"cancel_at_cycle_end": 1}
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "razorpay_subscription_cancel_failed",
            subscription_id=subscription_id,
            error=str(exc),
        )
        return _simulated("api_error", subscription_id=subscription_id)

    log.info("razorpay_subscription_cancelled", subscription_id=subscription_id)
    return {**dict(response), SIMULATED: False}


async def fetch_payment(client: razorpay.Client, payment_id: str) -> dict[str, Any]:
    """One payment's status, amount and method.

    Used to confirm a ``payment.captured`` webhook against Razorpay itself
    before a case is closed on the strength of it. The signature proves the
    message came from Razorpay; this proves the payment is still captured and
    was not refunded between the webhook being queued and us reading it.
    """
    try:
        response = await asyncio.to_thread(client.payment.fetch, payment_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("razorpay_payment_fetch_failed", payment_id=payment_id, error=str(exc))
        return _simulated("api_error", payment_id=payment_id)
    return {**dict(response), SIMULATED: False}


def _expiry_epoch(hours: int) -> int:
    """Unix seconds ``hours`` from now.

    Razorpay rejects an ``expire_by`` less than fifteen minutes out, so short
    windows are floored rather than passed through to a 400 the adapter would
    have to interpret.
    """
    from datetime import UTC, datetime, timedelta

    floor = timedelta(minutes=16)
    delta = max(timedelta(hours=hours), floor)
    return int((datetime.now(UTC) + delta).timestamp())
