# Recover — Infrastructure

Everything here deploys the stack to **Azure Container Apps**, with GitHub
Actions building and shipping images on every push to `main`.

```
  push to main
       │
       ▼
┌──────────────────────┐   docker build + push   ┌───────────────────────┐
│  GitHub Actions      │ ──────────────────────► │  Azure Container      │
│  .github/workflows/  │                         │  Registry             │
│  deploy.yml          │                         └───────────┬───────────┘
└──────────┬───────────┘                                     │ admin creds
           │  az containerapp update --image <sha>           │ (a secret on
           ▼                                                 ▼  each app)
┌──────────────────────────────────────────────────────────────────────┐
│  Container Apps environment                                          │
│                                                                      │
│   frontend  :3000  ──►  backend  :8000  ──►  Key Vault (via UAMI)    │
│   Next standalone       FastAPI              Supabase keys, Redis    │
│                                                                      │
│   logs ──► Log Analytics ──► Application Insights                    │
└──────────────────────────────────────────────────────────────────────┘
```

## Files

| File | What it is |
| --- | --- |
| `main.bicep` | Every Azure resource, declaratively. Re-running updates in place. |
| `main.parameters.json` | The two public Supabase values. **Placeholders — fill in locally, do not commit real ones.** |
| `setup-azure.sh` | One-time: resource group, service principal, first deployment. |
| `setup-github-secrets.sh` | Guided walkthrough for the GitHub Actions secrets. |
| `../.github/workflows/deploy.yml` | Build, push, deploy, verify. |

## Prerequisites

- An Azure subscription with rights to create a service principal
- [Azure CLI](https://aka.ms/azure-cli) 2.60 or newer — `az version`
- Bicep — `az bicep install` (the CLI installs it on first use anyway)
- Optionally [GitHub CLI](https://cli.github.com/) `gh`, to set secrets from the terminal
- A working Supabase project (see the root README)

## First-time setup

**1. Sign in and pick a subscription.**

```bash
az login
az account set --subscription "<your subscription id>"
```

**2. Fill in the public Supabase values.**

Edit `infra/main.parameters.json` and replace both placeholders:

```json
"supabaseUrl":     { "value": "https://<your-ref>.supabase.co" },
"supabaseAnonKey": { "value": "eyJ..." }
```

Neither is a secret — the anon key ships in the browser bundle, and RLS is what
protects the data. They stay as placeholders in git anyway, so nobody has to
wonder whether a real value in a diff is one that matters.

**3. Run the setup script.**

```bash
bash infra/setup-azure.sh recover-aa centralindia prod
#                         ^prefix    ^region      ^environment
```

The prefix must be lowercase, start with a letter, and be 3–12 characters.
Twelve is not arbitrary: every resource name derives from it, and Key Vault
allows 24 characters for a `<prefix>-<environment>-kv` name.

It registers the resource providers, creates the resource group and the
service principal, and runs the Bicep deployment. Budget **10–20 minutes** —
Redis is the slow part.

**4. Copy the service principal JSON.**

The script prints it once, between two rule lines. It is the `AZURE_CREDENTIALS`
secret. It cannot be read back afterwards — only rotated by re-running the
script.

**5. Put the real secrets in Key Vault.**

Bicep seeds these as the literal string `REPLACE_ME`, so that no genuine
credential is ever in this repository or in an Azure deployment history. **The
backend cannot authenticate a single request until these are set.**

```bash
VAULT=recover-aa-prod-kv

az keyvault secret set --vault-name $VAULT --name supabase-service-key --value '<service_role key>'
az keyvault secret set --vault-name $VAULT --name supabase-jwt-secret  --value '<JWT secret>'
# gemini-api-key can stay REPLACE_ME until Phase 5.
```

Both come from **Supabase → Project Settings → API**.

Container Apps caches a resolved secret for the life of a revision, so set
these *before* the first deploy — or force a new revision afterwards:

```bash
az containerapp revision restart \
  --name recover-aa-prod-backend --resource-group recover-aa-prod-rg \
  --revision "$(az containerapp revision list --name recover-aa-prod-backend \
      --resource-group recover-aa-prod-rg --query '[0].name' -o tsv)"
```

**6. Set the GitHub secrets.**

```bash
bash infra/setup-github-secrets.sh
```

It lists all eleven with descriptions, and sets them for you if `gh` is
installed and authenticated. `setup-azure.sh` has already printed most of the
values, including both Container App FQDNs.

**7. Merge to `main`.**

The deploy workflow runs on every push to `main`. Watch it under the repo's
**Actions** tab. The first run replaces the placeholder hello-world image on
each app with a real one.

## What Bicep creates

| Resource | Notes |
| --- | --- |
| Container Registry | Basic. Admin user enabled — that credential is how the Container Apps pull. |
| Log Analytics workspace | 30-day retention. Every container's stdout lands here. |
| Application Insights | Workspace-backed. Connection string is passed to the backend. |
| Container Apps environment | Consumption workload profile. |
| Redis | Basic C0, 250 MB. Unused until a later phase; provisioned now so the connection string is already in Key Vault. |
| Key Vault | RBAC-authorised. Soft delete on, purge protection deliberately off. |
| 2 × user-assigned identity | One per app. Only the backend's is granted vault access. |
| 2 × Container App | `minReplicas: 1` — scale-to-zero would put a cold start in front of the first request of a demo. |

## Cost

Rough monthly figures for `centralindia`, with both apps at one always-on
replica of 0.5 vCPU / 1 GiB. Treat them as an order of magnitude, not a quote —
check the [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/)
for current rates in your region.

| Resource | Approx / month |
| --- | --- |
| Container Apps (2 apps, 1 replica each) | $25–45 — the free grant of vCPU- and GiB-seconds covers a meaningful slice |
| Container Registry (Basic) | ~$5 |
| Redis (Basic C0) | ~$16 |
| Log Analytics | $0 at low volume — the first 5 GB/month of ingestion is free |
| Key Vault | cents |
| **Total** | **roughly $45–70** |

Two ways to cut it materially:

- **Drop Redis** until the phase that needs it. Comment out the `redis` resource
  and the `redis-url` secret and you save the largest fixed line item.
- **Set `minReplicas: 0`** on both apps between demos. You then pay near nothing
  when idle, at the price of a cold start on the first request.

## Teardown

The resource group is the unit of deletion. This removes **everything**,
including the registry and its images.

```bash
az group delete --name recover-aa-prod-rg --yes --no-wait
```

The Key Vault survives in a soft-deleted state for 7 days. To reuse the same
vault name before then:

```bash
az keyvault purge --name recover-aa-prod-kv --location centralindia
```

## Logs and diagnostics

```bash
RG=recover-aa-prod-rg

# Follow the backend's stdout
az containerapp logs show --name recover-aa-prod-backend --resource-group $RG --follow

# The last 100 lines, without following
az containerapp logs show --name recover-aa-prod-backend --resource-group $RG --tail 100

# Container Apps' own view of what happened to a revision — image pull
# failures and probe failures show up here, not in the app logs
az containerapp logs show --name recover-aa-prod-backend --resource-group $RG --type system

# Which revision is live, and is it healthy
az containerapp revision list --name recover-aa-prod-backend --resource-group $RG \
  --query "[].{name:name, active:properties.active, replicas:properties.replicas, image:properties.template.containers[0].image}" -o table

# Every env var the running container sees (secret values are shown as refs)
az containerapp show --name recover-aa-prod-backend --resource-group $RG \
  --query "properties.template.containers[0].env" -o table
```

The backend logs structured JSON, one object per line, each carrying a
`trace_id` that the API also returns as an `X-Trace-Id` response header. To
follow one request end to end, in Log Analytics:

```kusto
ContainerAppConsoleLogs_CL
| where Log_s contains "<the trace id from the response header>"
| order by TimeGenerated asc
```

## Common issues

**`The subscription is not registered to use namespace 'Microsoft.App'`**
A provider is unregistered. `setup-azure.sh` registers all seven, but
registration is asynchronous — wait a minute and re-run. To check:
`az provider show --namespace Microsoft.App --query registrationState -o tsv`

**Deployment fails on the Key Vault name**
A vault of that name is soft-deleted from an earlier run. Either purge it
(`az keyvault purge --name <name> --location <region>`) or use a different
prefix.

**The first revision never becomes healthy**
Almost always one of three things. Check `--type system` logs first.
1. The Key Vault secrets are still `REPLACE_ME`, so the app starts and then
   fails every Supabase call.
2. The image pull failed — confirm ACR admin user is enabled and the
   `acr-password` secret on the app is current.
3. The readiness probe is failing. `GET /health` should answer in milliseconds
   from process state alone; if it does not, something in startup is blocking.

**CORS errors in the browser once deployed**
`ALLOWED_ORIGINS` on the backend must contain the frontend origin, scheme
included, with no trailing slash. Bicep computes it from the environment's
default domain, so it is right unless the frontend is behind a custom domain —
in which case redeploy with `frontendUrlHint=https://your-domain`.

Note that CORS is handled **only** by FastAPI. There is deliberately no
`corsPolicy` on the Container Apps ingress: the ingress is Envoy, and its CORS
filter would append a second `Access-Control-Allow-Origin` to a response that
FastAPI already set one on — which browsers reject. If you find yourself adding
one, remove the FastAPI middleware in the same change.

**The frontend shows `Missing NEXT_PUBLIC_SUPABASE_URL`**
Those values are inlined by `next build`, not read at runtime. Setting them on
the Container App does nothing. They are `--build-arg`s in `deploy.yml`, fed
from GitHub secrets — check the secrets, then re-run the workflow.

**The simulator 404s on the deployed site**
Working as intended. `ENVIRONMENT=production` disables the simulator router
entirely, because an enabled simulator in production would let anyone write
fabricated cases into a live merchant's ledger.

To demo it live, move the backend to an environment name the router accepts —
`local`, `development`, `test`, or `staging`:

```bash
az containerapp update --name recover-aa-prod-backend --resource-group $RG \
  --set-env-vars ENVIRONMENT=staging
```

The sidebar link is separately gated on `NEXT_PUBLIC_ENVIRONMENT === "local"`,
which is a build-time value — so navigate to `/app/dev/simulator` directly, or
rebuild the frontend image with that build arg changed. **Move it back before
showing the site to anyone whose data you care about.**

## Changing infrastructure

CI never touches `main.bicep` — it only swaps container images. A change to
infrastructure means re-running the deployment:

```bash
az deployment group create \
  --resource-group recover-aa-prod-rg \
  --template-file infra/main.bicep \
  --parameters @infra/main.parameters.json \
  --parameters namePrefix=recover-aa environment=prod location=centralindia
```

Check what it would do first with `--what-if` in place of running it.
