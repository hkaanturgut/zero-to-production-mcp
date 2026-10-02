#!/bin/sh
# Mirror the Python base image into our own registry once, so builds never
# depend on Docker Hub rate limits (enterprise habit; also saves you on venue Wi-Fi).
set -e
ACR_NAME="$(echo "$AZURE_CONTAINER_REGISTRY_ENDPOINT" | cut -d. -f1)"
if az acr repository show --name "$ACR_NAME" --image base/python:3.11-slim >/dev/null 2>&1; then
  echo "Base image already mirrored in $ACR_NAME."
else
  echo "Mirroring python:3.11-slim into $ACR_NAME ..."
  az acr import --name "$ACR_NAME" \
    --source docker.io/library/python:3.11-slim \
    --image base/python:3.11-slim --force \
  || echo "WARNING: base image import failed; builds will pull from Docker Hub."
fi
echo
echo "MCP endpoint: $MCP_URL"

# Point the "dealer-cloud" server in .vscode/mcp.json at this environment.
if [ -f .vscode/mcp.json ] && [ -n "$MCP_URL" ]; then
  python3 - "$MCP_URL" <<'PY'
import json, sys
path = ".vscode/mcp.json"
cfg = json.load(open(path))
cfg["servers"]["dealer-cloud"]["url"] = sys.argv[1]
json.dump(cfg, open(path, "w"), indent=2)
print("Updated .vscode/mcp.json -> dealer-cloud =", sys.argv[1])
PY
fi
