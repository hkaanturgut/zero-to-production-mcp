#!/usr/bin/env bash
# Stage helper. Every command the runbook uses, short enough to type on stage.
#   ./scripts/demo.sh setup            create .env (once) and local signing keys
#   ./scripts/demo.sh dms              run the mock dealer system on :8081
#   ./scripts/demo.sh live             run src/live/server.py on :8080, reloads on save
#   ./scripts/demo.sh token manager    print a local token (salesperson|manager|agent|readonly)
#   ./scripts/demo.sh chaos slow       break the DMS on purpose (slow|errors|flaky|off)
#   ./scripts/demo.sh reset            fresh demo data, chaos off
#   ./scripts/demo.sh inspector        open MCP Inspector
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ] && [ "${1:-}" != "setup" ]; then
  echo "Run ./scripts/demo.sh setup first"; exit 1
fi
[ -f .env ] && { set -a; . ./.env; set +a; }

dms_post() {
  curl -fsS -X POST "${DMS_BASE_URL}$1" -H "X-API-Key: ${DMS_API_KEY}" \
    -H 'Content-Type: application/json' -d "${2:-{\}}"; echo
}

case "${1:-}" in
  setup)
    [ -f .env ] || { cp .env.example .env; sed -i.bak "s/change-me-long-random-string/$(openssl rand -hex 32)/" .env && rm -f .env.bak; }
    uv sync -q && uv run dev-token salesperson >/dev/null && echo "ready: .env and .dev/ keys created" ;;
  dms)       exec uv run dms ;;
  live)      exec uv run uvicorn live.server:app --app-dir src --port 8080 --reload --reload-dir src/live ;;
  reference) exec uv run server ;;
  token)     uv run dev-token "${2:-salesperson}" ;;
  chaos)     dms_post /_chaos "{\"mode\": \"${2:?slow|errors|flaky|off}\"}" ;;
  reset)     dms_post /_reset ;;
  inspector) exec npx -y @modelcontextprotocol/inspector ;;
  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
