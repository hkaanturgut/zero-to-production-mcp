#!/usr/bin/env bash
# Rebuild the azd environment on a fresh CI runner (nothing persists between runs).
#
#   * creates .azure/$AZURE_ENV_NAME pointing at the right subscription and region
#   * injects the stable DMS_API_KEY from the GitHub environment secret
#     (so the preprovision hook never generates a new one and rotates the key)
#   * tells Bicep whether the container apps already exist, so provisioning
#     keeps the deployed image instead of resetting it to the placeholder
#
# Writes first_deploy=true|false to $GITHUB_OUTPUT.
set -euo pipefail
: "${AZURE_ENV_NAME:?}" "${AZURE_LOCATION:?}" "${AZURE_SUBSCRIPTION_ID:?}" "${DMS_API_KEY:?DMS_API_KEY secret missing on this GitHub environment}"

azd env new "$AZURE_ENV_NAME" --subscription "$AZURE_SUBSCRIPTION_ID" --location "$AZURE_LOCATION" --no-prompt >/dev/null 2>&1 \
  || azd env select "$AZURE_ENV_NAME"
azd env set DMS_API_KEY "$DMS_API_KEY" >/dev/null
azd env set ASSIGN_MANAGER_ROLE false >/dev/null
azd env set ACR_ALLOWED_IPS "$(./scripts/acr-service-ips.sh "$AZURE_LOCATION")" >/dev/null
azd env set AZURE_PRINCIPAL_TYPE ServicePrincipal >/dev/null

rg="rg-$AZURE_ENV_NAME"
first=false
for svc in mcp dms; do
  upper=$(echo "$svc" | tr '[:lower:]' '[:upper:]')
  image=$(az containerapp show -g "$rg" -n "ca-$svc-$AZURE_ENV_NAME" \
            --query "properties.template.containers[0].image" -o tsv 2>/dev/null || true)
  if [ -n "$image" ] && [[ "$image" != mcr.microsoft.com/* ]]; then
    azd env set "SERVICE_${upper}_RESOURCE_EXISTS" true >/dev/null
    echo "$svc: running $image"
  else
    azd env set "SERVICE_${upper}_RESOURCE_EXISTS" false >/dev/null
    first=true
    echo "$svc: not deployed yet"
  fi
done
echo "first_deploy=$first" >> "${GITHUB_OUTPUT:-/dev/null}"
