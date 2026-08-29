# Recover — AI Revenue Recovery Agent

[![Typecheck](https://github.com/wizardsWeb/razorpay_buildathon/actions/workflows/typecheck.yml/badge.svg)](https://github.com/wizardsWeb/razorpay_buildathon/actions/workflows/typecheck.yml)
[![Deploy](https://github.com/wizardsWeb/razorpay_buildathon/actions/workflows/deploy.yml/badge.svg)](https://github.com/wizardsWeb/razorpay_buildathon/actions/workflows/deploy.yml)

Recover is a merchant-side agent for Razorpay sellers that watches the event
stream for revenue slipping away — failed payments, abandoned checkouts, broken
subscription mandates, overdue B2B invoices — diagnoses why each one happened,
and works it back through Razorpay's own rails. It addresses the **agentic
revenue recovery** track: not a dunning cron, but an agent that decides what to
do per case and learns from what happened.

What makes it different is that all four of its judgements are auditable. A
causal DAG produces the diagnosis, so the cause is a traversal you can read
rather than a sentence a model wrote. A contextual bandit picks the action, so
every alternative it rejected is on the case with the reason. A T-learner gates
whether to act at all, so the cheapest recovery — not sending anything to
someone who would have paid regardless — is one it can choose. And the number it
reports is measured against a deliberately untouched holdout group, so
"incremental" means caused rather than merely coincident.

Phase 13 wires it to the real Razorpay test API: webhooks are HMAC-verified,
payment links are genuine `rzp.io` URLs, and a customer paying one closes the
case and moves the bandit's posterior.

## Quick start

**Prerequisites:** Docker, Node 20, Python 3.11, Poetry, and a Supabase project.

**1. Create the database.**

Create a Supabase project, then apply the schema. Either:

```bash
supabase link --project-ref <your-project-ref>
supabase db push
```

or paste `supabase/migrations/20260101000000_initial_schema.sql` into the
Supabase SQL editor and run it.

Confirm it took — every table should come back with row security on:

```sql
select tablename, rowsecurity from pg_tables where schemaname = 'public';
```

**2. Fill in the environment.**

Three files, all from `.env.example` templates:

```bash
cp .env.example .env                          # compose build args
cp backend/.env.example backend/.env          # FastAPI
cp frontend/.env.example frontend/.env.local  # only needed for `npm run dev`
```

The values come from **Supabase → Project Settings → API**: the project URL,
the `anon` key, the `service_role` key, and the JWT secret.

> The `NEXT_PUBLIC_*` values are **build args**, not runtime config — Next
> inlines them into the browser bundle when it builds. Changing them means
> rebuilding the frontend image, not just restarting it.

**3. Run it.**

```bash
docker compose up --build
```

`docker-compose.override.yml` is picked up automatically and gives the backend
hot reload against your working tree. For frontend work, run `npm run dev` in
`frontend/` instead — it is much faster than a bind-mounted Next dev server.

**4. Check it.**

```bash
curl http://localhost:8000/health     # {"status":"ok",...}
open http://localhost:3000
```

Sign up, complete onboarding, and you land on the dashboard. Signup creates
both an `auth.users` row and a `public.merchants` row — the `on_auth_user_created`
trigger does the second one.

## Razorpay test mode

Everything below is optional. With no Razorpay keys the agent runs end to end
against the simulator and every adapter reports itself as simulated — which is
the state the test suite runs in. Setting the keys turns three adapters real.

**1. Keys.** [dashboard.razorpay.com](https://dashboard.razorpay.com) → make sure
the **Test mode** toggle is on → Settings → API Keys → Generate Test Key. Put
them in `backend/.env`:

```bash
RAZORPAY_TEST_API_KEY=rzp_test_xxxxxxxxxxxx
RAZORPAY_TEST_KEY_SECRET=...
```

**2. Webhook.** Settings → Webhooks → Add New Webhook.

- URL: `https://<your-backend>/api/events/webhook`
- Secret: any strong random string — put the same value in
  `RAZORPAY_WEBHOOK_SECRET`
- Events: `payment.failed`, `payment.captured`, `subscription.charged`,
  `subscription.halted`, `invoice.payment_failed`, `payment_link.paid`

Also set `RAZORPAY_WEBHOOK_MERCHANT_ID` to the merchant UUID the webhooks belong
to. A real Razorpay webhook carries no bearer token, so there is no JWT to read
the merchant from; the receiver resolves it from the payload's customer where it
can and falls back to this.

> Razorpay must be able to reach the URL. For local development, tunnel it
> (`cloudflared tunnel --url http://localhost:8000`) and use the tunnel host.

**3. A real subscription, for scenario S1 (optional).** In the dashboard: create
a Plan (₹2,999, monthly), a Customer, then a Subscription. Put the ids in
`backend/.env` and S1 fires against the real subscription instead of the
scripted one — no code change:

```bash
RAZORPAY_DEMO_SUBSCRIPTION_ID=sub_xxxxxxxx
RAZORPAY_DEMO_CUSTOMER_ID=cust_xxxxxxxx
```

**4. Check it.** Settings → **Test mode** in the dashboard reports what the
server thinks is configured, lists which adapters are real, and carries the test
cards. Or:

```bash
curl -H "Authorization: Bearer <jwt>" http://localhost:8000/api/integrations/razorpay
```

### Test credentials

| Method | Value | Outcome |
| --- | --- | --- |
| Visa (domestic) | `4111 1111 1111 1111` | mock bank page → you pick |
| Mastercard (domestic) | `5104 0600 0000 0008` | mock bank page → you pick |
| Visa (international) | `4239 5360 0631 5640` | mock bank page → you pick |
| UPI | `success@razorpay` | succeeds immediately |
| UPI | `failure@razorpay` | fails immediately |

Any CVV, any future expiry. **The cards do not decide their own outcome** —
after entering details Razorpay shows a mock bank page with *Success* and
*Failure* buttons and whichever you click is what happens. This is the thing
that trips up a first demo. The UPI handles are the exception.

### The loop, end to end

1. A payment fails — fired by the simulator, or by Razorpay for real.
2. The webhook is stored and 202'd; the agent runs in the background.
3. It diagnoses, checks uplift, picks an arm, clears the guardrail.
4. It mints a **real** payment link, stamped with the case id.
5. You open the `rzp.io` link and pay with a test card.
6. Razorpay fires `payment.captured`; the receiver verifies the signature.
7. The case closes as recovered and the arm's posterior moves.

Step 6 is what Phase 13 added. Before it the agent could send a real link and
never learn whether anyone paid it.

## Architecture

```
   browser
      │
      │  Supabase session cookie (refreshed in proxy.ts)
      ▼
┌─────────────────────┐        Bearer <supabase jwt>       ┌──────────────────┐
│  Next.js 16         │ ────────────────────────────────►  │  FastAPI         │
│  frontend :3000     │                                    │  backend :8000   │
│                     │ ◄────────────────────────────────  │                  │
│  server components  │            camelCase JSON          │  all business    │
│  read Supabase      │                                    │  logic lives     │
│  directly for reads │                                    │  here            │
└──────────┬──────────┘                                    └────────┬─────────┘
           │                                                        │
           │  anon key, RLS as the user                             │  same user JWT,
           │                                                        │  RLS as the user
           ▼                                                        ▼
        ┌───────────────────────────────────────────────────────────────┐
        │  Supabase — Postgres 15 + Auth                                │
        │  RLS on every table: merchant_id = auth.uid()                 │
        └───────────────────────────────────────────────────────────────┘
```

Two things are worth knowing about this shape:

- **The same JWT enforces RLS on both sides.** The frontend queries Supabase
  with the user's session; the backend forwards that same token into its own
  Supabase client. Neither relies on application code to scope a query — the
  `merchant_id = auth.uid()` policy does it.
- **Business logic never lives in a Next.js route handler.** Reads that a
  server component can do directly, it does. Everything that decides or writes
  goes through FastAPI.

### The agent loop

```
Razorpay webhooks ──► /api/events/webhook ──► agent core loop
  (HMAC-verified)      (202, then background)   │
                                               ├─ detect      event → playbook
                                               ├─ diagnose    causal DAG + Gemini
                                               ├─ uplift      T-learner gate
                                               ├─ decide      Thompson bandit
                                               ├─ guardrail   RBI / TRAI / DPDP
                                               ├─ execute     Razorpay APIs
                                               │                ├─ Payment Links
                                               │                ├─ Subscriptions
                                               │                └─ Payment Gateway
                                               ├─ listen       reply → intent
                                               ├─ learn        posterior update
                                               └─ audit        append-only trail
                                                       │
                        payment.captured ◄─────────────┘
                     (closes the case, credits the arm)
```

Three exits end a pass early, each writing a terminal state and an audit row:
the uplift check says SKIP, the guardrail says BLOCK, or the customer's reply
says stop.

## What is real and what is simulated

The distinction is enforced in code, not just documented here: every
`execution_attempts` row carries a `simulated` flag derived from the adapter's
own response, and the adapter name differs (`razorpay_payment_links` versus
`razorpay_payment_links_simulated`). A screen can therefore never present a
simulated send as a real one.

| Component | Status | Detail |
| --- | --- | --- |
| Razorpay webhooks | **Real** | HMAC-SHA256 verified over the raw body |
| Payment Links | **Real** | Genuine `rzp.io` URLs, stamped with the case id |
| Subscription state | **Real** | Reads `subscription.pending_update` |
| Payment fetch | **Real** | Confirms a capture against Razorpay |
| Customer payments | **Real** (test mode) | Test card → mock bank page |
| WhatsApp | Simulated | Payload and body stored; nothing sent |
| SMS / Email | Simulated | Payload stored; no provider wired |
| Gemini diagnosis + copy | Real | Falls back to templates when unavailable |
| Batch simulation numbers | Simulated | 1,000 synthetic cases, not merchant money |

Two honest notes on the Razorpay side:

- **There is no "retry this failed charge now" API.** A Razorpay subscription
  retries on its own schedule, so `retry_charge` reads and records the pending
  state rather than claiming to have forced a charge. The customer-facing
  recovery is the payment link the same decision mints.
- **Mandate re-registration is not something a merchant can do for a customer.**
  That adapter mints a payment link described "Update your payment method",
  which is the actual mechanism.

## Layout

```
.
├── frontend/                    Next.js 16, App Router, Tailwind 4, shadcn/Base UI
│   ├── app/
│   │   ├── (marketing)/         landing page — owns /
│   │   ├── (auth)/              login, signup, onboarding
│   │   └── app/                 the guarded dashboard at /app/*
│   │       └── dev/simulator/   scenario control panel (development only)
│   ├── components/
│   │   ├── shell/               sidebar, header, page chrome
│   │   ├── ui/                  shadcn components (CLI-managed)
│   │   └── ...
│   ├── lib/
│   │   ├── supabase/            browser, server, and proxy clients
│   │   └── api/                 typed client for the FastAPI backend
│   └── proxy.ts                 session refresh + route guards
│
├── backend/                     FastAPI, Python 3.11
│   ├── app/
│   │   ├── api/                 events, cases, playbooks, analytics, network,
│   │   │                        integrations, simulator
│   │   ├── agent/               the nine-step loop, bandit, causal DAG
│   │   ├── integrations/        Razorpay client and webhook verification
│   │   ├── simulator/           persona fixtures, event + reply generators,
│   │   │                        the nine scripted scenarios
│   │   ├── auth.py              Supabase JWT verification
│   │   └── deps.py              request-scoped user + Supabase client
│   └── tests/
│
├── supabase/
│   ├── migrations/              the frozen schema — later phases are additive
│   └── seed.sql                 unused: fixtures are per-merchant, so the
│                                simulator creates them at runtime
│
├── infra/                       Azure — Bicep template and setup scripts
│
├── docker-compose.yml           production-shaped stack
├── docker-compose.override.yml  backend hot reload, loaded automatically
└── docker-compose.prod.yml      the real production images, run locally
```

## Checks

```bash
cd frontend && npm run typecheck && npm run lint
cd backend  && poetry run pytest && poetry run mypy app/ && poetry run ruff check app/
```

Both run in CI on every pull request — see `.github/workflows/typecheck.yml`.

The database has its own check. `supabase/tests/rls_isolation.sql` applies the
migration to a throwaway Postgres and asserts that one merchant cannot read or
write another merchant's rows — see [`supabase/tests/README.md`](./supabase/tests/README.md).

## Simulator

There is no Razorpay webhook feed in development, so the simulator manufactures
one. Sign in, then open **Simulator** in the sidebar (`/app/dev/simulator`):

1. **Load demo fixtures** — creates the six persona customers from
   [`scenarios.md`](./scenarios.md), their payment methods, and the eight-customer
   cohort the SBI downtime beat needs. Idempotent; run it as often as you like.
2. **Fire a scenario** — S1–S6 each write one event and open one recovery case.
   B3 writes eight, for the cross-merchant downtime beat. B1 and B2 are the
   batch beats, driven from `/app/batch`.
3. **Inject a reply** — puts a customer reply on an open case, which is
   classified for intent (including opt-out and promise-to-pay) and fed back
   into the loop.
4. **Reset all data** — deletes everything the simulator created for your
   merchant. Customers you added yourself are left alone.

Two things worth knowing:

- The endpoints **404 outside a development environment**, whatever the frontend
  does. An enabled simulator in production would let anyone write fabricated
  cases into a live merchant's ledger.
- Every payload matches `scenarios.md` exactly, and
  `tests/simulator/test_payload_fidelity.py` reads that document to prove it. If
  the script changes and the generator does not, the build fails.

## Deployment

Both apps run on **Azure Container Apps**. Pushing to `main` builds each image,
pushes it to Azure Container Registry tagged with the commit SHA, points the
Container Apps at it, and verifies both are serving.

Setup, cost, teardown, logs, and the things that commonly go wrong are all in
[`infra/README.md`](./infra/README.md). The short version:

```bash
az login
# fill in the two public Supabase values in infra/main.parameters.json first
bash infra/setup-azure.sh recover-aa centralindia prod
bash infra/setup-github-secrets.sh
```

**Live URLs** — filled in after the first deployment; `setup-azure.sh` prints
both, and they are also on each Container App's overview page in the portal.

| | |
| --- | --- |
| Frontend | `https://<prefix>-prod-frontend.<region>.azurecontainerapps.io` |
| Backend | `https://<prefix>-prod-backend.<region>.azurecontainerapps.io` |

To run the production images locally before pushing — same Dockerfiles, same
build args, no Azure involved:

```bash
docker compose -f docker-compose.prod.yml up --build
```

## Submission checklist

Against the problem statement's bar:

- **Detects revenue at risk** — four event types across four playbooks, plus
  cross-merchant bank/method downtime detection in ~91s.
- **Determines the right intervention** — contextual Thompson bandit over per-
  playbook arms, conditioned on bank, method, hour and LTV band; every rejected
  alternative is on the case with its posterior.
- **Executes a bounded recovery workflow** — a nine-step loop with three early
  exits, per-action idempotency keys, and execution through Razorpay's rails.
- **Measures money recovered across a batch** — 1,000 synthetic cases:
  **₹14.8L gross, ₹9.2L incremental**, 35.2% settled recovery rate against a
  rule-based baseline on the same customers. Simulated cases, measured honestly.
- **Compliant escalation** — RBI retry ceilings, TRAI quiet hours, DPDP consent,
  and a human handoff that carries the case's history.
- **Stopping rules** — explicit opt-out, hardship signal, churn confirmation,
  max attempts per day and week, a hard day cap, and the RBI per-cycle limit.
- **Audit trail** — every decision, its reasoning, its alternatives, and every
  guardrail check, appended and never mutated.

The 300-word narrative is in
[`docs/submission-narrative.md`](./docs/submission-narrative.md).

## Phases

The full plan, phase by phase, is in [`phase-plan.md`](./phase-plan.md).
Scenario walkthroughs are in [`scenarios.md`](./scenarios.md).
