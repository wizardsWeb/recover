#!/usr/bin/env bash
set -euo pipefail

# =====================================================================
# Recover — GitHub Actions secrets walkthrough.
#
# Prints every secret .github/workflows/deploy.yml needs, and sets them
# for you if the GitHub CLI is available.
#
# Run infra/setup-azure.sh first: it prints most of these values already
# filled in, including the two Container App FQDNs.
#
# Indexed arrays rather than an associative array on purpose. macOS ships
# bash 3.2, where `declare -A` does not exist — and the order matters
# here anyway, which an associative array would not preserve.
# =====================================================================

KEYS=(
  AZURE_CREDENTIALS
  AZURE_SUBSCRIPTION_ID
  AZURE_RESOURCE_GROUP
  AZURE_LOCATION
  ACR_NAME
  BACKEND_APP_NAME
  FRONTEND_APP_NAME
  NEXT_PUBLIC_SUPABASE_URL
  NEXT_PUBLIC_SUPABASE_ANON_KEY
  NEXT_PUBLIC_API_BASE_URL
  NEXT_PUBLIC_APP_URL
)

DESCS=(
  "The whole service principal JSON from setup-azure.sh. Multi-line — supplied as a file path below, not typed."
  "Azure subscription id: az account show --query id -o tsv"
  "Resource group, e.g. recover-aa-prod-rg"
  "Azure region, e.g. centralindia"
  "ACR name from the Bicep outputs, e.g. recoveraaprodacr"
  "Backend Container App name, e.g. recover-aa-prod-backend"
  "Frontend Container App name, e.g. recover-aa-prod-frontend"
  "Supabase project URL. Baked into the browser bundle at build time."
  "Supabase anon key. Public — RLS is what protects the data."
  "Backend Container App FQDN, with the https:// prefix"
  "Frontend Container App FQDN, with the https:// prefix"
)

echo "==> GitHub Actions secrets needed by .github/workflows/deploy.yml"
echo "    Settings > Secrets and variables > Actions"
echo ""
for i in "${!KEYS[@]}"; do
  printf "  %s\n      %s\n\n" "${KEYS[$i]}" "${DESCS[$i]}"
done

# ---------------------------------------------------------------------
# Offer to set them, if gh is present and pointed at a repo
# ---------------------------------------------------------------------
if ! command -v gh >/dev/null 2>&1; then
  echo "==> GitHub CLI not installed — set the above by hand in the web UI."
  echo "    (brew install gh, then re-run this script to do it from here.)"
  exit 0
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "==> GitHub CLI is installed but not authenticated. Run: gh auth login"
  exit 0
fi

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
if [ -z "$REPO" ]; then
  echo "==> Could not determine the GitHub repository from this directory."
  echo "    Run this from inside the repo, or set the secrets in the web UI."
  exit 0
fi

echo "==> GitHub CLI is ready. Set these secrets on $REPO now? [y/N]"
read -r REPLY
case "$REPLY" in
  y|Y) ;;
  *) echo "    Skipped. Nothing was changed."; exit 0 ;;
esac

echo ""
echo "    Leave any answer blank to skip that secret and keep its current value."
echo ""

for i in "${!KEYS[@]}"; do
  KEY="${KEYS[$i]}"

  # AZURE_CREDENTIALS is a multi-line JSON document. `read` is line-oriented,
  # so it is taken as a file path and piped in whole.
  if [ "$KEY" = "AZURE_CREDENTIALS" ]; then
    printf "Path to the service principal JSON file for %s (blank to skip): " "$KEY"
    read -r SP_FILE
    if [ -z "$SP_FILE" ]; then
      echo "    skipped $KEY"
      continue
    fi
    if [ ! -f "$SP_FILE" ]; then
      echo "    ERROR: no file at '$SP_FILE' — skipping $KEY" >&2
      continue
    fi
    gh secret set "$KEY" --repo "$REPO" < "$SP_FILE"
    echo "    set $KEY"
    continue
  fi

  # The rest are not secret — a resource group name, a region, a public anon
  # key — so they are echoed as typed. A silent read here would hide typos in
  # values that later fail as a confusing 404 mid-deployment.
  printf "%-30s: " "$KEY"
  read -r VALUE
  if [ -z "$VALUE" ]; then
    echo "    skipped $KEY"
    continue
  fi
  gh secret set "$KEY" --repo "$REPO" --body "$VALUE"
  echo "    set $KEY"
done

echo ""
echo "==> Done. Confirm with: gh secret list --repo $REPO"
