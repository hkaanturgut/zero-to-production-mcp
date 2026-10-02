#!/usr/bin/env bash
# Roll one already-scanned image out to both container apps of an environment.
# Same image, two entry points (APP_ENTRY is set per app in Bicep).
#   usage: ci-deploy-image.sh <registry>/dealer-mcp:<sha>
set -euo pipefail
IMAGE="${1:?usage: ci-deploy-image.sh <image>}"
: "${AZURE_ENV_NAME:?}"
rg="rg-$AZURE_ENV_NAME"

# DMS first: the MCP server depends on it, never the other way around.
for svc in dms mcp; do
  echo "Deploying $IMAGE to ca-$svc-$AZURE_ENV_NAME"
  az containerapp update -g "$rg" -n "ca-$svc-$AZURE_ENV_NAME" --image "$IMAGE" \
    --revision-suffix "r${GITHUB_RUN_NUMBER:-0}a${GITHUB_RUN_ATTEMPT:-1}" -o none
done
