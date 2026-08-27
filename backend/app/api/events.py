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

Phase 4 authenticates the webhook with the merchant's own bearer token, which is
right for the simulator and for a merchant posting test events. A real Razorpay
integration also needs ``X-Razorpay-Signature`` HMAC verification before this
endpoint can be exposed publicly; that is called out here so it cannot be
mistaken for done.
"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.agent.core import process_event
from app.db import get_service_client
from app.deps import CurrentUserId, UserSupabase
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
    payload: Annotated[dict[str, Any], Field(description="Razorpay-shaped event payload")],
    background_tasks: BackgroundTasks,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> WebhookResponse:
    """Store an inbound event and hand it to the agent in the background."""
    event_row: dict[str, Any] = {
        "merchant_id": user_id,
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
                .eq("merchant_id", user_id)
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

    # The service client, not `supabase` — see the module docstring.
    background_tasks.add_task(process_event, event_id, user_id, get_service_client())

    return WebhookResponse(
        event_id=event_id,
        status="accepted",
        message="Event received — agent processing in background",
    )
