"""Cells of workshop/deploy-azure.ipynb: deploy your own copy to Azure, step by step.

Built together with demo.ipynb by `uv run python workshop/make_notebook.py`.
DEPLOY_NB_AUTO=1 runs it headless as a dry run: defaults for every answer, nothing created.
"""

DEPLOY_CELLS: list[tuple[str, str]] = []


def md(text: str) -> None:
    DEPLOY_CELLS.append(("markdown", text.strip()))


def code(text: str) -> None:
    DEPLOY_CELLS.append(("code", text.strip()))


md("""
# Deploy your own copy to Azure

Run the cells in order. The notebook signs you in, asks a few questions, shows exactly what will be created,
and only then deploys. Nothing is created until you type `yes` in step 4.

| You get | Time | Cost |
| --- | --- | --- |
| A resource group `rg-<name>` with a VNet, API Management (the public MCP URL), Container Apps (the MCP server and the mock dealer API), Premium ACR and Key Vault behind private endpoints, Log Analytics, and an Entra app registration | About 45 minutes (API Management takes 30 to 40) | Roughly $5 per day. Delete it with the last cell when you're done |

**You need:** an Azure subscription where you can create role assignments (Owner, or Contributor plus
User Access Administrator), permission to create app registrations in Microsoft Entra ID, and the
[Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) and [azd](https://aka.ms/azd) 1.35+.
No Docker: the image is built in Azure.

**Kernel:** pick the repo's `.venv` (Python) when VS Code asks.
""")

code(r'''
# Setup: helpers used below.
import getpass, json, os, re, subprocess, time
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "pyproject.toml").exists() else Path.cwd().parent
os.chdir(ROOT)
DRY_RUN = os.environ.get("DEPLOY_NB_AUTO") == "1"   # headless test: default answers, nothing created
LOGS = ROOT / ".dev" / "notebook"
LOGS.mkdir(parents=True, exist_ok=True)
JOBS: dict = {}


def sh(cmd: str, quiet: bool = False) -> str:
    out = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True)
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", (out.stdout + out.stderr)).strip()
    if not quiet and text:
        print(text)
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", out.stdout).strip() if out.returncode == 0 else ""


def ask(question: str, default: str = "") -> str:
    if DRY_RUN:
        print(f"{question} -> {default}")
        return default
    answer = input(f"{question} [{default}] ").strip()
    return answer or default


def job(name: str, cmd: str):
    """Start a long command in the background; follow it with progress(name)."""
    if DRY_RUN:
        print("dry run, would run:", cmd)
        return
    log = (LOGS / f"{name}.log").open("w")
    JOBS[name] = subprocess.Popen(cmd, shell=True, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print(f"started: {cmd}\nfollow it with the next cell (log .dev/notebook/{name}.log)")


def progress(name: str, lines: int = 12):
    path = LOGS / f"{name}.log"
    if not path.exists():
        print("not started")
        return
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", path.read_text())
    print("\n".join([l for l in text.splitlines() if l.strip()][-lines:]))
    p = JOBS.get(name)
    if p and p.poll() is None:
        print("\n... still running, run this cell again in a minute")
    elif p:
        print(f"\nfinished with exit code {p.returncode}")

print("ready" + (" (dry run)" if DRY_RUN else ""))
''')

md("""
## 1. Check the tools
""")
code(r'''
az = sh("az version --query '\"azure-cli\"' -o tsv", quiet=True)
azd_v = re.search(r"(\d+\.\d+\.\d+)", sh("azd version", quiet=True) or "")
print("Azure CLI:", az or "MISSING: install it first")
print("azd:      ", azd_v.group(1) if azd_v else "MISSING: install azd first")
if azd_v and tuple(map(int, azd_v.group(1).split("."))) < (1, 35, 0):
    print("azd is older than 1.35: update it (remote builds fail on older versions)")
''')

md("""
## 2. Sign in

Opens your browser. If no browser can open, the cell prints a device code instead.
""")
code(r'''
tenant = ask("Tenant ID (leave empty for your default tenant)", "")
if not sh("az account show --query id -o tsv", quiet=True):
    sh(f"az login {'--tenant ' + tenant if tenant else ''}")
if "Logged in" not in sh("azd auth login --check-status", quiet=True):
    sh(f"azd auth login {'--tenant-id ' + tenant if tenant else ''}")
print("Azure CLI:", sh("az account show --query user.name -o tsv", quiet=True))
print(sh("azd auth login --check-status", quiet=True))
''')

md("""
## 3. Choose the subscription, a name and a region
""")
code(r'''
print(sh("az account list --query \"[].{name:name, subscriptionId:id, default:isDefault}\" -o table", quiet=True))
sub = ask("Subscription ID", sh("az account show --query id -o tsv", quiet=True))
if not DRY_RUN:
    sh(f"az account set --subscription {sub}")

suggested = "mcp" + re.sub(r"[^a-z0-9]", "", getpass.getuser().lower())[:8]
name = ask("Environment name (lowercase letters and digits, 3 to 16)", suggested)
assert re.fullmatch(r"[a-z][a-z0-9]{2,15}", name), "use 3 to 16 lowercase letters or digits, starting with a letter"
region = ask("Azure region", "canadacentral")
email = ask("Contact email for API Management notifications",
            sh("az ad signed-in-user show --query mail -o tsv", quiet=True) or "noreply@example.com")

print(f"""
Will create, in subscription {sub}:
  resource group   rg-{name}   (region {region})
  API Management   apim-{name}-*        public MCP URL, rate limit per caller
  Container Apps   ca-mcp-{name}, ca-dms-{name}   in vnet-{name}
  Registry, Key Vault (private endpoints), Log Analytics, managed identity
  Entra app        dealer-mcp-{name}
About 45 minutes. Roughly $5 per day until you delete it.""")
''')

md("""
## 4. Deploy

Type `yes` to start. `azd up` creates the infrastructure, builds the image in Azure and deploys it.
It also points `dealer-cloud` in `.vscode/mcp.json` at your new server.
""")
code(r'''
if ask(f"Type yes to deploy {name}", "yes" if DRY_RUN else "") == "yes":
    if not DRY_RUN:
        sh(f"azd env new {name} --subscription {sub} --location {region} --no-prompt", quiet=True)
        sh(f"azd env select {name}", quiet=True)
        sh(f"azd env set APIM_PUBLISHER_EMAIL {email} -e {name}", quiet=True)
    job("azd-up", f"azd up -e {name} --no-prompt")
else:
    print("not started")
''')

md("""
## 5. Follow the progress

Run this cell again whenever you want an update. API Management is the slow part.
""")
code(r'''
progress("azd-up")
''')

md("""
## 6. Try your server

Smoke test (no credentials), then a real call with your Entra token through API Management.
""")
code(r'''
if DRY_RUN:
    print("dry run: skipped")
else:
    mcp_url = sh(f"azd env get-value MCP_URL -e {name}", quiet=True)
    api = sh(f"azd env get-value ENTRA_API_URI -e {name}", quiet=True)
    print("MCP URL:", mcp_url)
    sh(f"./scripts/smoke.sh {mcp_url}")
    token = sh(f"az account get-access-token --scope {api}/dms.read {api}/dms.write --query accessToken -o tsv", quiet=True)

    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth
    async with Client(mcp_url, auth=BearerAuth(token)) as c:
        print("tools:", sorted(t.name for t in await c.list_tools()))
        q = await c.call_tool("quote_price", {"stock_number": "TBA-1017"}, raise_on_error=False)
    print("all-in price for TBA-1017:", q.structured_content["all_in_price"])
    print("\nNext: VS Code > MCP: List Servers > dealer-cloud > Start, and sign in with Microsoft.")
''')

md("""
## 7. Delete everything

Removes the resource group and purges the Key Vault (about 15 minutes). Type the environment name to confirm.
""")
code(r'''
if ask(f"Type {name} to delete it", "" if DRY_RUN else "") == name:
    client_id = sh(f"azd env get-value ENTRA_CLIENT_ID -e {name}", quiet=True)
    job("azd-down", f"azd down -e {name} --purge --force")
    print(f"After it finishes, also delete the Entra app: az ad app delete --id {client_id}")
else:
    print("kept")
''')
code(r'''
progress("azd-down")
''')
