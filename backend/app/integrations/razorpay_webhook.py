"""Inbound webhook authentication.

Razorpay signs every webhook body with HMAC-SHA256 under a secret set in its
dashboard, and puts the hex digest in ``X-Razorpay-Signature``. Verifying it is
what makes the endpoint safe to expose publicly: without it, anyone who learns
the URL can post ``payment.captured`` and close cases as recovered.

Two details that are easy to get wrong and are the whole point of this module:

**The signature covers the raw bytes, not the parsed JSON.** ``json.dumps`` of a
parsed body re-orders nothing but does change whitespace, and any difference at
all produces a different digest. So the endpoint must read ``await
request.body()`` and hash that, before anything parses it.

**The comparison is ``compare_digest``, not ``==``.** String equality returns as
soon as two bytes differ, and the time it takes is a measurement of how many
leading bytes were right — enough, over many attempts, to reconstruct a valid
signature one byte at a time.
"""

import hashlib
import hmac
from typing import Any

from app.logging import get_logger

log = get_logger(__name__)

#: The header Razorpay puts its digest in.
SIGNATURE_HEADER = "X-Razorpay-Signature"


def verify_razorpay_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """Whether ``signature`` is Razorpay's HMAC-SHA256 of ``payload_body``.

    Returns ``False`` rather than raising on a malformed signature or an empty
    secret. A caller deciding whether to accept a request wants one boolean, and
    an exception here would have to be caught and turned into that boolean at
    every call site anyway.
    """
    if not secret or not signature:
        return False

    expected = hmac.new(secret.encode("utf-8"), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


# ─────────────────────────────────────────────────────────────────────
# Envelope normalisation
# ─────────────────────────────────────────────────────────────────────

#: Entity keys inside ``payload``, in the order they are worth reading. A
#: subscription webhook carries both a subscription and the payment that failed
#: against it; the subscription is the more specific fact, so it wins the keys
#: they share and the payment still contributes its own.
_ENTITY_ORDER = ("subscription", "invoice", "order", "payment_link", "payment")

#: Razorpay entity field → the flat key the agent's steps already read. This map
#: is the entire adaptation layer: `detect`, `execute` and the case builder go on
#: reading `amount`, `customer_id`, `bank` and `method` exactly as the simulator
#: emits them, and neither knows a real webhook has a different shape.
_FIELD_MAP = {
    "amount": "amount",
    "customer_id": "customer_id",
    "email": "customer_email",
    "contact": "customer_phone",
    "method": "method",
    "bank": "bank",
    "wallet": "wallet",
    "vpa": "vpa",
    "error_code": "error_code",
    "error_description": "error_description",
    "error_reason": "error_reason",
    "plan_id": "plan_id",
    "currency": "currency",
    "status": "entity_status",
}


def is_razorpay_envelope(body: dict[str, Any]) -> bool:
    """Whether ``body`` is a real Razorpay webhook rather than a simulator event.

    Razorpay wraps entities in ``{"payload": {"<entity>": {"entity": {...}}}}``.
    The simulator posts the flat shape the agent's steps read directly, so the
    presence of that nesting is what tells the two apart — and it is a shape
    check rather than a header check because the normaliser has to be correct for
    a replayed body with no headers at all.
    """
    payload = body.get("payload")
    if not isinstance(payload, dict):
        return False
    return any(
        isinstance(entity, dict) and "entity" in entity for entity in payload.values()
    )


def normalize_razorpay_event(body: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Razorpay webhook envelope into the shape the agent reads.

    Returns the body unchanged when it is not an envelope, so the simulator's
    events pass through untouched and one code path serves both.

    Flattening rather than teaching every step to walk the envelope: `detect`
    reads ``amount``, the case builder reads ``customer_id``, the network
    aggregator reads ``bank`` and ``method``. Pushing the envelope down into
    those would put Razorpay's payload schema in five files instead of one, and
    the simulator would then have to emit the envelope too — which would mean
    the scenarios no longer describe what they test.

    The original envelope is preserved under ``razorpay``. Nothing reads it
    today; it is there because the flattened view is lossy by design, and the
    first question anyone asks of a surprising case is what actually arrived.
    """
    if not is_razorpay_envelope(body):
        return body

    flat: dict[str, Any] = {
        "event": body.get("event", "unknown"),
        "razorpay": body,
        "source": "razorpay_webhook",
    }

    payload = body.get("payload") or {}
    # Least specific first, so a more specific entity overwrites shared keys.
    for entity_key in reversed(_ENTITY_ORDER):
        wrapper = payload.get(entity_key)
        if not isinstance(wrapper, dict):
            continue
        entity = wrapper.get("entity")
        if not isinstance(entity, dict):
            continue

        # The entity's own id, under a name that says which entity it is:
        # `payment_id`, `subscription_id`, `invoice_id`. The agent's metadata
        # already uses `subscription_id`, and this is where it comes from.
        entity_id = entity.get("id")
        if entity_id:
            flat[f"{entity_key}_id"] = entity_id

        for source_field, flat_key in _FIELD_MAP.items():
            value = entity.get(source_field)
            if value not in (None, ""):
                flat[flat_key] = value

        notes = entity.get("notes")
        if isinstance(notes, dict) and notes:
            # Notes are how the agent labels its own payment links, so a
            # captured payment can name the case it settled.
            flat.setdefault("notes", {}).update(notes)

    return flat
