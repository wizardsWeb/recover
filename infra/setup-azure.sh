#!/usr/bin/env bash
set -euo pipefail

# =====================================================================
# Recover — one-time Azure setup.
#
# What this creates:
#   • Resource group
#   • Service principal for GitHub Actions, scoped to that group
#   • The Bicep deployment (ACR, Container Apps environment, Key Vault,
#     Redis, Log Analytics, Application Insights, two Container Apps)
#
# Idempotent: re-running updates in place rather than failing. The one
# non-idempotent-looking step is the service principal, which is handled
# explicitly below.
#
# Prereqs:
#   • az login
#   • az account set --subscription "<id>"
#
# Usage:
#   bash infra/setup-azure.sh [prefix] [location] [environment]
#   bash infra/setup-azure.sh recover-aa centralindia prod
# =====================================================================

# Resolve paths from the script's own location, so this runs from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PREFIX="${1:-recover-aa}"          # lowercase, 3-12 chars, letters/digits/hyphen
LOCATION="${2:-centralindia}"      # centralindia / southindia keep latency low for Indian users
ENVIRONMENT_NAME="${3:-prod}"

RESOURCE_GROUP="${PREFIX}-${ENVIRONMENT_NAME}-rg"
SP_NAME="${PREFIX}-github-sp"

# ---------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------
if ! command -v az >/dev/null 2>&1; then
  echo "ERROR: Azure CLI not found. Install it: https://aka.ms/azure-cli" >&2
  exit 1
fi

if ! az account show >/dev/null 2>&1; then
  echo "ERROR: not logged in. Run: az login" >&2
  exit 1
fi

# Every resource name derives from this prefix, and the tightest constraint is
# the Key Vault's 24 characters against a "<prefix>-<environment>-kv" name — so
# main.bicep caps the parameter at 12. Catching a bad prefix here beats catching
# it four minutes into a deployment.
if [[ ! "$PREFIX" =~ ^[a-z][a-z0-9-]{2,11}$ ]]; then
  echo "ERROR: prefix must be lowercase, start with a letter, and be 3-12 chars of [a-z0-9-]." >&2
  exit 1
fi

echo "==> Configuration"
echo "    Prefix:         $PREFIX"
echo "    Location:       $LOCATION"
echo "    Environment:    $ENVIRONMENT_NAME"
echo "    Resource group: $RESOURCE_GROUP"
echo ""

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"
echo "    Subscription:   $SUBSCRIPTION_ID"
echo ""

# ---------------------------------------------------------------------
# 1. Resource providers
#
# A fresh subscription has these unregistered, and an unregistered provider
# fails the deployment several minutes in with a message that does not obviously
# say "register this". Registration is idempotent and asynchronous.
# ---------------------------------------------------------------------
echo "==> Registering resource providers (idempotent, async)..."
for provider in \
  Microsoft.App \
  Microsoft.ContainerRegistry \
  Microsoft.OperationalInsights \
  Microsoft.Insights \
  Microsoft.KeyVault \
  Microsoft.Cache \
  Microsoft.ManagedIdentity
do
  az provider register --namespace "$provider" --output none
  echo "    $provider"
done

# ---------------------------------------------------------------------
# 2. Resource group
# ---------------------------------------------------------------------
echo ""
echo "==> Creating resource group..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags project=recover environment="$ENVIRONMENT_NAME" \
  --output none

# ---------------------------------------------------------------------
# 3. Service principal for GitHub Actions
#
# `az ad sp create-for-rbac` does not fail on a name that already exists — Entra
# display names are not unique, so it would quietly create a *second* app
# registration every run. So look first, and reset the existing credential
# instead. `credential reset` has no --json-auth of its own (only
# create-for-rbac does), so the auth JSON is assembled here.
# ---------------------------------------------------------------------
echo ""
echo "==> Service principal for GitHub Actions..."
SP_SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP"
EXISTING_APP_ID="$(az ad sp list --display-name "$SP_NAME" --query '[0].appId' -o tsv 2>/dev/null || true)"

if [ -n "$EXISTING_APP_ID" ] && [ "$EXISTING_APP_ID" != "None" ]; then
  echo "    Exists ($EXISTING_APP_ID). Rotating its credential..."
  SP_PASSWORD="$(az ad sp credential reset --id "$EXISTING_APP_ID" --query password -o tsv)"
  SP_APP_ID="$EXISTING_APP_ID"

  # The role assignment may predate this run or may not exist at all; either way
  # this converges. A duplicate assignment is not an error worth stopping for.
  az role assignment create \
    --assignee "$SP_APP_ID" \
    --role Contributor \
    --scope "$SP_SCOPE" \
    --output none 2>/dev/null || true

  SP_JSON=$(cat <<JSON
{
  "clientId": "$SP_APP_ID",
  "clientSecret": "$SP_PASSWORD",
  "subscriptionId": "$SUBSCRIPTION_ID",
  "tenantId": "$TENANT_ID",
  "activeDirectoryEndpointUrl": "https://login.microsoftonline.com",
  "resourceManagerEndpointUrl": "https://management.azure.com/",
  "activeDirectoryGraphResourceId": "https://graph.windows.net/",
  "sqlManagementEndpointUrl": "https://management.core.windows.net:8443/",
  "galleryEndpointUrl": "https://gallery.azure.com/",
  "managementEndpointUrl": "https://management.core.windows.net/"
}
JSON
)
else
  echo "    Creating $SP_NAME..."
  SP_JSON="$(az ad sp create-for-rbac \
    --name "$SP_NAME" \
    --role Contributor \
    --scopes "$SP_SCOPE" \
    --json-auth)"
fi

echo ""
echo "======================================================================"
echo " SERVICE PRINCIPAL CREDENTIALS — copy this whole JSON."
echo " It is the AZURE_CREDENTIALS GitHub secret. It is shown once; the"
echo " secret cannot be read back, only rotated by re-running this script."
echo "======================================================================"
echo "$SP_JSON"
echo "======================================================================"
echo ""

# ---------------------------------------------------------------------
# 4. Bicep deployment
#
# The parameters file is supplied first and the CLI overrides after it, because
# az evaluates --parameters in order and the last assignment of a key wins.
# ---------------------------------------------------------------------
echo "==> Deploying Bicep template (this takes 10-20 minutes; Redis is the slow one)..."
DEPLOYMENT_NAME="recover-$(date +%Y%m%d%H%M%S)"
az deployment group create \
  --name "$DEPLOYMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --template-file "$SCRIPT_DIR/main.bicep" \
  --parameters "@$SCRIPT_DIR/main.parameters.json" \
  --parameters namePrefix="$PREFIX" environment="$ENVIRONMENT_NAME" location="$LOCATION" \
  --output none

# ---------------------------------------------------------------------
# 5. Report the outputs
#
# These are exactly the values the deploy workflow needs, so print them in the
# shape they will be pasted into.
# ---------------------------------------------------------------------
# Read back from the deployment this run created by name. `deployment group
# list` does not promise newest-first ordering, so picking [0] could report a
# previous run's outputs.
outputs() { az deployment group show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$DEPLOYMENT_NAME" \
  --query "properties.outputs.$1.value" -o tsv; }

ACR_NAME="$(outputs acrName)"
BACKEND_APP_NAME="$(outputs backendContainerAppName)"
FRONTEND_APP_NAME="$(outputs frontendContainerAppName)"
BACKEND_FQDN="$(outputs backendFqdn)"
FRONTEND_FQDN="$(outputs frontendFqdn)"
KEY_VAULT_NAME="$(outputs keyVaultName)"

echo ""
echo "==> Deployment complete."
echo ""
echo "    Backend:   https://$BACKEND_FQDN"
echo "    Frontend:  https://$FRONTEND_FQDN"
echo "    Key Vault: $KEY_VAULT_NAME"
echo ""
echo "==> GitHub Actions secrets — Settings > Secrets and variables > Actions:"
echo ""
echo "    AZURE_CREDENTIALS              <the JSON printed above>"
echo "    AZURE_SUBSCRIPTION_ID          $SUBSCRIPTION_ID"
echo "    AZURE_RESOURCE_GROUP           $RESOURCE_GROUP"
echo "    AZURE_LOCATION                 $LOCATION"
echo "    ACR_NAME                       $ACR_NAME"
echo "    BACKEND_APP_NAME               $BACKEND_APP_NAME"
echo "    FRONTEND_APP_NAME              $FRONTEND_APP_NAME"
echo "    NEXT_PUBLIC_SUPABASE_URL       <your Supabase project URL>"
echo "    NEXT_PUBLIC_SUPABASE_ANON_KEY  <your Supabase anon key>"
echo "    NEXT_PUBLIC_API_BASE_URL       https://$BACKEND_FQDN"
echo "    NEXT_PUBLIC_APP_URL            https://$FRONTEND_FQDN"
echo ""
echo "==> Next steps:"
echo "    1. Put the real secrets in Key Vault '$KEY_VAULT_NAME' — they are"
echo "       seeded as REPLACE_ME and the backend will not work until they are set:"
echo "         az keyvault secret set --vault-name $KEY_VAULT_NAME --name supabase-service-key --value '<key>'"
echo "         az keyvault secret set --vault-name $KEY_VAULT_NAME --name supabase-jwt-secret  --value '<secret>'"
echo "       (gemini-api-key can wait until Phase 5.)"
echo "    2. Point the backend's CORS at the real frontend URL:"
echo "         az deployment group create --resource-group $RESOURCE_GROUP \\"
echo "           --template-file infra/main.bicep \\"
echo "           --parameters @infra/main.parameters.json \\"
echo "           --parameters namePrefix=$PREFIX environment=$ENVIRONMENT_NAME location=$LOCATION \\"
echo "           --parameters frontendUrlHint=https://$FRONTEND_FQDN"
echo "    3. Run: bash infra/setup-github-secrets.sh"
echo "    4. Merge to main — the deploy workflow takes it from there."
