# Recover — Master Phase Plan

> **Purpose:** the end-to-end build plan, divided into 13 phases. Each phase ships something demonstrable, has explicit "done" criteria, and will get its own `phase-XX.md` file containing the Claude Code prompt to execute it.
>
> **Timeline:** 27 working days across 13 phases (fits into 22+ available days with buffer). Phases 1-6 = MUST-HAVE core. Phases 7-11 = SHOULD-HAVE differentiators. Phase 12 = NICE-TO-HAVE. Phase 13 = polish & submission.
>
> **Companion docs:** `plan.md` (product & architecture) + `scenarios.md` (turn-by-turn demo scripts). This doc is the *build sequence* that turns those into a shipped product.

---

## 1. Executive summary

We build **Recover** in 13 phases. The first 6 phases produce a working demo (MUST-HAVE): 3 personas, contextual bandit, LLM integration, compliance, live-deployed. The next 5 phases add differentiators (all playbooks, uplift, federated intelligence, batch runs). Phase 12 adds the causal DAG. Phase 13 is polish and video.

**Non-negotiables** enforced across every phase:
- **Contract-first**: DB schema and API contracts frozen in Phase 1. Every later phase reads/writes the same contract.
- **Ship every phase**: no "we built infra for a week." Each phase ends with something clickable and demoable.
- **Deploy early**: Phase 3 puts a live URL online. Every phase after auto-deploys.
- **Test scenarios as fixtures**: every persona in `scenarios.md` becomes a runnable end-to-end test.
- **Cache aggressively**: Gemini's free tier has 15 RPM limits — we pre-compute LLM outputs for the 6 scripted scenarios.

---

## 2. Tech stack (final decisions)

| Layer | Choice | Why |
|---|---|---|
| Frontend framework | **Next.js 14+ (App Router, TypeScript)** | Best-in-class DX, SSR, easy Azure deploy |
| UI components | **shadcn/ui + Tremor** | shadcn for base primitives; Tremor for dashboard-specific components (KPI cards, area charts, ROI panels) |
| Styling | **Tailwind CSS** | Utility-first, pairs with shadcn/Tremor |
| Icons | **Lucide React** | Clean, consistent |
| Charts | **Recharts + Tremor charts** | Recharts for custom; Tremor for standard dashboard views |
| Graph viz | **React Flow** | For the causal DAG visualization |
| Animation | **Framer Motion** | Micro-interactions, smooth transitions, counting numbers |
| Backend framework | **FastAPI (Python 3.11+)** | Best LLM/ML tooling ecosystem; async support; auto-OpenAPI |
| Database | **Supabase (PostgreSQL 15)** | Managed Postgres + built-in auth + realtime + generous free tier + brilliant dashboard for inspection |
| Auth | **Supabase Auth** | Email/password + magic link, JWT tokens, RLS integration |
| Cache & pubsub | **Upstash Redis** | Free-forever, HTTP-based (no persistent connection), works from anywhere |
| LLM | **Google Gemini 2.0 Flash** (free tier) | Free, supports structured JSON output via `responseSchema`, excellent Hinglish quality |
| Bandit | **Custom Thompson sampling in Python** (~200 LOC) | Simple, interpretable, no external dependency |
| Uplift modeling | **`causalml` library** | Microsoft's proven library; T-learner + X-learner support |
| Causal DAG | **`pgmpy` + hand-encoded nodes** | Lightweight Bayesian network library |
| Containers | **Docker + docker-compose** | Standard, portable |
| Deployment | **Azure Container Apps** (backend + frontend) + **Azure Cache for Redis** OR Upstash | Uses student credits, serverless containers, easy scaling |
| CI/CD | **GitHub Actions → Azure Container Registry → Azure Container Apps** | Native Azure integration |
| Secrets | **Azure Key Vault** (prod) + `.env.local` (dev) | Secure prod secrets |
| Observability | **Azure Application Insights** + structured JSON logs | Traces per case_id |

**Note on Supabase-inside-Azure:** Supabase is an external Postgres. That's fine — Azure Container Apps → Supabase over the public internet is a normal pattern. If we later want everything Azure-native, we can swap to Azure Database for PostgreSQL Flexible Server without changing app code (both are Postgres 15+).

---

## 3. Design system & UI philosophy

The UI carries as much of the "quality" signal as the code. Judges' first impression is visual.

### Aesthetic direction

**Reference points:** Stripe Dashboard, Linear, Vercel Dashboard, Razorpay Dashboard itself. Modern B2B fintech: whitespace-heavy, information-dense where it matters, muted-with-accent color palette, subtle motion.

### Color palette

```
Base surfaces
  --bg-primary:     #FAFAFA (near-white, warm)
  --bg-elevated:    #FFFFFF
  --bg-subtle:      #F4F4F5
  --border-subtle:  #E4E4E7
  --border-strong:  #D4D4D8

Text
  --text-primary:   #09090B
  --text-secondary: #52525B
  --text-tertiary:  #A1A1AA
  --text-inverse:   #FAFAFA

Brand (Razorpay-inspired but distinct)
  --brand:          #2563EB (deep blue)
  --brand-hover:    #1D4ED8
  --brand-subtle:   #EFF6FF

Semantic
  --success:        #10B981 (recovered)
  --success-subtle: #D1FAE5
  --warning:        #F59E0B (in flight, at risk)
  --warning-subtle: #FEF3C7
  --danger:         #EF4444 (stopped, violation)
  --danger-subtle:  #FEE2E2
  --info:           #6366F1 (holdout, exploration)
  --info-subtle:    #E0E7FF

Dark mode: full support via CSS variables, toggle in header.
```

### Typography

```
Sans (UI):      Inter (variable, self-hosted or via Google Fonts)
Mono (data):    JetBrains Mono (for JSON payloads, timestamps, code)
Display (hero): Inter with tighter tracking, larger sizes

Sizes (Tailwind scale):
  Body:     text-sm (14px)
  UI label: text-xs (12px)
  Metric:   text-3xl to text-5xl for hero numbers
  Section:  text-lg font-semibold
```

### Motion principles

- **Numbers count up**, not pop in (Framer Motion `useMotionValue` + `useTransform`)
- **List items stagger** in with 40ms delays
- **Bandit alternatives** fan out horizontally on reveal
- **Causal DAG edges** trace-animate along the diagnosis path
- **WhatsApp message bubbles** have a typing-dots interlude before rendering
- **All transitions**: 200-300ms, ease-out
- No bouncy easings, no gratuitous animation

### Imagery strategy

Real, human, India-specific:

- **Persona avatars:** DiceBear (`avataaars` or `notionists` style) — consistent, generated, ethnically diverse Indian representation
- **Merchant logos:** custom simple SVG marks we design per merchant (Kajal & Co. = lipstick outline, Zenith Learning = book+lightbulb, Sharma Distributors = crate icon)
- **Product images in scenarios:** Unsplash curated collections — skincare products for Kajal, textbooks/study for Zenith, food/oil crates for Sharma
- **Landing page hero:** short auto-playing muted MP4 loop of the dashboard in action (~10s loop), captured from actual product
- **Empty states:** custom illustrations via undraw.co (free, consistent style) — tinted to match brand color
- **Loading states:** skeleton screens, not spinners. Skeletons match the shape of the incoming content.

### Component inventory (what we build vs. install)

**Install from shadcn/ui (via CLI):** Button, Card, Dialog, DropdownMenu, Tabs, Table, Badge, Avatar, Alert, Toast, Sheet, Command (for cmd-k search), Select, Input, Label, Switch, Separator, Skeleton, Tooltip, Popover.

**Install from Tremor:** KPI cards, AreaChart, BarChart, DonutChart, Callout, ProgressBar.

**Build custom:**
- `CaseTimeline` — vertical timeline with agent step markers
- `CausalDagViewer` — React Flow wrapper with node highlighting
- `BanditAlternativesFan` — horizontal bar chart of arms with reasoning tooltips
- `WhatsAppBubble` — realistic WhatsApp UI for message previews
- `LiveTicker` — auto-incrementing counters via Framer Motion
- `NetworkHeatmap` — bank × hour cell grid with color grading
- `AuditLogEntry` — expandable JSON-highlighted row

### Screen inventory

| Screen | Route | Phase |
|---|---|---|
| Landing / marketing page | `/` | 8 |
| Login / signup | `/auth/*` | 1 |
| Dashboard home | `/app` | 1, 8 |
| Playbooks list | `/app/playbooks` | 7 |
| Playbook detail + config | `/app/playbooks/[slug]` | 7 |
| Cases list | `/app/cases` | 4, 8 |
| Case detail (the killer screen) | `/app/cases/[id]` | 4-6, 8, 12 |
| Network Intelligence | `/app/network` | 10 |
| Uplift & ROI | `/app/roi` | 9 |
| Audit log | `/app/audit` | 4, 8 |
| Batch results | `/app/batch` | 11 |
| Settings & merchant profile | `/app/settings` | 1 |
| Simulator control panel (dev only) | `/dev/simulator` | 2 |

---

## 4. Deployment architecture

### Local development
```
docker-compose.yml
├── frontend (Next.js dev server, port 3000)
├── backend  (FastAPI + uvicorn, port 8000)
├── redis    (Redis 7 for local pubsub/cache, port 6379)
└── .env files for both apps, pointing to Supabase (cloud) or a local Postgres
```

Supabase runs in the cloud (free tier) for both dev and prod — no local Postgres needed. This ensures dev/prod parity.

### Production on Azure
```
                            ┌─────────────────────┐
                            │  Azure Front Door   │
                            │  (CDN + WAF)        │
                            └──────────┬──────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                                     │
        ┌───────────▼──────────┐              ┌──────────▼──────────┐
        │  Azure Container App │              │ Azure Container App │
        │  frontend (Next.js)  │              │  backend (FastAPI)  │
        │  scale: 0-3          │              │  scale: 1-5         │
        └───────────┬──────────┘              └──────────┬──────────┘
                    │                                     │
                    │                          ┌──────────▼──────────┐
                    │                          │  Azure Cache for    │
                    │                          │  Redis (Basic C0)   │
                    │                          └──────────┬──────────┘
                    │                                     │
                    └─────────────────┬───────────────────┘
                                      │
                          ┌───────────▼───────────┐
                          │  Supabase             │
                          │  (Postgres + Auth)    │
                          └───────────────────────┘

Secrets: Azure Key Vault (LLM API key, Supabase service key, JWT secret)
Container Registry: Azure Container Registry (private)
CI/CD: GitHub Actions → build → push to ACR → update Container Apps
Observability: Azure Application Insights (traces, logs, metrics)
Custom domain: recover.yourdomain.com via Azure Front Door
```

**Scaling profile:**
- Frontend: 0-3 instances (Next.js is stateless; scale to zero when idle to save credits)
- Backend: 1-5 instances (keep 1 warm for demos)
- Concurrent requests per instance: 50 for frontend, 20 for backend

**Cost estimate (Azure student credits):** ~$8-15/month at demo traffic. Student credit ($100/year for standard student pack, $200 for GitHub Student Pack) more than covers this.

---

## 5. Database schema (the frozen contract)

Full schema is defined in `plan.md § 8`. Phase 1 creates a **single canonical migration** that establishes all tables at once. Every later phase either uses tables as-is, or adds *additive* migrations (new columns, new tables) — never breaking changes.

**Critical principle:** all tables get:
- `id` UUID PK (via `gen_random_uuid()`)
- `created_at` TIMESTAMPTZ default `now()`
- `updated_at` TIMESTAMPTZ (auto-updated via trigger)
- Appropriate `merchant_id` FK for multi-tenancy
- Row Level Security (RLS) policies enforcing "merchants see only their own data"

**Migration workflow:**
- SQL files in `supabase/migrations/YYYYMMDDHHMMSS_description.sql`
- Applied via `supabase db push`
- Each phase's `phase-XX.md` lists which migration(s) it introduces

---

## 6. API contracts (the frozen contract, part 2)

FastAPI backend exposes an OpenAPI 3.1 spec at `/openapi.json`. Frontend consumes types via `openapi-typescript` codegen. This guarantees frontend and backend never drift.

**API surface (finalized in Phase 1, additive-only after):**

```
Auth (handled by Supabase, not by our backend)

Merchant
  GET    /api/merchants/me
  PATCH  /api/merchants/me

Playbooks
  GET    /api/playbooks                  # list for current merchant
  GET    /api/playbooks/{slug}
  PATCH  /api/playbooks/{slug}/config
  POST   /api/playbooks/{slug}/toggle

Cases
  GET    /api/cases                       # filterable, paginated
  GET    /api/cases/{id}                  # full detail with timeline
  POST   /api/cases/{id}/override         # human override (pause/stop/escalate)

Events (webhook receiver)
  POST   /api/events/webhook              # Razorpay-shaped webhook ingestion

Simulator (dev-only, admin-guarded)
  POST   /api/simulator/scenarios/{code}  # fire a scripted scenario (S1..S6, B1..B3)
  POST   /api/simulator/batch/start       # start batch run of N cases
  GET    /api/simulator/batch/{id}        # batch status + results
  POST   /api/simulator/replies           # inject a customer reply for a case

Agent (internal — no external route, called by ingestor)
  # These are Python functions, not HTTP endpoints:
  # detect(event) → case
  # diagnose(case) → diagnosis
  # uplift_check(case, diagnosis) → verdict
  # decide(case, diagnosis, verdict) → decision
  # guardrail(decision) → check_result
  # execute(decision) → attempt
  # listen(reply) → classification
  # learn(case, outcome) → updates

Analytics
  GET    /api/analytics/overview          # live-ticker data
  GET    /api/analytics/funnel            # recovery funnel counts
  GET    /api/analytics/uplift            # incremental vs gross ROI
  GET    /api/analytics/bandit-curve      # bandit vs baseline over time

Network Intelligence
  GET    /api/network/heatmap             # bank × hour success rates
  GET    /api/network/alerts              # current + recent alerts
  WS     /api/network/alerts/stream       # websocket for live alerts

Audit
  GET    /api/audit                       # filterable log
  GET    /api/audit/case/{id}             # audit for one case

Realtime (via Supabase Realtime subscriptions from frontend directly)
  # Subscribe to: cases (per merchant), audit_events (per merchant)
```

Response schemas use camelCase in JSON despite Python snake_case internally (FastAPI's `alias_generator=to_camel`).

---

## 7. The 13 phases

Each phase below has: **Goal · Ships · Dependencies · Definition of Done · Files touched · Estimated effort**.

The `phase-XX.md` file for each phase (written later) will contain: full context (why now, what's already built), the exact Claude Code prompt, DB migrations, API contract additions, test cases from `scenarios.md`, and DoD checklist.

---

### Phase 1 — Foundations: Repo, DB, Docker, Auth, UI Shell
**Days:** 1-3 (3 days) · **Priority:** MUST · **Ships to:** local dev + Supabase

**Goal:** establish the entire skeleton so no later phase needs to touch setup.

**Ships:**
- Monorepo: `apps/frontend` (Next.js), `apps/backend` (FastAPI), `packages/shared-types` (TypeScript types + Python Pydantic mirrors), `supabase/migrations`
- `docker-compose.yml` running both apps locally
- Supabase project provisioned, all tables from `plan.md § 8` created via single migration, RLS enabled
- Supabase Auth wired to Next.js — sign-up, log-in, log-out, protected routes
- Design system: Tailwind + shadcn/ui installed, `globals.css` with color variables, base layout components (`AppShell`, `Sidebar`, `Header`, `PageContainer`)
- Empty-state dashboard home + Settings page (functional CRUD for merchant profile)
- README with local run instructions

**Dependencies:** none — this is the ground zero.

**Definition of Done:**
- [ ] `docker-compose up` starts both apps and they can reach each other
- [ ] Sign-up flow creates a Supabase user + a linked `merchants` row
- [ ] Login → land on `/app` dashboard shell
- [ ] Settings page can update merchant name and see it persist
- [ ] All tables from `plan.md § 8` exist in Supabase with RLS policies
- [ ] `openapi-typescript` codegen works and produces `packages/shared-types/api.d.ts`
- [ ] Design tokens visible: colors, typography, spacing all match the palette above
- [ ] Basic dark mode toggle works

**Files touched:** the entire scaffold.

---

### Phase 2 — Simulator & Fixtures
**Days:** 4-5 (2 days) · **Priority:** MUST · **Ships to:** local dev

**Goal:** every scenario in `scenarios.md` can be fired on demand into the system.

**Ships:**
- Event generator that produces webhook-shaped payloads for all 4 event types
- Reply generator for Hinglish/multilingual customer replies with known intent labels
- Fixture data for 3 merchants + 6 personas + ~100 supporting synthetic customers
- `POST /api/simulator/scenarios/{code}` endpoint firing S1..S6 end-to-end (payload only; agent processing comes in Phase 4)
- `POST /api/simulator/replies` endpoint injecting customer replies
- Simulator control panel at `/dev/simulator` — dropdown to pick scenario, "Fire" button, log tail
- Ground-truth `true_willingness_to_pay` recorded per synthetic customer for later uplift validation

**Dependencies:** Phase 1 (schema exists)

**Definition of Done:**
- [ ] Hitting `POST /api/simulator/scenarios/S1` inserts the exact event payload from `scenarios.md` into the `events` table
- [ ] All 6 personas exist in `customers` table with full metadata
- [ ] All 3 merchants exist with playbook configs
- [ ] Simulator control panel renders and can fire any scenario
- [ ] Payload matches `scenarios.md` byte-for-byte (verify with a snapshot test)

**Files touched:** `apps/backend/simulator/*`, `apps/frontend/app/dev/simulator/*`, `supabase/migrations/002_seed_fixtures.sql`.

---

### Phase 3 — Azure Deployment & CI/CD
**Days:** 6-7 (2 days) · **Priority:** MUST · **Ships to:** production

**Goal:** live URL online. Every subsequent commit auto-deploys.

**Ships:**
- Multi-stage `Dockerfile` for frontend (Next.js standalone output)
- Multi-stage `Dockerfile` for backend (Python 3.11-slim, gunicorn+uvicorn)
- Azure resource setup via Bicep template (idempotent, checked into repo):
  - Resource group
  - Azure Container Registry
  - Azure Container Apps environment (shared)
  - Frontend container app
  - Backend container app
  - Azure Cache for Redis (Basic C0)
  - Azure Key Vault
  - Azure Application Insights
- Secrets loaded from Key Vault into Container Apps
- GitHub Actions workflow: on push to `main` → build both images → push to ACR → update both Container Apps
- Custom domain via Azure Front Door (or free `*.azurecontainerapps.io` for MVP)
- Both apps live and callable, sign-up + login work in production

**Dependencies:** Phase 1 (apps exist), Phase 2 (simulator works locally)

**Definition of Done:**
- [ ] Frontend live at a public URL, loads without errors
- [ ] Backend live at a public URL, `/health` returns 200
- [ ] Sign-up works in production, creates merchant, persists to Supabase
- [ ] Push to `main` deploys automatically within 5 minutes
- [ ] Application Insights showing traces for backend requests
- [ ] Bicep template can rebuild the entire Azure setup from scratch

**Files touched:** `Dockerfile.frontend`, `Dockerfile.backend`, `.github/workflows/deploy.yml`, `infra/main.bicep`, `infra/README.md`.

---

### Phase 4 — Agent Core Loop (no AI yet)
**Days:** 8-9 (2 days) · **Priority:** MUST · **Ships to:** production

**Goal:** the 9-step agent loop skeleton runs end-to-end with rules-based stubs. No LLM, no bandit. Sets the shape everything else plugs into.

**Ships:**
- Agent core module: `agent/core.py` with the 9 steps as functions
- Detect step: route event → playbook
- Guardrail step: full RBI/TRAI/consent rule engine (deterministic)
- Execute step: simulated adapters for retry, payment_link, whatsapp_send, sms_send, email_send, mandate_reregister (write to DB, don't actually call external APIs)
- Audit step: writes to `audit_events` table for every decision, execution, outcome
- Diagnose stub: returns a fixed diagnosis (LLM comes in Phase 5)
- Uplift stub: always returns "PROCEED" (real model comes in Phase 9)
- Decide stub: rule-based (LLM + bandit come in Phases 5 & 6)
- Listen stub: hard-coded pattern match for "STOP" (LLM comes in Phase 5)
- Learn stub: no-op (bandit updates in Phase 6)
- Basic case detail page at `/app/cases/[id]` showing timeline of steps

**Dependencies:** Phase 3 (deployment), Phase 2 (simulator)

**Definition of Done:**
- [ ] Fire S6 (Sana STOP) via simulator → case created → guardrail passes → execute logs the whatsapp send → simulator injects "STOP" reply → listen stub matches → consent revoked → audit trail complete
- [ ] Case detail page shows the full timeline for any case
- [ ] All 9 agent steps produce audit_events entries with structured details
- [ ] Guardrail correctly blocks a message attempt during quiet hours (test case)
- [ ] Guardrail correctly blocks after opt-out (test case)

**Files touched:** `apps/backend/agent/*`, `apps/frontend/app/(app)/cases/[id]/page.tsx`, `apps/frontend/components/CaseTimeline.tsx`.

---

### Phase 5 — Gemini LLM Integration
**Days:** 10-11 (2 days) · **Priority:** MUST · **Ships to:** production

**Goal:** three LLM calls (diagnose evidence, message generation, reply classification) working with Gemini 2.0 Flash structured outputs. Response caching for the 6 scripted scenarios.

**Ships:**
- Gemini client wrapper with structured output via `responseSchema`
- Diagnosis LLM call — returns evidence JSON matching `scenarios.md` schemas
- Message generation LLM call — produces Hinglish WhatsApp/SMS/email copy
- Reply classification LLM call — classifies inbound customer replies
- Prompt template library (versioned, in `agent/prompts/*.py`)
- Response cache keyed on `sha256(prompt + params)` in Supabase table `llm_cache` — critical for demo (avoids rate limits, ensures reproducibility)
- Pre-warmed cache: run all 6 scenarios once locally, cache the outputs, commit the cache seed
- Fallback: if Gemini fails or returns invalid JSON, log the failure and use a scenario-specific default response

**Dependencies:** Phase 4 (agent loop shape)

**Definition of Done:**
- [ ] S6 Sana STOP now runs with real LLM classification of the "STOP" reply
- [ ] S2 Priya scenario generates a Hinglish WhatsApp message via Gemini
- [ ] Cache hits show latency <20ms; cache misses show real Gemini latency
- [ ] Structured JSON output enforced — no invalid JSON reaches the agent
- [ ] Case detail page shows LLM reasoning in an expandable section
- [ ] Gemini API key stored in Azure Key Vault

**Files touched:** `apps/backend/agent/prompts/*`, `apps/backend/agent/llm.py`, `apps/backend/agent/steps/diagnose.py`, `apps/backend/agent/steps/decide.py` (message gen part), `apps/backend/agent/steps/listen.py`.

---

### Phase 6 — Contextual Bandit + First Scenarios Working
**Days:** 12-13 (2 days) · **Priority:** MUST · **Ships to:** production

**Goal:** the bandit picks actions and learns from outcomes. Scenarios S1, S2, S3, S6 all work end-to-end and produce audit trails matching `scenarios.md`.

**Ships:**
- Thompson sampling bandit implementation (Beta-Bernoulli per arm × context bucket)
- Context feature extraction from cases (bank, method, hour, LTV bucket, etc.)
- Bandit decision path in `decide()` step
- Reward wiring: when a case closes as `recovered` or `stopped`, post reward to bandit
- Bandit alternatives displayed in case detail (which arms were considered, why chosen arm won)
- Bandit posteriors visualization: horizontal bar chart of arms with confidence intervals
- Merchant-visible bandit performance panel in playbook detail

**Dependencies:** Phase 5 (LLM), Phase 4 (agent skeleton)

**Definition of Done:**
- [ ] S1 Suresh — bandit picks `retry_at_inferred_date_plus_whatsapp_fallback`, retries succeed on day 6, reward posted
- [ ] S2 Priya — bandit picks 8% discount arm (not 5%, not 12%), WhatsApp sent, cart recovered
- [ ] S3 Aditya — bandit picks silent retry, no message sent, Monday retry succeeds
- [ ] S6 Sana — bandit picks initial WhatsApp, STOP received, hard stop honored
- [ ] Case detail page shows bandit alternatives with expected rewards for each
- [ ] Bandit posteriors visibly narrow after ~20 cases in the same context bucket (verify with test)

**Files touched:** `apps/backend/agent/bandit/*`, `apps/backend/agent/steps/decide.py` (bandit path), `apps/frontend/components/BanditAlternativesFan.tsx`.

**🎯 MUST-HAVE MILESTONE:** at end of Phase 6, we have a demoable product. Even if everything after this fails, we can submit.

---

### Phase 7 — All 4 Playbooks + All 6 Personas
**Days:** 14-15 (2 days) · **Priority:** SHOULD · **Ships to:** production

**Goal:** all four playbooks fully configured with their action spaces. Scenarios S4 (Meera) and S5 (Vikram) work.

**Ships:**
- Full playbook config for all 4 (action spaces, stopping rules, merchant-configurable caps)
- Playbook config UI at `/app/playbooks/[slug]` — merchant can toggle playbooks, adjust caps, view stats
- B2B invoice playbook working end-to-end (S4 Meera scenario)
- Subscription playbook handles churn signals (S5 Vikram scenario)
- Human handoff card generation for high-LTV churn cases
- Playbook-specific bandits (each playbook has its own bandit + reward space)

**Dependencies:** Phase 6 (bandit)

**Definition of Done:**
- [ ] S4 Meera — polite → firm sequence → LLM classifies promise-to-pay reply → partial payment → remainder tracked → full recovery
- [ ] S5 Vikram — WhatsApp sent → LLM classifies churn confirmation → stop + human handoff card generated
- [ ] All 4 playbooks toggleable from UI, config persists
- [ ] Playbook detail page shows recovery rate, in-flight cases, recent decisions

**Files touched:** `apps/backend/playbooks/*`, `apps/frontend/app/(app)/playbooks/*`.

---

### Phase 8 — Dashboard Polish: Case Detail, Audit, Timeline
**Days:** 16-17 (2 days) · **Priority:** SHOULD · **Ships to:** production

**Goal:** the merchant dashboard is *screenshot-worthy*. Every screen looks like a shipped product.

**Ships:**
- **Home dashboard** — live ticker (₹ at risk, ₹ recovered today, cases in flight), recovery funnel, playbook toggle row, real-time updates via Supabase Realtime
- **Case detail (the killer screen)** — full re-polish:
  - Vertical timeline with agent step markers
  - Bandit alternatives fan on the right, animated
  - LLM reasoning collapsible section with syntax-highlighted JSON
  - Customer profile card with consent status, past behavior
  - WhatsApp thread mockup with real message bubbles
  - Manual override buttons (pause, escalate, stop)
- **Cases list** — filterable table with status badges, quick preview drawer
- **Audit log** — filterable list with expandable JSON entries
- **Landing page at `/`** — hero with autoplay video loop of the dashboard, problem statement, "how it works" sections, CTA to sign up
- **Empty states everywhere** — no cases yet, no playbooks configured, no audit events
- **Loading states** — skeletons matching content shape
- **Error states** — graceful, actionable
- **Framer Motion polish** — counting numbers, staggered lists, smooth transitions
- **Dark mode** — every screen looks equally good in both modes

**Dependencies:** Phase 7 (all scenarios working)

**Definition of Done:**
- [ ] Every screen can be screenshotted for the submission one-pager without needing edits
- [ ] Home dashboard updates in real-time when a scenario fires
- [ ] Case detail is aesthetically at the level of Stripe/Linear/Vercel dashboards
- [ ] Landing page has autoplay hero video loop
- [ ] Dark mode toggle works globally
- [ ] All screens responsive (desktop primary; tablet acceptable; mobile graceful)

**Files touched:** widespread across `apps/frontend/app/*` and `apps/frontend/components/*`.

---

### Phase 9 — Uplift Modeling + ROI Panel
**Days:** 18-19 (2 days) · **Priority:** SHOULD · **Ships to:** production

**Goal:** we honestly report incremental vs gross recovery. B2 system beat is live.

**Ships:**
- Uplift holdout assignment: ~5% of eligible cases randomly assigned to holdout (no intervention, tracked for outcome)
- T-learner uplift model using `causalml` — trains nightly on accumulated data
- CATE estimates per context bucket
- Uplift check in agent loop: if estimated uplift × recovery amount < intervention cost, skip
- Uplift transparency page at `/app/roi`:
  - Gross vs incremental big numbers
  - Four-bucket breakdown (persuadable, sure thing, lost cause, DND)
  - Holdout methodology explainer
  - Confidence intervals
- Uplift bucket badge shown on case cards ("persuadable" / "would have paid anyway" / etc.)

**Dependencies:** Phase 7 (enough scenarios generating outcomes)

**Definition of Done:**
- [ ] B2 uplift ROI panel renders with real numbers from batch simulation
- [ ] Holdout group correctly excluded from intervention
- [ ] Uplift model trains without errors on accumulated data
- [ ] Batch simulation of 200+ cases produces distinguishable uplift buckets
- [ ] Case detail shows uplift bucket assignment with reasoning

**Files touched:** `apps/backend/ml/uplift/*`, `apps/backend/agent/steps/uplift_check.py`, `apps/frontend/app/(app)/roi/*`.

---

### Phase 10 — Federated Intelligence + Downtime Detection
**Days:** 20-21 (2 days) · **Priority:** SHOULD · **Ships to:** production

**Goal:** cross-merchant intelligence works. B3 SBI UPI downtime scenario runs live.

**Ships:**
- Network stats aggregation service (background job, updates every 60s from `bandit_rewards` + `execution_attempts`)
- Time-series anomaly detector (rolling z-score over 10-minute windows per bank×method)
- Redis pub/sub channel for network alerts
- Frontend websocket subscription for real-time alert display
- Network Intelligence dashboard at `/app/network`:
  - Bank × hour × method heatmap (color-graded cells)
  - Active alerts banner
  - Merchant-vs-vertical-benchmark comparison
  - Population priors panel
- Bandit prior update mechanism: when network alert fires, affected bandit contexts get updated priors (e.g., SBI UPI arm's expected reward drops)
- Simulator support: `POST /api/simulator/network/downtime` to inject a downtime event across N merchants

**Dependencies:** Phase 6 (bandit), Phase 8 (dashboard polish)

**Definition of Done:**
- [ ] B3 scenario — inject SBI UPI degradation across 8 merchants → alert fires within 90s → dashboard shows red alert → all pending SBI UPI retries are auto-paused → bandit switches to alternate methods → after 30 min sim time, alert resolves
- [ ] Network heatmap renders with realistic (bank × hour) success rates
- [ ] Merchants see cross-merchant benchmarks (their vs vertical median)

**Files touched:** `apps/backend/network/*`, `apps/frontend/app/(app)/network/*`.

---

### Phase 11 — Bandit Learning Curve + Batch Simulation
**Days:** 22-23 (2 days) · **Priority:** SHOULD · **Ships to:** production

**Goal:** B1 bandit-vs-baseline chart is live. Batch simulation of 1,000 cases produces the closing-shot numbers.

**Ships:**
- Fast-forward simulator mode (compresses 30 sim-days into ~90 seconds real time)
- Batch runner that fires 1,000 cases across merchants and playbooks
- Baseline runner: parallel-run an "LLM-only decision" policy for comparison
- Bandit learning curve data collection (recovery rate rolling window per policy)
- Batch results screen at `/app/batch`:
  - Bandit curve chart (B1 system beat)
  - Batch summary (revenue, compliance, ML performance)
  - Downloadable JSON export of the full batch
- Progress UI for batch runs (progress bar, ETA, live-updating metrics)

**Dependencies:** Phase 10 (federated ready for batch traffic)

**Definition of Done:**
- [ ] Batch run of 1,000 cases completes in <5 min wall clock
- [ ] B1 bandit learning curve chart shows clear cross-over of baseline
- [ ] Batch results page shows all the numbers from `scenarios.md` closing shot
- [ ] Batch run doesn't rate-limit Gemini (all LLM calls hit cache after first cycle)

**Files touched:** `apps/backend/simulator/batch.py`, `apps/frontend/app/(app)/batch/*`.

---

### Phase 12 — Causal DAG + Interpretability
**Days:** 24-25 (2 days) · **Priority:** NICE · **Ships to:** production

**Goal:** diagnosis is interpretable via causal graph traversal. Case detail shows the DAG lighting up.

**Ships:**
- Hand-encoded causal DAGs per playbook (10-20 nodes each) using `pgmpy` or hand-rolled Bayesian updater
- Prior probabilities loaded from historical stats
- Diagnosis step upgraded: causal DAG traversal replaces (or augments) the LLM-only diagnosis
- Case-specific posterior updates via Bayesian inference on observed features
- `CausalDagViewer` React component (React Flow) with:
  - Full DAG rendered as nodes + edges
  - Diagnosis path highlighted with animated edge tracing
  - Node posteriors shown as tooltips
  - Alternative hypotheses in a sidebar
- DAG structure editor for engineering team (JSON file, not merchant-facing)

**Dependencies:** Phase 8 (case detail screen exists)

**Definition of Done:**
- [ ] S1 Suresh case detail shows causal DAG with the salary-mismatch path lit up
- [ ] Alternative hypotheses (mandate revoked, account closed) shown with their probabilities
- [ ] DAG visualization is aesthetically at the level of the rest of the dashboard
- [ ] DAG updates its edge counts after cases resolve (learning)

**Files touched:** `apps/backend/agent/causal_dag/*`, `apps/frontend/components/CausalDagViewer.tsx`, `apps/backend/agent/steps/diagnose.py` (DAG path).

---

### Phase 13 — Final Polish, Video, Submission
**Days:** 26-27+ (2+ days) · **Priority:** MUST · **Ships to:** submission

**Goal:** everything is submission-ready. Video recorded. Deploy hardened.

**Ships:**
- End-to-end run of all 9 beats (6 personas + 3 system beats) with the exact timings from `scenarios.md`
- UI micro-polish based on video rehearsal (any awkward transitions, layout issues fixed)
- Performance profiling: LLM latencies, DB query performance, chart render times
- Cache warm-up script: pre-populate LLM cache for all 6 scripted scenarios before recording
- Deployment hardening: health checks, restart policies, resource limits, cost monitoring
- **Video capture:** screen record all 9 beats with narration, edit to 4:10 total
- **One-pager PDF:** problem, solution, why-Razorpay, results, architecture, ML methodology
- **README:** setup, architecture diagram, tech stack, how to run locally
- **Architecture diagram** (SVG in the README)
- **Submission form fill:** whatever Razorpay's form asks for
- Live demo URL, GitHub repo link, video URL

**Dependencies:** Phase 11 minimum (Phase 12 preferred)

**Definition of Done:**
- [ ] All 9 beats play back cleanly in sequence, matching `scenarios.md` timings
- [ ] Video is 4-5 min, uploaded to YouTube unlisted
- [ ] One-pager PDF finalized
- [ ] README lets a judge clone + run locally
- [ ] Live demo URL is stable, ≥99% uptime for the submission window
- [ ] Submission form submitted before deadline

**Files touched:** widespread polish, plus `README.md`, `docs/one-pager.pdf`, `docs/architecture.svg`.

---

## 8. Cross-cutting concerns

### Contract stability

- **DB schema** frozen at end of Phase 1. All later changes are additive (new columns nullable, new tables). Zero breaking changes. If a phase realizes it needs a schema change, that change adds columns; it doesn't drop or rename.
- **API contracts** frozen at end of Phase 1 for MVP endpoints. New endpoints are added freely; existing endpoints can add optional fields but never remove or rename.
- **TypeScript type codegen** runs on every backend change (`openapi-typescript` in a pre-commit hook) — frontend can never call an endpoint that doesn't exist.

### Testing strategy

- **Every scenario in `scenarios.md` is an integration test.** Located in `apps/backend/tests/scenarios/test_S1_suresh.py` etc. Each test fires the scenario, waits for completion, asserts the audit trail matches expected structure.
- **Unit tests** for pure functions: bandit math, guardrail rules, uplift buckets, DAG traversal.
- **Frontend visual tests:** Playwright screenshots of every key screen; catches accidental UI regressions.
- **Type safety:** strict TypeScript on frontend, mypy strict on backend.

### LLM cost & rate management

- **Cache first, always.** Every prompt+params hashes to a cache key. All 6 scripted scenarios have their LLM outputs cached before recording.
- **Batch simulation uses cache only.** No live LLM calls during a 1,000-case batch run.
- **Rate limiter** in front of Gemini client: max 12 req/min (conservative below 15 RPM limit).
- **Fallback:** if Gemini fails or returns invalid JSON, log and use a deterministic default. Never crash the agent.
- **Prompt tokens tracked** per case in the `agent_decisions` table (for cost analysis in the submission).

### Cost management (Azure)

- Container Apps set to scale-to-zero when idle (frontend can, backend keeps 1 warm).
- Redis Basic C0 (~$16/mo, well within student credits).
- Application Insights sampling at 20% for logs, 100% for exceptions.
- Bicep template outputs cost tags on every resource.

### Observability & debugging

- Every case gets a `trace_id` used in all structured logs and Application Insights spans.
- `debug=true` query param on case detail page shows full raw payloads for every step.
- Feature flags via env vars: `AGENT_USE_LLM=true`, `AGENT_USE_BANDIT=true`, `AGENT_USE_UPLIFT=true` — lets us swap components without redeploying.

---

## 9. What each `phase-XX.md` file will contain

When you say "give me Phase X", I'll produce `phase-XX.md` containing:

```
# Phase XX — [Title]

## Context (what's already built, what this phase adds)

## Deliverables (bulleted list from this master plan, expanded)

## New DB migrations (SQL files with exact contents)

## New API endpoints (OpenAPI additions with schemas)

## New/changed files (tree diff with brief descriptions)

## Test cases (from scenarios.md, made executable)

## Definition of Done (copy of this plan's DoD + expanded checklist)

## Design notes for UI phases (component structure, states, interactions)

## The Claude Code prompt

  A single, complete, self-contained prompt you can paste into Claude Code.
  It will:
  - Reference the sections above
  - Give explicit "touch these files, don't touch those" constraints
  - Include the DB migration SQL inline
  - Include example test invocations
  - Specify design tokens and component library to use
  - End with a checklist Claude Code should verify before completing

## Verification steps (how you'll manually confirm the phase is done)

## Common failure modes and fixes
```

Each `phase-XX.md` will be ~2-4K words. Standalone enough that you can hand it to Claude Code and it produces working code without needing to re-read the master plan.

---

## 10. Suggested cadence

Given 27 days of phase work and 22+ available days, we have ~5 days of slack. Recommended use:

- **Days 1-13:** Phases 1-6 (MUST-HAVE). Ship the working demo.
- **Days 14-21:** Phases 7-10 (SHOULD-HAVE differentiators).
- **Days 22-23:** Phase 11 (bandit curve + batch).
- **Days 24-25:** Phase 12 (causal DAG) — cut this if we're behind.
- **Days 26-27:** Phase 13 (polish + video).
- **Buffer days:** for the inevitable "the LLM cache broke" moments.

**Milestone commitments:**
- End of Day 13 → **demoable MVP live**, video-recordable
- End of Day 21 → **all differentiators live**, dashboard polished
- End of Day 27 → **submitted**

---

## 11. What we do next

You say **"Phase 1"** and I produce `phase-01.md` — the complete Claude Code prompt for the foundations phase (repo scaffolding, Supabase setup, Docker, Auth, UI shell). Then you paste it into Claude Code, it builds, you review, we iterate. Then you say "Phase 2" and we go again.

Recommended immediate next steps for you personally:
1. Create the GitHub repo (empty)
2. Create the Supabase project (free tier)
3. Set up Azure resources (Container Registry, Container Apps env) — or wait for Phase 3 to walk you through it
4. Provision a Gemini API key at https://aistudio.google.com/apikey
5. Say **"Phase 1"** to me

---

## Appendix A — Environment variables inventory

**Frontend (`apps/frontend/.env.local`):**
```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_BASE_URL=  # e.g. http://localhost:8000 or https://api.recover.dev
NEXT_PUBLIC_APP_URL=
```

**Backend (`apps/backend/.env`):**
```
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
GEMINI_API_KEY=
REDIS_URL=
JWT_SECRET=  # for verifying Supabase JWTs
LOG_LEVEL=INFO
AGENT_USE_LLM=true
AGENT_USE_BANDIT=true
AGENT_USE_UPLIFT=true
AGENT_USE_CAUSAL_DAG=false  # true after Phase 12
```

**Azure Key Vault (prod only):**
Everything from backend `.env` above (except URLs) goes into Key Vault; Container Apps reference secrets by name.

---

## Appendix B — Repository structure

```
recover/
├── apps/
│   ├── frontend/                 # Next.js 14 App Router
│   │   ├── app/
│   │   │   ├── (marketing)/      # public landing
│   │   │   ├── (auth)/           # auth routes
│   │   │   ├── (app)/            # authed dashboard
│   │   │   │   ├── layout.tsx    # AppShell + Sidebar
│   │   │   │   ├── page.tsx      # home dashboard
│   │   │   │   ├── cases/
│   │   │   │   ├── playbooks/
│   │   │   │   ├── network/
│   │   │   │   ├── roi/
│   │   │   │   ├── audit/
│   │   │   │   ├── batch/
│   │   │   │   └── settings/
│   │   │   └── dev/              # dev-only simulator control panel
│   │   ├── components/
│   │   │   ├── ui/               # shadcn/ui primitives
│   │   │   ├── charts/
│   │   │   └── domain/           # CaseTimeline, BanditFan, CausalDag, etc.
│   │   ├── lib/
│   │   │   ├── supabase/
│   │   │   ├── api/              # typed API client from openapi codegen
│   │   │   └── utils/
│   │   ├── styles/
│   │   ├── package.json
│   │   ├── next.config.js
│   │   ├── tailwind.config.ts
│   │   └── Dockerfile
│   └── backend/                  # FastAPI
│       ├── main.py               # app entry
│       ├── api/                  # route handlers
│       │   ├── merchants.py
│       │   ├── playbooks.py
│       │   ├── cases.py
│       │   ├── events.py
│       │   ├── simulator.py
│       │   ├── analytics.py
│       │   ├── network.py
│       │   └── audit.py
│       ├── agent/
│       │   ├── core.py           # 9-step orchestration
│       │   ├── steps/            # one file per step
│       │   ├── prompts/          # LLM prompt templates
│       │   ├── bandit/           # Thompson sampling
│       │   ├── causal_dag/       # per-playbook DAGs
│       │   ├── llm.py            # Gemini wrapper + cache
│       │   └── guardrail.py
│       ├── ml/
│       │   ├── uplift/           # T-learner
│       │   └── network/          # anomaly detector
│       ├── playbooks/            # per-playbook config + action definitions
│       ├── simulator/
│       │   ├── events.py
│       │   ├── replies.py
│       │   ├── batch.py
│       │   └── fixtures/         # seed data
│       ├── tests/
│       │   ├── scenarios/        # one test per S1..S6, B1..B3
│       │   └── unit/
│       ├── pyproject.toml
│       └── Dockerfile
├── packages/
│   └── shared-types/             # OpenAPI-generated TS + hand-written Pydantic
├── supabase/
│   ├── migrations/
│   │   ├── 001_initial_schema.sql
│   │   ├── 002_seed_fixtures.sql
│   │   └── ...                   # additive only
│   └── config.toml
├── infra/
│   ├── main.bicep                # Azure resources
│   └── README.md
├── .github/
│   └── workflows/
│       ├── deploy.yml
│       ├── test.yml
│       └── typecheck.yml
├── docs/
│   ├── plan.md                   # (already written)
│   ├── scenarios.md              # (already written)
│   ├── phase-plan.md             # this file
│   ├── phase-01.md               # each phase gets its own file
│   ├── phase-02.md
│   ├── ...
│   ├── architecture.svg
│   └── one-pager.pdf
├── docker-compose.yml
├── package.json                  # workspace root
└── README.md
```

---

**Ready to start. Say "Phase 1" when you want me to produce `phase-01.md`.**
