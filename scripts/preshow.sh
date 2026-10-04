#!/usr/bin/env bash
# Show-morning check. Read-mostly: it only resets the show env's demo data and
# makes sure the manager role is off. Never provisions anything.
#   ./scripts/preshow.sh            everything, including the 34-step local rehearsal
#   ./scripts/preshow.sh --cloud    cloud checks only
set -uo pipefail
cd "$(dirname "$0")/.."

ENV=mcpshow
RG=rg-$ENV
SPARE=https://ca-mcp-mcprehearse.yellowdesert-1d8bdd6e.canadacentral.azurecontainerapps.io/mcp
fails=0
ok()   { printf '  PASS  %s\n' "$1"; }
bad()  { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }
step() { printf '\n== %s\n' "$1"; }

step "Tools and sign-in"
v=$(azd version 2>/dev/null | sed -n 's/^azd version \([0-9.]*\).*/\1/p')
[ "$(printf '%s\n1.35.0\n' "$v" | sort -V | head -1)" = "1.35.0" ] && ok "azd $v" || bad "azd $v (need 1.35+: brew uninstall azd && brew install azure/azd/azd)"
azd env select "$ENV" >/dev/null 2>&1 && ok "azd default env = $ENV" || bad "azd env $ENV missing (azd env new $ENV && azd env refresh -e $ENV)"
sub=$(az account show --query id -o tsv 2>/dev/null)
[ "$sub" = "$(azd env get-value AZURE_SUBSCRIPTION_ID -e "$ENV" 2>/dev/null)" ] && ok "az on the $ENV subscription" || bad "az subscription is '$sub' (run: az login)"
MCP_URL=$(azd env get-value MCP_URL -e "$ENV" 2>/dev/null)
API=$(azd env get-value ENTRA_API_URI -e "$ENV" 2>/dev/null)

step "Environments"
APIM=$(azd env get-value APIM_NAME -e "$ENV" 2>/dev/null)
apim_id=$(az apim show -g "$RG" -n "$APIM" --query id -o tsv 2>/dev/null)
health=$(az rest --method get --url "https://management.azure.com${apim_id}/providers/Microsoft.ResourceHealth/availabilityStatuses/current?api-version=2024-02-01" --query properties.availabilityState -o tsv 2>/dev/null)
[ "$health" = "Available" ] && ok "API Management $APIM available" || bad "API Management $APIM is '$health' (Developer tier upgrades take ~25 min; use dealer-spare)"
./scripts/smoke.sh "$MCP_URL" >/dev/null 2>&1 && ok "$ENV smoke" || bad "$ENV smoke ($MCP_URL)"
./scripts/smoke.sh "$SPARE" >/dev/null 2>&1 && ok "hot spare smoke" || bad "hot spare smoke"
grep -q "${MCP_URL%/mcp}" .vscode/mcp.json && ok ".vscode/mcp.json dealer-cloud = $ENV" || bad "dealer-cloud does not point at $ENV"

step "Show state"
./scripts/manager-role.sh off >/dev/null 2>&1 && ok "manager role off (finale: \$900 is refused)" || bad "manager-role.sh off"
rev=$(az containerapp revision list -g "$RG" -n "ca-dms-$ENV" --query "[?properties.active].name | [0]" -o tsv 2>/dev/null)
az containerapp revision restart -g "$RG" -n "ca-dms-$ENV" --revision "$rev" -o none 2>/dev/null \
  && ok "demo data reset (DMS revision $rev restarted)" || bad "DMS restart"

step "Real Entra token, end to end (also warms the replicas)"
TOKEN=$(az account get-access-token --scope "$API/dms.read" "$API/dms.write" --query accessToken -o tsv 2>/dev/null)
MCP_URL=$MCP_URL TOKEN=$TOKEN uv run --quiet python - <<'PY' && ok "6 tools, TBA-1017 all-in \$20,209.50, \$900 refused" || bad "real-token check"
import asyncio, os, sys
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

async def main():
    for attempt in range(12):  # the DMS restarts just before this
        try:
            async with Client(os.environ["MCP_URL"], auth=BearerAuth(os.environ["TOKEN"])) as c:
                tools = {t.name for t in await c.list_tools()}
                q = await c.call_tool("quote_price", {"stock_number": "TBA-1017"}, raise_on_error=False)
                if q.is_error:
                    raise RuntimeError(q.content[0].text)
                d = await c.call_tool("apply_discount", {"stock_number": "TBA-1017", "amount": 900,
                                                         "reason": "preshow check"}, raise_on_error=False)
            break
        except Exception as e:  # noqa: BLE001
            if attempt == 11:
                sys.exit(f"      {e}")
            await asyncio.sleep(10)
    checks = {
        "6 tools, no delete_lead": len(tools) == 6 and "delete_lead" not in tools,
        "all-in 20209.5": q.structured_content.get("all_in_price") == 20209.5,
        "discount refused": d.is_error and "sales manager" in d.content[0].text,
    }
    for name, good in checks.items():
        print(f"      {'ok ' if good else 'BAD'} {name}")
    sys.exit(0 if all(checks.values()) else 1)

asyncio.run(main())
PY

step "Laptop"
[ -z "$(git status --porcelain)" ] && ok "git tree clean" || bad "git tree has changes"
npx -y @modelcontextprotocol/inspector@latest --help >/dev/null 2>&1 && ok "MCP Inspector cached" || bad "npx inspector"
if [ "${1:-}" != "--cloud" ]; then
  ./scripts/demo.sh rehearse 2>&1 | tail -1 | grep -q "34/34" && ok "rehearse 34/34" || bad "rehearse (needs :8080 and :8081 free)"
fi

printf '\n%s\n' "$([ $fails -eq 0 ] && echo 'ALL GREEN' || echo "$fails check(s) failed")"
exit $fails
