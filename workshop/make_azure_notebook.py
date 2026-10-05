"""Cells of workshop/azure.ipynb: the finished server, deployed in Azure behind API Management.

Built together with demo.ipynb by `uv run python workshop/make_notebook.py`.
"""

AZURE_CELLS: list[tuple[str, str]] = []


def md(text: str) -> None:
    AZURE_CELLS.append(("markdown", text.strip()))


def code(text: str) -> None:
    AZURE_CELLS.append(("code", text.strip()))


md("""
# Zero to Production MCP: the deployed version

The server you built in [demo.ipynb](demo.ipynb), running in Azure: a private network, API Management as the
only way in, Entra ID for identity. Every cell is read-only unless you set `DEPLOY_LIVE = True`.

**You need:** `az login` done in a terminal, and a deployed environment: the presenter's `mcpshow`, or your own
from [deploy-azure.ipynb](deploy-azure.ipynb) (set `ENV` below to its name).

**Kernel:** pick the repo's `.venv` (Python) when VS Code asks.
""")

code(r'''
# Setup: finds the environment and checks you're signed in.
import json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "pyproject.toml").exists() else Path.cwd().parent
os.chdir(ROOT)
VENV = ROOT / ".venv"
if Path(sys.prefix).resolve() != VENV.resolve():
    raise RuntimeError(
        f"Wrong kernel: this notebook needs the repo's .venv, but it's running {sys.executable}. "
        "Top right: click the kernel name > Select Another Kernel > Python Environments > .venv "
        "(run ./scripts/demo.sh setup first if .venv doesn't exist), then run this cell again.")
import httpx
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

ENV = "mcpshow"        # your own copy: the name you chose in deploy-azure.ipynb
DEPLOY_LIVE = False    # True: step 1 rebuilds the image from this repo and rolls it out (about 75 s)


def sh(cmd: str, quiet: bool = False) -> str:
    out = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True)
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", (out.stdout + out.stderr)).strip()
    if not quiet and text:
        print(text)
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", out.stdout).strip() if out.returncode == 0 else ""


def azd_values() -> dict:
    return dict(re.findall(r'^(\w+)="(.*)"$', sh(f"azd env get-values -e {ENV}", quiet=True), re.M))


account = sh("az account show --query '[user.name, id]' -o tsv", quiet=True).split()
if not account:
    raise RuntimeError("Not signed in to Azure: run `az login` in a terminal, then this cell again.")
vals = azd_values()
if "MCP_URL" not in vals:
    # Deployed, but this machine has no local azd environment for it: rebuild it from the resource group's tag.
    loc = sh(f"az group list --tag azd-env-name={ENV} --query '[0].location' -o tsv", quiet=True)
    if not loc:
        raise RuntimeError(f"No deployment named '{ENV}' in subscription {account[1]}. Pick the right one with "
                           "`az account set -s <id>`, or deploy your own with deploy-azure.ipynb.")
    sh(f"azd env new {ENV} --subscription {account[1]} --location {loc} --no-prompt", quiet=True)
    sh(f"azd env refresh -e {ENV} --no-prompt", quiet=True)
    vals = azd_values()
MCP_URL, API, RG = vals["MCP_URL"], vals["ENTRA_API_URI"], vals["AZURE_RESOURCE_GROUP"]
print(f"signed in as {account[0]}\nenvironment {ENV} ({RG})\nMCP URL {MCP_URL}")
''')

md("""
## 1. What runs there

CI built the image once, scanned it and promoted it to this environment (`release.yml`): it's the stage 5
file. Set `DEPLOY_LIVE = True` in Setup only to show a live redeploy.
""")
code(r'''
if DEPLOY_LIVE:
    sh(f"azd deploy mcp -e {ENV} --no-prompt")
else:
    print("No redeploy: the finished server already runs here.")
''')

md("""
## 2. The production walkthrough

**Code:** `infra/modules/apim-api.bicep` (`rate-limit-by-key` on the caller's `oid`);
`infra/modules/platform.bicep` (`ipSecurityRestrictions`, Key Vault `publicNetworkAccess: 'Disabled'`).
**Portal:** API Management > APIs > dealer-mcp > Inbound processing (the policy).

Then prove the lock-down: the app refuses direct calls, the gateway answers.
""")
code(r'''
app = sh(f"az containerapp show -g {RG} -n ca-mcp-{ENV} --query properties.configuration.ingress.fqdn -o tsv",
         quiet=True)
print("direct to the app:  ", httpx.get(f"https://{app}/healthz", timeout=15).status_code)   # 403
print("through the gateway:", httpx.get(MCP_URL.removesuffix("/mcp") + "/healthz", timeout=15).text)
''')

md("""
## 3. A real call with your Entra token

The same request as the local finale, now through Entra ID and API Management. Your role in the Entra app
decides what you may do, exactly like the local personas.
""")
code(r'''
token = sh(f"az account get-access-token --scope {API}/dms.read {API}/dms.write --query accessToken -o tsv",
           quiet=True)
async with Client(MCP_URL, auth=BearerAuth(token)) as c:
    names = sorted(t.name for t in await c.list_tools())
    q = await c.call_tool("quote_price", {"stock_number": "TBA-1017"}, raise_on_error=False)
    d = await c.call_tool("apply_discount", {"stock_number": "TBA-1017", "amount": 900, "reason": "finale"},
                          raise_on_error=False)
print(f"{len(names)} tools: {', '.join(names)}")
print("cloud all-in:", q.structured_content["all_in_price"], "| discount:", d.content[0].text)
''')

md("""
## 4. Connect your chat to the cloud

VS Code: *MCP: List Servers* > stop `dealer-local`, start `dealer-cloud`, sign in with Microsoft, and send the
same Copilot prompt as in demo.ipynb. Same answers, now through Entra and API Management.
For your own copy, set the `dealer-cloud` URL in `.vscode/mcp.json` to the MCP URL printed by Setup.

**Picture (if time):** Log Analytics in the portal: your calls with caller, outcome and latency.
**If the cloud stalls:** retry *Start* once; if API Management is down, use `dealer-spare`.
""")
