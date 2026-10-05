#!/usr/bin/env bash
# Stage helper. Every command the runbook uses, short enough to type on stage.
#   ./scripts/demo.sh setup            create .env (once) and local signing keys
#   ./scripts/demo.sh dms              run the mock dealer system on :8081
#   ./scripts/demo.sh live             run src/live/server.py on :8080, reloads on save
#   ./scripts/demo.sh token manager    print a local token (salesperson|manager|agent|readonly)
#   ./scripts/demo.sh chaos slow       break the DMS on purpose (slow|errors|flaky|off)
#   ./scripts/demo.sh reset            fresh demo data, chaos off
#   ./scripts/demo.sh inspector [persona]   MCP Inspector, pre-connected to :8080 (with a token from stage 3)
#   ./scripts/demo.sh rehearse         run every runbook step automatically and report PASS/FAIL
#   ./scripts/demo.sh stage 2          set src/live/server.py to stage N, open the diff vs N-1 in VS Code
#   ./scripts/demo.sh stage done       put the file back to main (after the talk)
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
  inspector)
    # Restart this to switch persona (salesperson -> manager in stage 4).
    args=(--web --transport http --server-url http://127.0.0.1:8080/mcp --protocol-era modern)
    [ -n "${2:-}" ] && args+=(--header "Authorization: Bearer $(uv run dev-token "$2")")
    exec npx -y @modelcontextprotocol/inspector "${args[@]}" ;;
  rehearse)  exec uv run python workshop/rehearse.py "${@:2}" ;;
  stage)
    # Stay on main (latest scripts, docs, mcp.json); swap only the file built on stage.
    n="${2:?stage number 0-5, or done}"
    if [ "$n" = "done" ]; then git checkout main -- src/live/server.py && echo "src/live/server.py = main"; exit 0; fi
    git checkout "stage-$n" -- src/live/server.py && echo "src/live/server.py = stage $n"
    if [ "$n" -gt 0 ] && command -v code >/dev/null; then
      prev="${TMPDIR:-/tmp}/stage-$((n - 1))-server.py"
      git show "stage-$((n - 1)):src/live/server.py" > "$prev" && code --diff "$prev" src/live/server.py
    fi ;;
  *) sed -n '2,14p' "$0"; exit 1 ;;
esac
