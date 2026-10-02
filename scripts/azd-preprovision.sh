#!/bin/sh
# Generate the MCP-server-to-DMS service key once per azd environment.
# It lives in .azure/<env>/.env (git-ignored) and in Key Vault, nowhere else.
set -e
if [ -z "$(azd env get-value DMS_API_KEY 2>/dev/null || true)" ] || azd env get-value DMS_API_KEY 2>&1 | grep -qi "not found"; then
  azd env set DMS_API_KEY "$(openssl rand -hex 32)" >/dev/null
  echo "Generated DMS_API_KEY for this environment."
fi
