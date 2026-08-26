# Recover — AI Revenue Recovery Agent

Recover is a merchant-side agent for Razorpay sellers that watches for revenue
slipping away — failed payments, abandoned checkouts, broken subscription
mandates, overdue B2B invoices — diagnoses why each one happened, and works it
back. It decides with a contextual bandit, explains every step it took, honours
every opt-out, and reports what it earned against a holdout group rather than
against raw totals.

This repository is at **Phase 1: Foundations** — schema, auth, API surface, and
the UI shell. The agent itself arrives in Phase 4.

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
│   │   ├── api/                 health, merchants
│   │   ├── auth.py              Supabase JWT verification
│   │   └── deps.py              request-scoped user + Supabase client
│   └── tests/
│
├── supabase/
│   ├── migrations/              the frozen schema — later phases are additive
│   └── seed.sql                 fixtures land here in Phase 2
│
├── docker-compose.yml           production-shaped stack
└── docker-compose.override.yml  backend hot reload, loaded automatically
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

## Phases

The full plan, phase by phase, is in [`phase-plan.md`](./phase-plan.md).
Scenario walkthroughs are in [`scenarios.md`](./scenarios.md).
