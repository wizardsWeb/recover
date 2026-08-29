"""Webhook ingestion.

One endpoint, and the whole design is in how it answers. A payment processor
retries any webhook it does not get a fast success for, so the handler stores
the event, returns 202, and does the thinking afterwards. The agent loop takes
seconds; a webhook that waited for it would be retried, and a retried webhook
would open a second recovery case against the same customer.

**Why the background task gets the service-role client.** The dependency-injected
client is authenticated with the caller's JWT, and it is scoped to the request:
by the time a ``BackgroundTask`` runs, the response has been sent and that token
is no longer being refreshed. The loop therefore takes ``get_service_client()``,
which bypasses RLS — safe here because ``merchant_id`` is taken from the verified
token before the task is queued, never from the request body.

**Two authenticators, because there are two legitimate callers.** The simulator
and a merchant posting test events carry a Supabase bearer token. Razorpay
carries an HMAC-SHA256 signature over the raw body and no token at all — so
requiring the token would reject every real webhook before its signature was
ever looked at. A request is accepted if either one satisfies us, and rejected
if neither does.

A signature that is present and *wrong* is a hard 400 even when a valid token
accompanies it. Someone replaying a tampered body while holding a token is not a
case worth being lenient about.

**Resolving the merchant without a JWT.** The token path reads the merchant from
``sub``. The signature path has no token, so it looks the payload's customer up
across merchants and falls back to ``RAZORPAY_WEBHOOK_MERCHANT_ID`` — one
Razorpay account maps to one merchant in this deployment. A multi-tenant one
would key off the account id in the payload instead, and this is the single
place that would change.
"""

import json
from typing import Any, cast

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.agent.core import process_event
from app.config import get_settings
from app.db import get_service_client
from app.deps import OptionalUserId
from app.integrations.razorpay_webhook import (
    SIGNATURE_HEADER,
    normalize_razorpay_event,
    verify_razorpay_signature,
)
from app.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


class CamelModel(BaseModel):
    """Base model that speaks camelCase on the wire and snake_case in Python."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class WebhookResponse(CamelModel):
    event_id: str
    status: str
    message: str


def _rows(result: Any) -> list[dict[str, Any]]:
    """Narrow a PostgREST result to plain dicts."""
    return cast(list[dict[str, Any]], result.data or [])


def _external_customer_id(payload: dict[str, Any]) -> str | None:
    """Pull the merchant's own customer identifier out of a webhook payload.

    Razorpay-shaped payloads carry the merchant's id for the customer
    (``cust_suresh_iyer``), not ours. Three spellings are accepted because the
    scripted scenarios, the simulator and Razorpay itself do not agree.
    """
    value = (
        payload.get("customer_id")
        or payload.get("customer_external_id")
        or payload.get("external_customer_id")
    )
    return str(value) if value else None


@router.post(
    "/webhook",
    response_model=WebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: OptionalUserId,
) -> WebhookResponse:
    """Store an inbound event and hand it to the agent in the background."""
    settings = get_settings()

    # The raw bytes, read before anything parses them. The signature covers
    # exactly these bytes: re-serialising a parsed body changes whitespace, and
    # any difference at all produces a different digest.
    raw_body = await request.body()
    signature = request.headers.get(SIGNATURE_HEADER)

    signature_verified = False
    if signature:
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            # Nothing to check it against. Not a rejection on its own — a caller
            # with a valid token is still welcome — but worth saying loudly,
            # because it means a publicly exposed endpoint is unauthenticated.
            log.warning("webhook_signature_present_but_no_secret_configured")
        elif verify_razorpay_signature(raw_body, signature, settings.RAZORPAY_WEBHOOK_SECRET):
            signature_verified = True
        else:
            log.warning("webhook_signature_invalid")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature",
            )

    if user_id is None and not signature_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook requires a bearer token or a valid Razorpay signature",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        body = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON body",
        ) from exc
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body must be a JSON object",
        )

    # Razorpay nests entities; the simulator posts the flat shape already. After
    # this line neither the agent's steps nor anything below can tell which
    # arrived — see `normalize_razorpay_event`.
    payload = normalize_razorpay_event(body)

    # The signature path has no user client to write with, and no RLS context to
    # write under. It uses the service client, with `merchant_id` resolved below
    # rather than taken from the body — a caller who could name their own
    # merchant_id could write into someone else's account.
    service = get_service_client()
    supabase: Any = service
    if user_id is not None:
        merchant_id = user_id
    else:
        resolved = await _resolve_merchant(service, payload, settings)
        if resolved is None:
            # A genuine Razorpay event we cannot attribute. 202 rather than an
            # error on purpose: Razorpay retries anything that is not a 2xx, and
            # retrying will not make this one attributable.
            log.warning("webhook_merchant_unresolved", event_type=payload.get("event"))
            return WebhookResponse(
                event_id="",
                status="ignored",
                message="No merchant could be resolved for this event",
            )
        merchant_id = resolved

    event_row: dict[str, Any] = {
        "merchant_id": merchant_id,
        "event_type": payload.get("event", "unknown"),
        "payload": payload,
    }

    # Resolving the customer FK is best-effort. An event whose customer we do not
    # recognise is still worth storing — dropping it would lose the only record
    # that the failure happened — so a miss leaves the column null rather than
    # failing the webhook.
    external_id = _external_customer_id(payload)
    if external_id:
        try:
            customer = (
                supabase.table("customers")
                .select("id")
                .eq("merchant_id", merchant_id)
                .eq("external_id", external_id)
                .limit(1)
                .execute()
            )
            if customer.data:
                event_row["customer_id"] = _rows(customer)[0]["id"]
        except Exception as exc:  # noqa: BLE001
            log.warning("webhook_customer_lookup_failed", external_id=external_id, error=str(exc))

    try:
        inserted = supabase.table("events").insert(event_row).execute()
    except Exception as exc:  # noqa: BLE001
        log.error("webhook_event_insert_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Event storage error",
        ) from exc

    if not inserted.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store event",
        )
    event_id = str(_rows(inserted)[0]["id"])

    log.info(
        "webhook_accepted",
        event_id=event_id,
        event_type=event_row["event_type"],
        authenticated_by="signature" if user_id is None else "bearer_token",
    )

    # The service client, not a request-scoped one — see the module docstring.
    background_tasks.add_task(process_event, event_id, merchant_id, get_service_client())

    return WebhookResponse(
        event_id=event_id,
        status="accepted",
        message="Event received — agent processing in background",
    )


async def _resolve_merchant(
    service: Any,
    payload: dict[str, Any],
    settings: Any,
) -> str | None:
    """Which merchant a signature-verified webhook belongs to.

    Customer first, configured fallback second. The customer lookup is the more
    trustworthy of the two — it is derived from the event itself rather than from
    a deployment setting — but it only works from the second event about a given
    customer onwards, which is why there is a fallback at all.

    This query deliberately does not filter by merchant: it is the one read in
    the service that is looking *for* a merchant rather than within one.
    """
    external_id = _external_customer_id(payload)
    if external_id:
        try:
            found = (
                service.table("customers")
                .select("merchant_id")
                .eq("external_id", external_id)
                .limit(1)
                .execute()
            )
            if found.data:
                return str(_rows(found)[0]["merchant_id"])
        except Exception as exc:  # noqa: BLE001
            log.warning("webhook_merchant_lookup_failed", external_id=external_id, error=str(exc))

    return str(settings.RAZORPAY_WEBHOOK_MERCHANT_ID) or None
