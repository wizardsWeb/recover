# Recover — AI Revenue Recovery Agent

[![Typecheck](https://github.com/wizardsWeb/razorpay_buildathon/actions/workflows/typecheck.yml/badge.svg)](https://github.com/wizardsWeb/razorpay_buildathon/actions/workflows/typecheck.yml)
[![Deploy](https://github.com/wizardsWeb/razorpay_buildathon/actions/workflows/deploy.yml/badge.svg)](https://github.com/wizardsWeb/razorpay_buildathon/actions/workflows/deploy.yml)

Recover is a merchant-side agent for Razorpay sellers that watches for revenue
slipping away — failed payments, abandoned checkouts, broken subscription
mandates, overdue B2B invoices — diagnoses why each one happened, and works it
back. It decides with a contextual bandit, explains every step it took, honours
every opt-out, and reports what it earned against a holdout group rather than
against raw totals.

This repository is at **Phase 3: Deployment** — schema, auth, API surface, the
UI shell, the scenario simulator, and a CI/CD pipeline onto Azure Container
Apps. The agent itself arrives in Phase 4.

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
│   │   ├── api/                 health, merchants, simulator
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
   B3 writes eight. B1 and B2 are batch beats that land in Phase 11 and write
   nothing until then.
3. **Inject a reply** — puts a customer reply on an open case. Classification
   arrives in Phase 5; for now the row is stored raw.
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

## Phases

The full plan, phase by phase, is in [`phase-plan.md`](./phase-plan.md).
Scenario walkthroughs are in [`scenarios.md`](./scenarios.md).
