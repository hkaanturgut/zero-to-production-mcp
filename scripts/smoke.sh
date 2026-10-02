#!/usr/bin/env bash
# Post-deploy smoke test that needs no credentials:
#   1. the server is healthy
#   2. /mcp refuses anonymous calls with 401 + a resource_metadata pointer
#   3. Protected Resource Metadata names the expected authorization server
set -euo pipefail
MCP_URL="${1:?usage: smoke.sh https://host/mcp}"
BASE="${MCP_URL%/mcp}"

for i in $(seq 1 30); do
  curl -fsS "$BASE/healthz" >/dev/null && break
  sleep 5
done
curl -fsS "$BASE/healthz" | grep -q '"ok"' || { echo "healthz failed"; exit 1; }

HDRS_FILE=$(mktemp)
STATUS=$(curl -s -o /dev/null -D "$HDRS_FILE" -w '%{http_code}' -X POST "$MCP_URL" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}')
[ "$STATUS" = "401" ] || { echo "expected 401 for anonymous call, got $STATUS"; exit 1; }
grep -qi 'www-authenticate:.*resource_metadata=' "$HDRS_FILE" || { echo "missing resource_metadata"; exit 1; }
rm -f "$HDRS_FILE"

PRM=$(curl -fsS "$BASE/.well-known/oauth-protected-resource/mcp")
echo "$PRM" | grep -q 'authorization_servers' || { echo "bad PRM: $PRM"; exit 1; }
echo "smoke ok: $MCP_URL"
