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

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, cast

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.agent.causal_dag.seed import seed_causal_dag
from app.agent.core import process_event
from app.agent.playbooks import PLAYBOOK_CONFIGS
from app.config import get_settings
from app.db import get_redis_client, get_service_client
from app.deps import CurrentUserId, UserSupabase
from app.logging import get_logger
from app.ml.network.aggregator import IST, normalise_bank, normalise_method
from app.ml.network.detector import publish_alert
from app.ml.uplift.model import train_uplift_model
from app.simulator import loader, reply_generator
from app.simulator.batch import MAX_CASES, SECONDS_PER_CASE, run_batch
from app.simulator.network_seed import DEFAULT_DAYS, MAX_DAYS, seed_network_stats
from app.simulator.scenarios import (
    DEFERRED_SCENARIOS,
    SCENARIO_METADATA,
    SCENARIO_REGISTRY,
)
from app.simulator.uplift_seed import (
    DEFAULT_HOLDOUT_RATE,
    DEFAULT_TOTAL_CASES,
    MAX_TOTAL_CASES,
    PLAYBOOK_WEIGHTS,
    seed_uplift_history,
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
    #: The demo bandit priors go in with the fixtures — without them every
    #: scenario cold-starts and picks an arm at random.
    bandit_priors_seeded: bool = False
    bandit_prior_rows: int = 0


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


class HoldoutResolveRequest(CamelModel):
    case_id: str
    outcome: str = Field(pattern="^(recovered|not_recovered)$")
    amount_cents: int = Field(default=0, ge=0)


class HoldoutResolveResponse(CamelModel):
    case_id: str
    outcome: str
    amount_cents: int


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
async def load_fixtures(user_id: CurrentUserId, supabase: UserSupabase) -> LoadResponse:
    """Load the six personas, the B3 cohort, their payment methods, and the priors."""
    _require_onboarded_merchant(supabase, user_id)
    result = await loader.load_fixtures_for_merchant(supabase, user_id, _trace_id())
    return LoadResponse(
        loaded=LoadedCounts.model_validate(result),
        message=(
            f"Loaded {result['customers']} fixture customers, "
            f"{result['payment_methods']} payment methods "
            f"and {result['bandit_prior_rows']} bandit priors."
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
        # 202: accepted, but the work does not happen inside this request. B1
        # starts a background batch and hands back its id in `case_id`, so the
        # caller has something to subscribe to; B2 only points at a page, since
        # its numbers are computed on read from the holdout group.
        result = SCENARIO_REGISTRY[normalised](supabase, user_id, _trace_id())
        if normalised == "B1":
            started = _start_batch_run(BatchStartRequest(), background_tasks, user_id, supabase)
            result = {**result, "case_id": started.batch_id}
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


@router.post("/holdout/resolve", response_model=HoldoutResolveResponse)
def resolve_holdout(
    payload: HoldoutResolveRequest,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> HoldoutResolveResponse:
    """Record what happened to a control case.

    In production this is not an endpoint at all — a holdout's outcome is
    observed, by a payment arriving or failing to. There is nothing to observe
    in a simulator, so the outcome is stated instead. It is the only way to
    produce a trained model for the demo, and it is why this lives behind the
    dev-environment gate with the rest of the fabrication tools.

    The case row is updated alongside the holdout row. A recovered control still
    recovered money, and the ROI page's treated-versus-control comparison reads
    recovery from the case table for both groups — leaving the case at zero
    would make every control look like a failure and inflate measured uplift.
    """
    holdout = (
        supabase.table("uplift_holdouts")
        .select("id, case_id")
        .eq("case_id", payload.case_id)
        .limit(1)
        .execute()
    )
    if not _rows(holdout):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No holdout row for that case. Only control cases have outcomes to set.",
        )

    recovered = payload.outcome == "recovered"
    now = datetime.now(UTC).isoformat()

    supabase.table("uplift_holdouts").update(
        {
            "outcome": payload.outcome,
            "outcome_amount_cents": payload.amount_cents if recovered else 0,
            "updated_at": now,
        }
    ).eq("case_id", payload.case_id).execute()

    supabase.table("recovery_cases").update(
        {
            "amount_recovered_cents": payload.amount_cents if recovered else 0,
            "closed_at": now,
            "updated_at": now,
        }
    ).eq("id", payload.case_id).execute()

    log.info(
        "holdout_resolved",
        case_id=payload.case_id,
        outcome=payload.outcome,
        amount_cents=payload.amount_cents,
    )
    return HoldoutResolveResponse(
        case_id=payload.case_id,
        outcome=payload.outcome,
        amount_cents=payload.amount_cents if recovered else 0,
    )


class UpliftSeedRequest(CamelModel):
    """Knobs on the corpus, all optional — the defaults are the demo."""

    total_cases: int = Field(default=DEFAULT_TOTAL_CASES, ge=40, le=MAX_TOTAL_CASES)
    holdout_rate: float = Field(default=DEFAULT_HOLDOUT_RATE, gt=0.0, lt=0.9)
    #: Fixes the draw so a rehearsed demo shows the same numbers twice.
    seed: int | None = Field(default=None)


class SeededPlaybook(CamelModel):
    playbook: str
    status: str
    treated_samples: int = 0
    control_samples: int = 0
    mean_cate: float | None = None


class UpliftSeedResponse(CamelModel):
    cases: int
    treated: int
    controls: int
    customers: int
    models: list[SeededPlaybook]


@router.post("/uplift/seed", response_model=UpliftSeedResponse)
async def seed_uplift(
    payload: UpliftSeedRequest,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> UpliftSeedResponse:
    """Manufacture a treated/control history, then fit a model on it.

    The two halves are one endpoint because neither is useful alone: a corpus
    with no model shows an empty ROI page, and training with nothing to train on
    reports `insufficient_data` four times. Whoever is running the demo wants the
    finished state.

    Seeding and fitting both run in a worker thread. The inserts are blocking
    HTTP calls inside the Supabase client and the fits are CPU-bound sklearn —
    several hundred rows and four models is long enough on the event loop to
    stall every other request on the process.
    """
    summary = await asyncio.to_thread(
        seed_uplift_history,
        supabase,
        user_id,
        total_cases=payload.total_cases,
        holdout_rate=payload.holdout_rate,
        seed=payload.seed,
    )

    models: list[SeededPlaybook] = []
    for playbook in PLAYBOOK_WEIGHTS:
        outcome = await asyncio.to_thread(train_uplift_model, supabase, user_id, playbook)
        models.append(
            SeededPlaybook(
                playbook=playbook,
                status=str(outcome.get("status")),
                treated_samples=int(outcome.get("treated_samples") or 0),
                control_samples=int(outcome.get("control_samples") or 0),
                mean_cate=outcome.get("mean_cate"),
            )
        )

    log.info(
        "uplift_seed_complete",
        merchant_id=user_id,
        **summary,
        statuses=[m.status for m in models],
    )
    return UpliftSeedResponse(**summary, models=models)


# ── Network downtime (B3) ──────────────────────────────────────────────

#: What each severity looks like as a success rate, and the story each tells.
#: Not derived from the z-score bands on purpose — the detector infers severity
#: from a rate, and this is the inverse, so deriving one from the other would
#: make the simulator agree with the detector by construction and prove nothing.
_DOWNTIME_RATES: dict[str, float] = {
    "critical": 0.20,
    "high": 0.41,
    "medium": 0.58,
}

#: Sample size stamped on the manufactured stats row. Comfortably above the
#: detector's `MIN_ALERT_SAMPLES` so the simulated outage is one the real
#: detector would also have called, rather than one only the simulator believes.
_DOWNTIME_SAMPLE_SIZE = 240

#: The rate a bank returns to when the outage lifts. Above the alert's own
#: baseline, so `find_resolved_alerts` would also clear it on the next poll —
#: the scheduled resolution and the real one agree instead of racing.
_RECOVERED_RATE = 0.86

#: Strong references to pending auto-resolution tasks. The event loop holds only
#: a weak reference to a task nobody keeps, so a fire-and-forget timer can be
#: collected mid-sleep. It does not raise; the outage simply never lifts, and
#: the guardrail goes on blocking retries into a bank that came back.
_PENDING_RESOLUTIONS: set[asyncio.Task[None]] = set()


class DowntimeRequest(CamelModel):
    bank: str = Field(min_length=1, max_length=32)
    method: str = Field(min_length=1, max_length=32)
    severity: Literal["medium", "high", "critical"] = "high"
    #: Bounded at both ends: a zero-minute outage resolves before anyone sees
    #: it, and an eight-hour one outlives the process that would have lifted it.
    duration_minutes: int = Field(default=30, ge=1, le=240)


class DowntimeResponse(CamelModel):
    alert_id: str
    bank: str
    method: str
    severity: str
    success_rate: float
    will_resolve_at: str


async def _lift_downtime(
    supabase_client: Any,
    alert_id: str,
    bank: str,
    method: str,
    delay_seconds: float,
) -> None:
    """Wait out the outage, then clear it and say so.

    Everything is suppressed except cancellation. This runs detached from any
    request, so an exception here would surface only as a task-exception warning
    in the logs — and the visible symptom would be an outage that never lifts.
    """
    try:
        await asyncio.sleep(delay_seconds)
        now = datetime.now(UTC).isoformat()

        supabase_client.table("network_alerts").update({"resolved_at": now, "updated_at": now}).eq(
            "id", alert_id
        ).execute()
        _write_network_stat(supabase_client, bank, method, _RECOVERED_RATE)

        await publish_alert(
            get_redis_client(),
            {
                "type": "alert_resolved",
                "alert": {
                    "id": alert_id,
                    "affected_bank": bank,
                    "affected_method": method,
                    "resolved_at": now,
                    "recovered_rate": _RECOVERED_RATE,
                },
            },
        )
        log.info("simulated_downtime_lifted", alert_id=alert_id, bank=bank, method=method)
    except asyncio.CancelledError:
        # Shutdown. The alert stays open in the database, which is the honest
        # state: nothing observed it recovering.
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("simulated_downtime_lift_error", alert_id=alert_id, error=str(exc))


def _write_network_stat(supabase_client: Any, bank: str, method: str, rate: float) -> None:
    """Stamp a reading for this instrument at the current IST hour.

    Written through the same shape the aggregator uses so the heatmap, the
    detector and the resolver all see one kind of row. A simulator that invented
    its own row shape would demo beautifully and diverge from production at the
    first real poll.
    """
    now = datetime.now(UTC)
    payload = {
        "bank": bank,
        "method": method,
        "hour_of_day": datetime.now(IST).hour,
        "day_of_week": datetime.now(IST).weekday(),
        "success_rate": rate,
        "sample_size": _DOWNTIME_SAMPLE_SIZE,
        "window_start": (now - timedelta(minutes=10)).isoformat(),
        "window_end": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    existing = _rows(
        supabase_client.table("network_stats")
        .select("id")
        .eq("bank", bank)
        .eq("method", method)
        .eq("hour_of_day", payload["hour_of_day"])
        .eq("day_of_week", payload["day_of_week"])
        # `window_end`, for the same reason the aggregator uses it: the window
        # trails the reading, so a start-keyed match misses its own row in the
        # first ten minutes of every hour.
        .gte("window_end", now.replace(minute=0, second=0, microsecond=0).isoformat())
        .limit(1)
        .execute()
    )
    if existing:
        supabase_client.table("network_stats").update(payload).eq("id", existing[0]["id"]).execute()
    else:
        supabase_client.table("network_stats").insert(payload).execute()


@router.post("/network/downtime", response_model=DowntimeResponse)
async def simulate_downtime(
    payload: DowntimeRequest,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> DowntimeResponse:
    """Take a bank down for a fixed window — the B3 scenario.

    Writes the same two rows a real detection writes: the alert the guardrail
    blocks on, and the degraded stats reading that justifies it. Both matter.
    An alert with no stats behind it shows a banner and an unexplained heatmap;
    a stats row with no alert degrades the grid and blocks nothing.

    Both writes go through the **service-role** client, like the network seeder
    and unlike everything else in this router. `network_alerts` and
    `network_stats` are global reference tables: their RLS grants authenticated
    users `SELECT` and nothing else, because a merchant has no business writing
    a network-wide outage. The caller's own client is still used to *read* — the
    duplicate-alert check below — so the endpoint reads with exactly the
    privileges the dashboard has.

    The alert is inserted **before** anything is published. The row is what stops
    retries; the Redis message only moves a banner, and publishing first would
    open a window where the dashboard says a bank is down while the agent is
    still retrying into it.
    """
    service = get_service_client()
    bank = normalise_bank(payload.bank)
    method = normalise_method(payload.method)
    rate = _DOWNTIME_RATES[payload.severity]
    now = datetime.now(UTC)
    resolves_at = now + timedelta(minutes=payload.duration_minutes)

    existing = _rows(
        supabase.table("network_alerts")
        .select("id")
        .eq("affected_bank", bank)
        .eq("affected_method", method)
        .is_("resolved_at", "null")
        .limit(1)
        .execute()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{bank} {method} is already in a simulated outage.",
        )

    alert: dict[str, Any] = {
        "alert_type": "downtime",
        "affected_bank": bank,
        "affected_method": method,
        "severity": payload.severity,
        "z_score": None,
        "sample_size": _DOWNTIME_SAMPLE_SIZE,
        "affected_merchants_count": _network_merchant_count(service),
        "network_wide_success_rate": rate,
        "baseline_rate": 0.82,
        "detected_at": now.isoformat(),
        "resolved_at": None,
        "metadata": {
            "source": "simulator",
            "duration_minutes": payload.duration_minutes,
            "will_resolve_at": resolves_at.isoformat(),
        },
    }
    written = _rows(service.table("network_alerts").insert(alert).execute())
    alert_id = str(written[0]["id"]) if written else ""

    _write_network_stat(service, bank, method, rate)

    await publish_alert(
        get_redis_client(),
        {"type": "alert_fired", "alert": {**alert, "id": alert_id}},
    )

    task = asyncio.create_task(
        _lift_downtime(service, alert_id, bank, method, payload.duration_minutes * 60)
    )
    _PENDING_RESOLUTIONS.add(task)
    task.add_done_callback(_PENDING_RESOLUTIONS.discard)

    log.info(
        "simulated_downtime_started",
        alert_id=alert_id,
        bank=bank,
        method=method,
        severity=payload.severity,
        duration_minutes=payload.duration_minutes,
    )
    return DowntimeResponse(
        alert_id=alert_id,
        bank=bank,
        method=method,
        severity=payload.severity,
        success_rate=rate,
        will_resolve_at=resolves_at.isoformat(),
    )


def _network_merchant_count(supabase_client: Any) -> int:
    """How wide to claim the outage is.

    A count and nothing else — the same posture as the real detector's
    `affected_merchants_count`, where a cardinality is the only cross-tenant
    fact that ever leaves. Floored at a plausible network size, because the
    sentence the demo is making ("this is hitting eight of you") is a claim
    about a network that a single-tenant fixture cannot produce, and a simulator
    rendering "affecting 1 merchant" would be simulating the wrong thing.
    """
    rows = _rows(supabase_client.table("merchants").select("id").limit(50).execute())
    return max(len(rows), 8)


class NetworkSeedRequest(CamelModel):
    days: int = Field(default=DEFAULT_DAYS, ge=1, le=MAX_DAYS)
    #: Fixes the draw so a rehearsed demo shows the same heatmap twice.
    seed: int | None = Field(default=None)


class NetworkSeedResponse(CamelModel):
    rows: int
    cleared: int
    days: int
    instruments: int
    banks: list[str]
    methods: list[str]


@router.post("/network/seed", response_model=NetworkSeedResponse)
async def seed_network(
    payload: NetworkSeedRequest,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> NetworkSeedResponse:
    """Populate the heatmap with a week of plausible payment behaviour.

    Writes through the **service-role** client, unlike everything else in this
    router. `network_stats` has no merchant column, so there is no RLS policy a
    user client could satisfy — the table is cross-tenant by design, and the
    dev-environment gate on this router is what keeps that safe rather than a
    per-row check that has nothing to check.

    Off the event loop: roughly 1,700 rows in batches is blocking Supabase I/O,
    and holding the loop for it would stall every other request on the process.
    """
    summary = await asyncio.to_thread(
        seed_network_stats,
        get_service_client(),
        days=payload.days,
        seed=payload.seed,
    )
    log.info("network_seed_requested", merchant_id=user_id, **summary)
    return NetworkSeedResponse(**summary)


# ── Batch simulation (B1) ──────────────────────────────────────────────


class BatchStartRequest(CamelModel):
    n_cases: int = Field(default=1000, ge=50, le=MAX_CASES)
    #: Optional override of the playbook mix. Weights are normalised, so they
    #: need not sum to one.
    playbook_distribution: dict[str, float] | None = Field(default=None)
    #: Fixes the draw, so a rehearsed demo shows the same curve twice.
    seed: int | None = Field(default=None)


class BatchStartResponse(CamelModel):
    batch_id: str
    status: str
    estimated_seconds: float


class BatchRunResponse(CamelModel):
    batch_id: str
    status: str
    n_cases: int
    #: Null before the first progress tick; a partial `{progress: ...}` object
    #: while running; the finished `BatchResult` once complete.
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


def _normalised_distribution(raw: dict[str, float] | None) -> dict[str, float] | None:
    """Validate and normalise a caller-supplied playbook mix."""
    if raw is None:
        return None

    unknown = set(raw) - set(PLAYBOOK_CONFIGS)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown playbooks: {', '.join(sorted(unknown))}",
        )
    total = sum(weight for weight in raw.values() if weight > 0)
    if total <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Playbook distribution must have at least one positive weight.",
        )
    return {name: weight / total for name, weight in raw.items() if weight > 0}


async def _run_batch_to_completion(
    batch_id: str,
    merchant_id: str,
    n_cases: int,
    distribution: dict[str, float] | None,
    seed: int | None,
) -> None:
    """Run the batch and record how it ended, whichever way that is.

    A crashed run must leave `status = 'failed'` rather than `'running'`. The
    frontend shows a progress bar for anything still running, so a row left in
    that state is a spinner nobody can clear — worse than an error, because it
    looks like work still happening.
    """
    service = get_service_client()
    try:
        result = await run_batch(
            service,
            merchant_id,
            n_cases=n_cases,
            playbook_distribution=distribution,
            batch_id=batch_id,
            seed=seed,
        )
        service.table("batch_runs").update(
            {
                "status": "completed",
                "result": result.to_dict(),
                "completed_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", batch_id).execute()
        log.info("batch_run_completed", batch_id=batch_id, n_cases=n_cases)
    except Exception as exc:  # noqa: BLE001
        log.warning("batch_run_failed", batch_id=batch_id, error=str(exc))
        with contextlib.suppress(Exception):
            service.table("batch_runs").update(
                {
                    "status": "failed",
                    "error": str(exc)[:500],
                    "completed_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).eq("id", batch_id).execute()


def _start_batch_run(
    payload: BatchStartRequest,
    background_tasks: BackgroundTasks,
    user_id: str,
    supabase: Any,
) -> BatchStartResponse:
    """Insert the run row and queue the work.

    Synchronous and separate from the route so the scenario endpoint — which is
    a plain `def` — can start a batch for B1 without either duplicating this or
    being rewritten as a coroutine.
    """
    distribution = _normalised_distribution(payload.playbook_distribution)

    written = _rows(
        supabase.table("batch_runs")
        .insert(
            {
                "merchant_id": user_id,
                "status": "running",
                "n_cases": payload.n_cases,
                "started_at": datetime.now(UTC).isoformat(),
            }
        )
        .execute()
    )
    if not written:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not start the batch run.",
        )
    batch_id = str(written[0]["id"])

    background_tasks.add_task(
        _run_batch_to_completion, batch_id, user_id, payload.n_cases, distribution, payload.seed
    )
    log.info("batch_run_started", batch_id=batch_id, merchant_id=user_id, n_cases=payload.n_cases)

    return BatchStartResponse(
        batch_id=batch_id,
        status="running",
        estimated_seconds=round(payload.n_cases * SECONDS_PER_CASE, 1),
    )


@router.post(
    "/batch/start", response_model=BatchStartResponse, status_code=status.HTTP_202_ACCEPTED
)
async def start_batch(
    payload: BatchStartRequest,
    background_tasks: BackgroundTasks,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> BatchStartResponse:
    """Kick off a batch run and return before any of it has happened.

    202, not 200: the work is accepted, not done. The row is inserted through
    the caller's own client so RLS decides whose run it is; everything after
    that is the service role, because a background task outlives the request
    whose token would have scoped it.
    """
    return _start_batch_run(payload, background_tasks, user_id, supabase)


def _batch_response(row: dict[str, Any]) -> BatchRunResponse:
    return BatchRunResponse(
        batch_id=str(row["id"]),
        status=str(row.get("status") or "running"),
        n_cases=int(row.get("n_cases") or 0),
        result=row.get("result"),
        error=row.get("error"),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
    )


@router.get("/batch/latest", response_model=BatchRunResponse)
async def get_latest_batch(user_id: CurrentUserId, supabase: UserSupabase) -> BatchRunResponse:
    """The most recent run, finished or not.

    Declared before `/batch/{batch_id}` so the literal path wins the match —
    otherwise "latest" is read as an id and the route 404s on a valid request.

    Deliberately not "most recent *completed*": a page that skipped past a run
    still in flight would show stale results beside a progress bar for the run
    that is about to replace them.
    """
    rows = _rows(
        supabase.table("batch_runs")
        .select("*")
        .eq("merchant_id", user_id)
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No batch runs yet.",
        )
    return _batch_response(rows[0])


@router.get("/batch/{batch_id}", response_model=BatchRunResponse)
async def get_batch(
    batch_id: str, user_id: CurrentUserId, supabase: UserSupabase
) -> BatchRunResponse:
    """One run by id. RLS decides whether it is the caller's to see."""
    rows = _rows(supabase.table("batch_runs").select("*").eq("id", batch_id).limit(1).execute())
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown batch run.")
    return _batch_response(rows[0])


# ── Causal DAG definitions ─────────────────────────────────────────────


class DagSeedResponse(CamelModel):
    nodes: int
    playbooks: list[str]
    dag_version: str


@router.post("/dag/seed", response_model=DagSeedResponse)
async def seed_dag(user_id: CurrentUserId, supabase: UserSupabase) -> DagSeedResponse:
    """Publish the causal graph definitions into `causal_dag`.

    Service-role, like the network seeder and for the same reason: the table is
    global reference data with no merchant column, so no RLS policy exists that
    a user client could satisfy for a write.

    The rows are a published copy, not the source. `definitions.py` is what the
    agent reasons from and what the API serves, so a stale table degrades a SQL
    query rather than a diagnosis.
    """
    summary = await asyncio.to_thread(seed_causal_dag, get_service_client())
    log.info("dag_seed_requested", merchant_id=user_id, **summary)
    return DagSeedResponse(**summary)
