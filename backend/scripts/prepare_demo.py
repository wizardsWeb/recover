"""Seed a deployment with complete, recording-ready demo data.

Three merchants, all fixtures, all six scenarios fired and driven to their end
state, uplift models trained, a batch run, network history, and a warm LLM
cache. Writes ``demo_state.json`` for the Playwright recording script.

**Why this runs against the database rather than the API.** ``/api/simulator/*``
is gated by ``require_dev_environment`` and returns 404 wherever ENVIRONMENT is
"production" — deliberately, since the router manufactures financial events. So
a seeder that drove the deployed HTTP surface would get 404s for every step that
matters. This calls the same functions the router calls, with the service-role
client the router hands them, which is the identical code path minus the gate.

**Why there are no sleeps.** The API fires scenarios through
``BackgroundTasks``, so a caller has to wait and hope. Here the agent loop is
awaited directly: when ``process_event`` returns, the pass is genuinely over.
That is both faster and deterministic, where a fixed sleep is neither.

**On verification.** Expected arms and statuses are reported, not asserted. Arm
selection is a Thompson draw, so a run that dies because sampling went the other
way would be a seeder that fails for the one reason that is not a bug. The
summary prints expected beside actual and flags mismatches; deciding whether a
mismatch matters is a judgement, and it is yours.

Usage::

    cd backend
    .venv/bin/python scripts/prepare_demo.py
    .venv/bin/python scripts/prepare_demo.py --skip-llm-cache   # no Gemini quota
    .venv/bin/python scripts/prepare_demo.py --batch-cases 200

Most of this is idempotent: users are reused, fixtures upsert, priors reset in
place, network stats clear their window before rewriting it, and any still-open
case for a scenario's persona is closed before that scenario fires again.

**The uplift history is the exception.** ``seed_uplift_history`` only inserts —
it has no delete — so running it twice leaves 400 synthetic cases per merchant
rather than 200, and a third run leaves 600. That corpus is what the uplift
models train on and what the ROI page counts, so quietly doubling it changes the
numbers on screen. Pass ``--skip-history`` on a re-run unless you actually want
more history than you had.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.agent.core import process_event

# Private names, imported on purpose. The alert row below has to match what
# `/api/simulator/network/downtime` writes or the network page will render it
# differently from a real one, and a copy of the shape here would be a second
# definition of the same row waiting to drift from the first.
from app.api.simulator import (
    _DOWNTIME_RATES,
    _DOWNTIME_SAMPLE_SIZE,
    _network_merchant_count,
    _write_network_stat,
)
from app.config import get_settings
from app.db import get_service_client
from app.ml.network.aggregator import normalise_bank, normalise_method
from app.ml.uplift.model import train_uplift_model
from app.simulator import loader
from app.simulator.batch import run_batch
from app.simulator.network_seed import seed_network_stats
from app.simulator.scenarios import SCENARIO_REGISTRY
from app.simulator.uplift_seed import PLAYBOOK_WEIGHTS, seed_uplift_history

FRONTEND_URL = "https://recover-aa-prod-frontend.ashybay-6728b979.eastasia.azurecontainerapps.io"
PASSWORD = "DemoRecover2026!"

#: Fixed so a rehearsed demo shows the same numbers twice.
SEED = 20260115


@dataclass
class DemoMerchant:
    slug: str
    email: str
    brand_name: str
    vertical: str
    merchant_id: str = ""


@dataclass
class Scenario:
    key: str
    code: str
    merchant_slug: str
    customer_name: str
    expected_arm: str
    expected_status: str
    #: Injected after the first agent pass, then a second pass reads it.
    reply: str | None = None
    case_id: str = ""
    actual_arm: str = ""
    actual_status: str = ""
    note: str = ""


MERCHANTS = [
    DemoMerchant("kajal", "demo.kajal@recoverapp.dev", "Kajal & Co.", "d2c_beauty"),
    DemoMerchant("zenith", "demo.zenith@recoverapp.dev", "Zenith Learning", "edtech_subscription"),
    DemoMerchant("sharma", "demo.sharma@recoverapp.dev", "Sharma Distributors", "b2b_distribution"),
]

SCENARIOS = [
    Scenario(
        "S1_suresh",
        "S1",
        "zenith",
        "Suresh Iyer",
        "retry_at_inferred_date_plus_whatsapp_fallback",
        "recovered",
    ),
    Scenario(
        "S5_vikram",
        "S5",
        "zenith",
        "Vikram Sethi",
        "whatsapp_payment_link_now",
        "stopped",
        reply="bhaisaab beta ab coaching nahi le raha, cancel kar do please",
    ),
    Scenario("S2_priya", "S2", "kajal", "Priya Menon", "whatsapp_saved_cart_8pct", "in_flight"),
    Scenario("S3_aditya", "S3", "kajal", "Aditya Rao", "silent_retry_next_morning", "recovered"),
    Scenario("S6_sana", "S6", "kajal", "Sana Khatri", "any", "stopped", reply="STOP"),
    Scenario(
        "S4_meera",
        "S4",
        "sharma",
        "Meera Patil",
        "graduated_b2b_sequence",
        "in_flight",
        reply="boss, 50% abhi kar deti hoon, baaki 25 tak",
    ),
]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

_step = 0


def step(title: str) -> None:
    global _step
    _step += 1
    print(f"\n[{_step}/9] {title}", flush=True)


def ok(message: str) -> None:
    print(f"      ✓ {message}", flush=True)


def warn(message: str) -> None:
    print(f"      ! {message}", flush=True)


def _rows(result: Any) -> list[dict[str, Any]]:
    return list(result.data or [])


#: Errors worth trying again. All transport-level: the request never reached
#: PostgREST, or its answer never came back. A 4xx is not in here, because
#: retrying a rejected request just gets it rejected again.
_TRANSIENT = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
)


def service_client() -> Any:
    """A service-role client with timeouts sized for a long-haul link.

    The default postgrest timeout assumes the client is near the database. Run
    from a laptop against a project in another region, a seeder making thousands
    of round trips will eventually meet one that takes longer than the default
    allows, and the whole run dies on a single slow insert.
    """
    settings = get_settings()
    try:
        from supabase import create_client

        # SyncClientOptions, not the `ClientOptions` in the same module — that
        # one is the async variant, and create_client rejects it.
        from supabase.lib.client_options import SyncClientOptions

        return create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_KEY,
            options=SyncClientOptions(postgrest_client_timeout=120),
        )
    except Exception as exc:  # noqa: BLE001 - options are a nicety, not a requirement
        warn(f"could not set a custom timeout ({exc}); using the default client")
        return get_service_client()


def retry(label: str, call: Any, *args: Any, attempts: int = 4, **kwargs: Any) -> Any:
    """Run a synchronous call, retrying transport failures with a growing pause.

    Only used for steps that are safe to repeat — upserts, reads, and writes
    that overwrite rather than append. The agent loop is deliberately *not*
    retried: a pass that timed out halfway may already have sent a message, and
    running it again would send a second one.
    """
    for attempt in range(1, attempts + 1):
        try:
            return call(*args, **kwargs)
        except _TRANSIENT as exc:
            if attempt == attempts:
                raise
            warn(f"{label}: {type(exc).__name__} (attempt {attempt}/{attempts}), retrying")
            time.sleep(2 * attempt)


async def retry_async(label: str, call: Any, *args: Any, attempts: int = 4, **kwargs: Any) -> Any:
    """``retry`` for awaitables. Same restriction on what may be retried."""
    for attempt in range(1, attempts + 1):
        try:
            return await call(*args, **kwargs)
        except _TRANSIENT as exc:
            if attempt == attempts:
                raise
            warn(f"{label}: {type(exc).__name__} (attempt {attempt}/{attempts}), retrying")
            await asyncio.sleep(2 * attempt)


def _export_dotenv() -> None:
    """Copy ``backend/.env`` into the process environment.

    pydantic-settings reads the file into a ``Settings`` object without ever
    touching ``os.environ``, and not everything goes through settings:
    ``app/agent/llm.py`` reads ``GEMINI_API_KEY`` from the environment directly.
    In a container that is fine, because the platform sets real environment
    variables. Run from a shell with only a ``.env`` file, the key is invisible
    and every LLM call quietly returns its fallback — which looks like working
    software right up until you read the message copy.

    Existing variables win, so an explicitly exported value still overrides the
    file.
    """
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


# ---------------------------------------------------------------------------
# 1 — accounts
# ---------------------------------------------------------------------------


def _sign_in(email: str) -> str | None:
    """Return the user id for ``email``, or None if the password does not match.

    Used instead of paging ``admin.list_users`` to recognise an account this
    script created on an earlier run. Enumerating every user in the project to
    find three known addresses is a lot of reading for a lookup we can do with
    the credential we already set, and the password is fixed precisely so this
    works.
    """
    settings = get_settings()
    try:
        response = httpx.post(
            f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": settings.SUPABASE_ANON_KEY},
            json={"email": email, "password": PASSWORD},
            timeout=20.0,
        )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    user = response.json().get("user") or {}
    return str(user.get("id")) if user.get("id") else None


def create_accounts(db: Any) -> None:
    step("Creating merchant accounts")
    for merchant in MERCHANTS:
        # `dev: true` is what opens /app/dev/simulator on a deployed build —
        # see the gate in frontend/app/app/dev/simulator/page.tsx.
        metadata = {"dev": True, "brand_name": merchant.brand_name, "name": merchant.brand_name}

        try:
            created = db.auth.admin.create_user(
                {
                    "email": merchant.email,
                    "password": PASSWORD,
                    "email_confirm": True,
                    "user_metadata": metadata,
                }
            )
            user = created.user if hasattr(created, "user") else created
            merchant.merchant_id = str(user.id)
            ok(f"{merchant.brand_name}: created {merchant.merchant_id}")
        except Exception as exc:  # noqa: BLE001 - the API's conflict is not a typed error
            # Already there from a previous run. Sign in to recover the id, then
            # refresh the metadata in case this script's shape has changed since.
            existing_id = _sign_in(merchant.email)
            if not existing_id:
                print(f"      ✗ {merchant.brand_name}: cannot create or sign in — {exc}")
                raise SystemExit(
                    f"{merchant.email} exists with a different password. Reset it in the "
                    "Supabase dashboard, or delete the user, then re-run."
                ) from exc
            db.auth.admin.update_user_by_id(
                existing_id,
                {"password": PASSWORD, "email_confirm": True, "user_metadata": metadata},
            )
            merchant.merchant_id = existing_id
            ok(f"{merchant.brand_name}: reused {merchant.merchant_id}")

        # on_auth_user_created has made the row; this sets what it could not
        # know, and marks it onboarded so sign-in lands on /app.
        db.table("merchants").update(
            {
                "name": merchant.brand_name,
                "vertical": merchant.vertical,
                "onboarded": True,
            }
        ).eq("id", merchant.merchant_id).execute()


# ---------------------------------------------------------------------------
# 2/3 — fixtures, priors, network, uplift corpus
# ---------------------------------------------------------------------------


async def load_all_fixtures(db: Any) -> None:
    step("Loading fixtures and bandit priors")
    for merchant in MERCHANTS:
        result = await retry_async(
            f"{merchant.slug} fixtures",
            loader.load_fixtures_for_merchant,
            db,
            merchant.merchant_id,
            "prepare-demo",
        )
        priors = await retry_async(
            f"{merchant.slug} priors", loader.seed_bandit_priors, db, merchant.merchant_id
        )
        ok(
            f"{merchant.brand_name}: {result.get('customers_created', 0)} customers, "
            f"{result.get('payment_methods', 0)} payment methods, "
            f"{priors.get('rows', 0)} prior rows"
        )


def seed_shared_data(db: Any) -> dict[str, Any]:
    step("Seeding network stats (shared) and uplift history (per merchant)")
    network = seed_network_stats(db, seed=SEED)
    ok(f"network_stats: {network.get('rows_written', network.get('rows', '?'))} rows")

    for merchant in MERCHANTS:
        history = seed_uplift_history(db, merchant.merchant_id, total_cases=200, seed=SEED)
        ok(f"{merchant.brand_name}: {history.get('cases', history.get('rows', '?'))} history cases")
    return network


def train_models(db: Any) -> int:
    step("Training uplift models (4 playbooks × 3 merchants)")
    trained = 0
    for merchant in MERCHANTS:
        for playbook in PLAYBOOK_WEIGHTS:
            result = retry(
                f"{merchant.slug}/{playbook} training",
                train_uplift_model,
                db,
                merchant.merchant_id,
                playbook,
            )
            if result.get("status") == "insufficient_data":
                warn(f"{merchant.slug}/{playbook}: insufficient data, no snapshot")
                continue
            trained += 1
            ok(
                f"{merchant.slug}/{playbook}: {result.get('model_type', 'model')}, "
                f"n={result.get('n_samples', result.get('treated_n', '?'))}"
            )
    return trained


# ---------------------------------------------------------------------------
# 5 — LLM cache
# ---------------------------------------------------------------------------


async def warm_llm_cache(db: Any, merchant: DemoMerchant) -> int:
    step("Warming the LLM cache")
    try:
        from warm_llm_cache import build_targets, load_merchant
    except ImportError as exc:
        warn(f"could not import warm_llm_cache ({exc}); skipping")
        return 0

    override = load_merchant(db, merchant.merchant_id)
    targets = build_targets(db, override)
    warmed = 0
    for label, run in targets:
        if await run():
            warmed += 1
            ok(label)
        else:
            warn(f"{label} — fell back, re-run to retry")
    return warmed


# ---------------------------------------------------------------------------
# 6 — scenarios
# ---------------------------------------------------------------------------


def _close_open_cases(db: Any, merchant_id: str, customer_name: str) -> int:
    """Close any still-open case for this persona.

    Without this the scenario functions find the existing case and reuse it, so
    a second run of this script would leave the demo showing whatever state the
    first run's case drifted into rather than a freshly played one.
    """
    customers = _rows(
        db.table("customers")
        .select("id")
        .eq("merchant_id", merchant_id)
        .eq("name", customer_name)
        .execute()
    )
    if not customers:
        return 0

    ids = [c["id"] for c in customers]
    open_cases = _rows(
        db.table("recovery_cases")
        .select("id")
        .eq("merchant_id", merchant_id)
        .in_("customer_id", ids)
        .in_("status", ["open", "in_flight", "scheduled"])
        .execute()
    )
    for case in open_cases:
        db.table("recovery_cases").update(
            {"status": "stopped", "updated_at": datetime.now(UTC).isoformat()}
        ).eq("id", case["id"]).execute()
    return len(open_cases)


def _inject_reply(db: Any, scenario: Scenario, merchant_id: str) -> None:
    """Insert a customer reply the way /api/simulator/replies does.

    The agent picks it up on its *next* pass — `_fetch_pending_reply` in
    agent/core.py treats a null `applied_state_update` as unread — which is why
    the caller runs the loop again afterwards rather than sleeping.
    """
    case = _rows(
        db.table("recovery_cases")
        .select("id, customer_id")
        .eq("id", scenario.case_id)
        .limit(1)
        .execute()
    )
    if not case:
        warn(f"{scenario.key}: no case to reply to")
        return

    row = case[0]
    inserted = _rows(
        db.table("customer_replies")
        .insert(
            {
                "case_id": row["id"],
                "merchant_id": merchant_id,
                "customer_id": row["customer_id"],
                "channel": "whatsapp",
                "raw_text": scenario.reply,
            }
        )
        .execute()
    )
    db.table("audit_events").insert(
        {
            "case_id": row["id"],
            "merchant_id": merchant_id,
            "actor": "system",
            "event": "reply_injected",
            "details": {
                "channel": "whatsapp",
                "reply_id": str(inserted[0]["id"]) if inserted else None,
            },
            "trace_id": "prepare-demo",
        }
    ).execute()


def _case_state(db: Any, case_id: str) -> tuple[str, str]:
    """Return ``(status, chosen_arm)`` for a case.

    Two tables, because the arm is not a property of the case. ``recovery_cases``
    holds the status; the arm is on the ``decide`` step in ``agent_decisions``,
    where it sits beside the context vector and the alternatives that were
    passed over — a case that was decided twice has both rows, and the latest
    one is the arm currently in play.
    """
    cases = _rows(db.table("recovery_cases").select("status").eq("id", case_id).limit(1).execute())
    if not cases:
        return ("missing", "")

    decisions = _rows(
        db.table("agent_decisions")
        .select("bandit_chosen_arm")
        .eq("case_id", case_id)
        .eq("step_name", "decide")
        .order("step_number", desc=True)
        .limit(1)
        .execute()
    )
    arm = str(decisions[0].get("bandit_chosen_arm") or "") if decisions else ""
    return (str(cases[0].get("status") or ""), arm)


async def fire_scenarios(db: Any, by_slug: dict[str, DemoMerchant]) -> None:
    step("Firing scenarios")
    for scenario in SCENARIOS:
        merchant = by_slug[scenario.merchant_slug]
        closed = _close_open_cases(db, merchant.merchant_id, scenario.customer_name)

        result = SCENARIO_REGISTRY[scenario.code](db, merchant.merchant_id, "prepare-demo")
        scenario.case_id = str(result.get("case_id") or "")

        event_ids = [e for e in (result.get("event_ids") or []) if e]
        if not event_ids and result.get("event_id"):
            event_ids = [str(result["event_id"])]

        for event_id in event_ids:
            await process_event(str(event_id), merchant.merchant_id, db)

        if scenario.reply:
            _inject_reply(db, scenario, merchant.merchant_id)
            # Second pass: this is where the reply is classified and acted on.
            for event_id in event_ids:
                await process_event(str(event_id), merchant.merchant_id, db)

        scenario.actual_status, scenario.actual_arm = _case_state(db, scenario.case_id)
        matched = scenario.actual_status == scenario.expected_status
        prefix = "✓" if matched else "!"
        if not matched:
            scenario.note = f"expected {scenario.expected_status}"
        print(
            f"      {prefix} {scenario.key}: {scenario.actual_status or '—'} "
            f"arm={scenario.actual_arm or '—'}" + (f"  (closed {closed} stale)" if closed else ""),
            flush=True,
        )


# ---------------------------------------------------------------------------
# 7/8 — batch and network alert
# ---------------------------------------------------------------------------


async def run_demo_batch(db: Any, merchant: DemoMerchant, n_cases: int) -> dict[str, Any]:
    """Run a batch and record it the way the API does.

    ``run_batch`` computes and writes case rows, but it does not create the
    ``batch_runs`` row — that belongs to ``_start_batch_run`` in the router,
    with ``_run_batch_to_completion`` closing it out afterwards. Calling
    ``run_batch`` alone therefore leaves /app/batch with nothing to show, since
    the page reads the run row rather than the cases. Both halves are mirrored
    here, including marking the row failed on the way out: the frontend renders
    a progress bar for anything still ``running``, so a row abandoned in that
    state is a spinner nobody can clear.
    """
    step(f"Running a {n_cases}-case batch for {merchant.brand_name}")
    started = time.monotonic()

    written = _rows(
        db.table("batch_runs")
        .insert(
            {
                "merchant_id": merchant.merchant_id,
                "status": "running",
                "n_cases": n_cases,
                "started_at": datetime.now(UTC).isoformat(),
            }
        )
        .execute()
    )
    if not written:
        warn("could not create the batch_runs row; /app/batch will be empty")
        return {}
    batch_id = str(written[0]["id"])

    try:
        result = await retry_async(
            "batch",
            run_batch,
            db,
            merchant.merchant_id,
            n_cases=n_cases,
            batch_id=batch_id,
            seed=SEED,
            attempts=2,
        )
    except Exception as exc:  # noqa: BLE001 - the row must not be left running
        db.table("batch_runs").update(
            {
                "status": "failed",
                "error": str(exc)[:500],
                "completed_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", batch_id).execute()
        raise

    now = datetime.now(UTC).isoformat()
    db.table("batch_runs").update(
        {
            "status": "completed",
            "result": result.to_dict(),
            "completed_at": now,
            "updated_at": now,
        }
    ).eq("id", batch_id).execute()

    elapsed = time.monotonic() - started
    # The rates live in a dict keyed by policy, not as two scalar fields.
    settled = result.settled_recovery_rate_by_policy or {}
    whole_run = result.recovery_rate_by_policy or {}
    bandit = settled.get("bandit", whole_run.get("bandit"))
    baseline = settled.get("baseline", whole_run.get("baseline"))

    if bandit is not None and baseline is not None:
        ok(
            f"settled: bandit {bandit:.1%} vs baseline {baseline:.1%} "
            f"({'bandit ahead' if bandit > baseline else 'BANDIT NOT AHEAD'}), {elapsed:.0f}s"
        )
        if bandit <= baseline:
            warn("the learning curve will not show a crossover — re-run with a different seed")
    else:
        ok(f"completed in {elapsed:.0f}s — no policy rates in the result")

    if result.bandit_convergence_case:
        ok(f"bandit overtook baseline at case {result.bandit_convergence_case}")

    return {"batch_id": batch_id, "bandit": bandit, "baseline": baseline}


def seed_network_alert(db: Any) -> str:
    step("Writing a resolved SBI/UPI downtime alert into history")
    bank = normalise_bank("SBI")
    method = normalise_method("upi")
    now = datetime.now(UTC)

    # Clear anything still open first, so the demo does not open on a live
    # outage banner and so the insert below cannot hit the duplicate check the
    # endpoint enforces.
    db.table("network_alerts").update(
        {"resolved_at": now.isoformat(), "updated_at": now.isoformat()}
    ).is_("resolved_at", "null").execute()

    alert = {
        "alert_type": "downtime",
        "affected_bank": bank,
        "affected_method": method,
        "severity": "high",
        "z_score": None,
        "sample_size": _DOWNTIME_SAMPLE_SIZE,
        "affected_merchants_count": _network_merchant_count(db),
        "network_wide_success_rate": _DOWNTIME_RATES["high"],
        "baseline_rate": 0.82,
        "detected_at": now.isoformat(),
        # Resolved on insert: the point is a history entry, not a live banner
        # sitting over the recording. Playwright fires a fresh one on camera.
        "resolved_at": now.isoformat(),
        "metadata": {"source": "prepare_demo", "duration_minutes": 30},
    }
    written = _rows(db.table("network_alerts").insert(alert).execute())
    alert_id = str(written[0]["id"]) if written else ""

    # Put the instrument back to a healthy reading, so the heatmap does not
    # show SBI/UPI permanently red after a resolved alert.
    _write_network_stat(db, bank, method, 0.82)
    ok(f"alert {alert_id or '(unknown id)'} — detected and resolved")
    return alert_id


# ---------------------------------------------------------------------------
# 9/10 — state file and summary
# ---------------------------------------------------------------------------


def write_state(path: Path, batch: dict[str, Any], alert_id: str) -> None:
    step("Writing demo_state.json")
    state = {
        "base_url": FRONTEND_URL,
        "accounts": {
            m.slug: {
                "email": m.email,
                "password": PASSWORD,
                "merchant_id": m.merchant_id,
                "brand_name": m.brand_name,
            }
            for m in MERCHANTS
        },
        "cases": {
            s.key: {
                "case_id": s.case_id,
                "merchant": s.merchant_slug,
                "customer_name": s.customer_name,
                "expected_arm": s.expected_arm,
                "expected_status": s.expected_status,
                "actual_arm": s.actual_arm,
                "actual_status": s.actual_status,
            }
            for s in SCENARIOS
        },
        "batch_id": batch.get("batch_id", ""),
        "network_alert_id": alert_id,
        "network_downtime_endpoint": "/api/simulator/network/downtime",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    path.write_text(json.dumps(state, indent=2) + "\n")
    ok(str(path))


def summary(network: dict[str, Any], trained: int, batch: dict[str, Any], warmed: int) -> None:
    line = "═" * 67
    print(f"\n{line}")
    print("  RECOVER — DEMO DATA READY")
    print(f"{line}\n")

    print("  ACCOUNTS")
    for m in MERCHANTS:
        print(f"    {m.brand_name:<22} {m.email:<30} {PASSWORD}")

    print("\n  SCENARIOS")
    print(f"    {'Code':<11}{'Merchant':<10}{'Status':<12}{'Arm':<40}")
    for s in SCENARIOS:
        flag = " " if s.actual_status == s.expected_status else "!"
        arm = (s.actual_arm or "—")[:38]
        print(f"  {flag} {s.key:<11}{s.merchant_slug:<10}{s.actual_status or '—':<12}{arm:<40}")

    mismatches = [s for s in SCENARIOS if s.actual_status != s.expected_status]
    if mismatches:
        print("\n    ! rows above did not reach their expected status:")
        for s in mismatches:
            print(f"      {s.key}: got {s.actual_status or 'nothing'}, {s.note}")

    print("\n  SUPPORTING DATA")
    print(f"    Network stats:     {network.get('rows_written', network.get('rows', '?'))} rows")
    print(f"    Uplift snapshots:  {trained} trained")
    print(f"    Batch:             {batch.get('batch_id') or 'not run'}")
    print(f"    LLM cache:         {warmed} targets warmed")
    print(f"\n  NEXT: log in at {FRONTEND_URL}/login")
    print(f"{line}\n")


# ---------------------------------------------------------------------------


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-cases", type=int, default=200)
    parser.add_argument("--skip-llm-cache", action="store_true")
    parser.add_argument("--skip-batch", action="store_true")
    parser.add_argument(
        "--skip-history",
        action="store_true",
        help="Skip network stats and uplift history. Use on a re-run: the uplift "
        "seeder only inserts, so repeating it doubles the corpus.",
    )
    args = parser.parse_args()

    _export_dotenv()

    settings = get_settings()
    print(f"Supabase project: {settings.SUPABASE_URL}")
    print(f"Local ENVIRONMENT: {settings.ENVIRONMENT}")

    if not os.environ.get("GEMINI_API_KEY"):
        print(
            "\n  ! GEMINI_API_KEY is not set. Every LLM call will return its fallback,\n"
            "    so the WhatsApp copy and reply classifications in the recording would\n"
            "    be canned text rather than generated. Set it in backend/.env and re-run,\n"
            "    or pass --skip-llm-cache to acknowledge and continue.\n"
        )
        if not args.skip_llm_cache:
            return 2

    db = service_client()
    by_slug = {m.slug: m for m in MERCHANTS}

    create_accounts(db)
    await load_all_fixtures(db)

    network: dict[str, Any] = {}
    if args.skip_history:
        step("Skipping network stats and uplift history (--skip-history)")
    else:
        network = seed_shared_data(db)
    trained = train_models(db)

    warmed = 0
    if args.skip_llm_cache:
        step("Skipping the LLM cache (--skip-llm-cache)")
    else:
        warmed = await warm_llm_cache(db, by_slug["kajal"])

    await fire_scenarios(db, by_slug)

    batch: dict[str, Any] = {}
    if args.skip_batch:
        step("Skipping the batch run (--skip-batch)")
    else:
        batch = await run_demo_batch(db, by_slug["kajal"], args.batch_cases)

    alert_id = seed_network_alert(db)
    write_state(Path(__file__).parent / "demo_state.json", batch, alert_id)
    summary(network, trained, batch, warmed)

    return 1 if any(s.actual_status != s.expected_status for s in SCENARIOS) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
