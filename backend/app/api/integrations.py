"""Integration status, for the settings screen.

Answers one question — *is this wired up* — and deliberately cannot answer any
other. The response carries booleans, a mode, and a masked key id. It never
carries a secret, and there is no route here that could, because the only
reliable way to keep a secret out of a browser is for nothing to be able to send
it.

The key id is public by design: it ships in every Razorpay checkout page. It is
still masked to its last four characters, because "which key is this" is a
question a merchant asks and "what is the whole key" is not.
"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.config import get_settings
from app.deps import CurrentUserId

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class RazorpayStatus(CamelModel):
    """What is configured, never what it is configured to."""

    #: Whether outbound API calls are possible at all.
    api_configured: bool
    #: Whether inbound webhooks are signature-verified. False means the endpoint
    #: accepts anything that reaches it, which is worth saying out loud.
    webhook_verified: bool
    #: ``test``, ``live`` or ``unconfigured`` — read from the key's own prefix
    #: rather than from the deployment environment, because those two disagreeing
    #: is exactly the situation worth surfacing.
    mode: str
    #: ``rzp_test_••••1234``, or an empty string.
    key_id_masked: str
    #: Which adapters make real calls in this configuration.
    live_adapters: list[str]


#: Adapters that call Razorpay when keys are present. The messaging adapters are
#: absent on purpose: WhatsApp, SMS and email have no provider wired, and listing
#: them here would let the settings screen imply a real send.
_RAZORPAY_ADAPTERS = ["Payment Links", "Subscriptions", "Payment fetch"]


def _mask(key_id: str) -> str:
    """``rzp_test_AbCdEf1234`` -> ``rzp_test_••••1234``."""
    if not key_id:
        return ""
    prefix, separator, _ = key_id.rpartition("_")
    tail = key_id[-4:]
    return f"{prefix}{separator}{'•' * 4}{tail}" if separator else f"{'•' * 4}{tail}"


def _mode(key_id: str) -> str:
    if key_id.startswith("rzp_test_"):
        return "test"
    if key_id.startswith("rzp_live_"):
        return "live"
    return "unconfigured"


@router.get("/razorpay", response_model=RazorpayStatus)
async def razorpay_status(_: CurrentUserId) -> RazorpayStatus:
    """Whether the Razorpay integration is wired, from the server's own settings.

    Authenticated: this is not a secret, but it describes a deployment's
    configuration and there is no reason for it to be public.
    """
    settings = get_settings()
    configured = settings.razorpay_configured
    return RazorpayStatus(
        api_configured=configured,
        webhook_verified=bool(settings.RAZORPAY_WEBHOOK_SECRET),
        mode=_mode(settings.RAZORPAY_KEY_ID),
        key_id_masked=_mask(settings.RAZORPAY_KEY_ID),
        live_adapters=_RAZORPAY_ADAPTERS if configured else [],
    )
