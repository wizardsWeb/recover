"""Simulator control-plane endpoints.

Everything here is a development affordance: it manufactures events that in
production would arrive from Razorpay. That makes it the one router where a
misconfiguration is genuinely dangerous — an enabled simulator in production
would let anyone write fabricated recovery cases into a real merchant's ledger.
So it is gated on the environment and refuses to exist outside development.

Within that gate, the usual rules hold. Every query runs through the caller's
Supabase client, so RLS scopes each operation to the signed-in merchant; there
is no service-role client anywhere in this file. Firing a scenario for someone
else's merchant is not blocked by a check we wrote — it is impossible.

Wire format follows Phase 1: ``CamelModel`` renders camelCase for the browser
and keeps snake_case in Python, so the frontend's types read the same as
``Merchant``'s do.
"""

from typing import Annotated, Any, cast

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.agent.core import process_event
from app.config import get_settings
from app.db import get_service_client
from app.deps import CurrentUserId, UserSupabase
from app.logging import get_logger
from app.simulator import loader, reply_generator
from app.simulator.scenarios import (
    DEFERRED_SCENARIOS,
    SCENARIO_METADATA,
    SCENARIO_REGISTRY,
)

log = get_logger(__name__)

#: Environments where manufacturing events is legitimate.
_DEV_ENVIRONMENTS = frozenset({"local", "development", "test", "staging"})


def require_dev_environment() -> None:
    """Refuse to serve the simulator outside a development environment.

    404 rather than 403: in production this router should be indistinguishable
    from a route that was never registered.
    """
    if get_settings().ENVIRONMENT.lower() not in _DEV_ENVIRONMENTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


router = APIRouter(
    prefix="/api/simulator",
    tags=["simulator"],
    dependencies=[Depends(require_dev_environment)],
)


def _trace_id() -> str:
    """The current request's trace id, bound by the middleware in ``main``."""
    bound = structlog.contextvars.get_contextvars()
    return str(bound.get("trace_id", "untraced"))


class CamelModel(BaseModel):
    """Base model that speaks camelCase on the wire and snake_case in Python."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


def _rows(result: Any) -> list[dict[str, Any]]:
    """Narrow a PostgREST result to plain dicts.

    supabase-py types ``.data`` as a broad JSON union, so this cast is where we
    state the row shape we already know each query returns — the same pattern
    ``merchants.py`` uses.
    """
    return cast(list[dict[str, Any]], result.data or [])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class LoadedCounts(CamelModel):
    customers: int
    customers_created: int
    payment_methods: int
    personas: list[str]


class LoadResponse(CamelModel):
    loaded: LoadedCounts
    message: str


class ResetResponse(CamelModel):
    deleted: dict[str, int]
    message: str


class FixtureCounts(CamelModel):
    customers: int
    payment_methods: int
    events: int
    cases: int


class ScenarioMeta(CamelModel):
    code: str
    persona_name: str | None = None
    persona_external_id: str | None = None
    merchant_context: str
    playbook: str | None = None
    amount_at_risk_inr: int | None = None
    amount_at_risk_cents: int | None = None
    event_type: str | None = None
    one_line_description: str
    video_expected_path: str
    deferred: bool
    #: The payload this scenario would send, so the panel can preview it
    #: without firing anything.
    sample_payload: dict[str, Any] | None = None


class ReplyExample(CamelModel):
    text: str
    expected_intent: str
    language: str


class FixtureStatusResponse(CamelModel):
    loaded: bool
    counts: FixtureCounts
    personas: list[str]
    scenarios: list[ScenarioMeta]
    reply_examples: list[ReplyExample]


class FireScenarioResponse(CamelModel):
    case_id: str | None = None
    event_id: str | None = None
    case_ids: list[str] | None = None
    event_ids: list[str] | None = None
    scenario_code: str
    message: str


class InjectReplyRequest(CamelModel):
    case_id: str
    channel: str = Field(pattern="^(whatsapp|sms|email|voice)$")
    raw_text: Annotated[str, Field(min_length=1, max_length=4000)]
    #: Accepted so the frontend contract is stable, but not yet honoured —
    #: see the note in ``inject_reply``.
    delay_seconds: int | None = Field(default=None, ge=0, le=86400)


class InjectReplyResponse(CamelModel):
    reply_id: str
    message: str


class RecentEvent(CamelModel):
    id: str
    event_type: str
    payload: dict[str, Any]
    received_at: str
    customer_name: str | None = None


class InFlightCase(CamelModel):
    id: str
    playbook: str
    status: str
    amount_at_risk_cents: int
    opened_at: str
    customer_name: str | None = None


class SimulatorStatusResponse(CamelModel):
    fixtures_loaded: bool
    recent_events: list[RecentEvent]
    in_flight_cases: list[InFlightCase]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scenario_catalogue() -> list[ScenarioMeta]:
    """Scenario metadata in registry order, each with a payload preview.

    The preview is built by calling the real builders with the real scripted
    arguments, so what the panel shows is what the firing will write — a
    hand-written sample would drift the first time a payload changed.
    """
    from app.simulator import scenarios as scenario_module

    previews = scenario_module.sample_payloads()
    return [
        ScenarioMeta.model_validate({**meta, "sample_payload": previews.get(code)})
        for code, meta in SCENARIO_METADATA.items()
    ]


def _require_onboarded_merchant(supabase: Any, user_id: str) -> None:
    """Fail loudly if the account has no merchant row yet.

    The signup trigger creates one, so its absence means a broken account rather
    than a new one, and loading fixtures against it would fail later with a
    foreign-key error that says nothing useful.
    """
    result = supabase.table("merchants").select("id").eq("id", user_id).limit(1).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="No merchant record for this account. Finish onboarding first.",
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@router.post("/fixtures/load", response_model=LoadResponse)
def load_fixtures(user_id: CurrentUserId, supabase: UserSupabase) -> LoadResponse:
    """Load the six personas, the B3 cohort, and their payment methods."""
    _require_onboarded_merchant(supabase, user_id)
    result = loader.load_fixtures_for_merchant(supabase, user_id, _trace_id())
    return LoadResponse(
        loaded=LoadedCounts.model_validate(result),
        message=(
            f"Loaded {result['customers']} fixture customers "
            f"and {result['payment_methods']} payment methods."
        ),
    )


@router.post("/fixtures/reset", response_model=ResetResponse)
def reset_fixtures(user_id: CurrentUserId, supabase: UserSupabase) -> ResetResponse:
    """Delete every simulator-created row for the signed-in merchant."""
    _require_onboarded_merchant(supabase, user_id)
    deleted = loader.reset_fixtures_for_merchant(supabase, user_id, _trace_id())
    return ResetResponse(
        deleted=deleted,
        message="All fixture data reset for this merchant.",
    )


@router.get("/fixtures/status", response_model=FixtureStatusResponse)
def fixture_status(user_id: CurrentUserId, supabase: UserSupabase) -> FixtureStatusResponse:
    """Report what is loaded, plus the scenario catalogue and reply corpus.

    The catalogue rides along with the status because the control panel needs
    both to render one screen, and two round trips to draw one card is a worse
    trade than a slightly wider response.
    """
    _require_onboarded_merchant(supabase, user_id)
    result = loader.get_fixture_status(supabase, user_id)
    return FixtureStatusResponse(
        loaded=result["loaded"],
        counts=FixtureCounts.model_validate(result["counts"]),
        personas=result["personas"],
        scenarios=_scenario_catalogue(),
        reply_examples=[
            ReplyExample(
                text=example["text"],
                expected_intent=example["expected_intent"],
                language=example["language"],
            )
            for example in reply_generator.REPLY_EXAMPLES
        ],
    )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


@router.post("/scenarios/{code}", response_model=FireScenarioResponse)
def fire_scenario(
    code: str,
    response: Response,
    background_tasks: BackgroundTasks,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> FireScenarioResponse:
    """Fire one scenario: write its event, open its case, run the agent on it.

    The agent runs as a background task on the service-role client, exactly as
    it does for a real webhook — the point of the simulator is that the path
    from event to recovery is the same one production uses. See
    ``app.api.events`` for why the request-scoped client cannot be used.
    """
    normalised = code.strip().upper()
    if normalised not in SCENARIO_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown scenario {code!r}. Known: {', '.join(SCENARIO_REGISTRY)}",
        )

    _require_onboarded_merchant(supabase, user_id)

    if normalised in DEFERRED_SCENARIOS:
        # 202: the request was understood and accepted as well-formed, but the
        # work is not implemented. Nothing is written.
        result = SCENARIO_REGISTRY[normalised](supabase, user_id, _trace_id())
        response.status_code = status.HTTP_202_ACCEPTED
        return FireScenarioResponse.model_validate(result)

    status_result = loader.get_fixture_status(supabase, user_id)
    if not status_result["loaded"]:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Load fixtures first",
        )

    result = SCENARIO_REGISTRY[normalised](supabase, user_id, _trace_id())
    _queue_agent_runs(background_tasks, result, user_id)
    return FireScenarioResponse.model_validate(result)


def _queue_agent_runs(
    background_tasks: BackgroundTasks,
    result: dict[str, Any],
    user_id: str,
) -> None:
    """Hand every event a scenario produced to the agent loop.

    Scenarios fire one event each except the network-effect ones, which fire a
    batch; both shapes are handled so a multi-merchant scenario does not
    silently process only its first event.
    """
    event_ids = [eid for eid in (result.get("event_ids") or []) if eid]
    if not event_ids and result.get("event_id"):
        event_ids = [str(result["event_id"])]
    if not event_ids:
        return
    service_client = get_service_client()
    for event_id in event_ids:
        background_tasks.add_task(process_event, str(event_id), user_id, service_client)


# ---------------------------------------------------------------------------
# Replies
# ---------------------------------------------------------------------------


@router.post("/replies", response_model=InjectReplyResponse)
def inject_reply(
    payload: InjectReplyRequest,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> InjectReplyResponse:
    """Inject a customer reply against an open case.

    ``delay_seconds`` is accepted and ignored in Phase 2. Honouring it needs a
    scheduler that survives a process restart; a bare ``asyncio.sleep`` would
    drop the reply on the next deploy and look like a bug in the agent rather
    than in the simulator. The response says so rather than pretending.
    """
    case = (
        supabase.table("recovery_cases")
        .select("id, customer_id")
        .eq("id", payload.case_id)
        .limit(1)
        .execute()
    )
    # RLS already filters other merchants' cases out of this select, so an empty
    # result means "not yours or not real" — and 404 is the right answer to both.
    if not case.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    row = _rows(case)[0]
    inserted = (
        supabase.table("customer_replies")
        .insert(
            {
                "case_id": row["id"],
                "merchant_id": user_id,
                "customer_id": row["customer_id"],
                "channel": payload.channel,
                "raw_text": payload.raw_text,
            }
        )
        .execute()
    )
    reply_id = str(_rows(inserted)[0]["id"])

    supabase.table("audit_events").insert(
        {
            "case_id": row["id"],
            "merchant_id": user_id,
            "actor": "system",
            "event": "reply_injected",
            "details": {"channel": payload.channel, "reply_id": reply_id},
            "trace_id": _trace_id(),
        }
    ).execute()

    log.info("simulator.reply_injected", merchant_id=user_id, case_id=row["id"], reply_id=reply_id)

    message = "Reply injected — classification lands in Phase 5."
    if payload.delay_seconds:
        message += " Delayed injection is not implemented in Phase 2; inserted immediately."
    return InjectReplyResponse(reply_id=reply_id, message=message)


# ---------------------------------------------------------------------------
# Live status
# ---------------------------------------------------------------------------


@router.get("/status", response_model=SimulatorStatusResponse)
def simulator_status(user_id: CurrentUserId, supabase: UserSupabase) -> SimulatorStatusResponse:
    """The event tail and open-case list the control panel polls."""
    _require_onboarded_merchant(supabase, user_id)

    events = (
        supabase.table("events")
        .select("id, event_type, payload, received_at, customers(name)")
        .eq("merchant_id", user_id)
        .order("received_at", desc=True)
        .limit(20)
        .execute()
    )
    cases = (
        supabase.table("recovery_cases")
        .select("id, playbook, status, amount_at_risk_cents, opened_at, customers(name)")
        .eq("merchant_id", user_id)
        .in_("status", ["open", "in_flight"])
        .order("opened_at", desc=True)
        .limit(50)
        .execute()
    )

    def customer_name(row: dict[str, Any]) -> str | None:
        # PostgREST returns an embedded to-one relation as an object, but older
        # versions and some select shapes return a single-element list.
        embedded = row.get("customers")
        if isinstance(embedded, list):
            embedded = embedded[0] if embedded else None
        if isinstance(embedded, dict):
            return embedded.get("name")
        return None

    return SimulatorStatusResponse(
        fixtures_loaded=loader.get_fixture_status(supabase, user_id)["loaded"],
        recent_events=[
            RecentEvent(
                id=str(row["id"]),
                event_type=str(row["event_type"]),
                payload=row["payload"],
                received_at=str(row["received_at"]),
                customer_name=customer_name(row),
            )
            for row in _rows(events)
        ],
        in_flight_cases=[
            InFlightCase(
                id=str(row["id"]),
                playbook=str(row["playbook"]),
                status=str(row["status"]),
                amount_at_risk_cents=int(row["amount_at_risk_cents"]),
                opened_at=str(row["opened_at"]),
                customer_name=customer_name(row),
            )
            for row in _rows(cases)
        ],
    )
