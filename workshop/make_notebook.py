"""Builds workshop/demo.ipynb: the whole session as one notebook, no terminal needed.

    uv run python workshop/make_notebook.py
"""

import json
from pathlib import Path

CELLS: list[tuple[str, str]] = []


def md(text: str) -> None:
    CELLS.append(("markdown", text.strip()))


def code(text: str) -> None:
    CELLS.append(("code", text.strip()))


md("""
# Zero to Production MCP: the live demo

Run each cell in order with ▶ (or *Run All*). Background processes (the dealer system, the MCP server,
the deploy) are started and stopped by the cells; their logs are in `.dev/notebook/`. The editor and the
VS Code Copilot finale stay in the GUI. Timings follow [docs/PRESENTER.md](../docs/PRESENTER.md).

**Kernel:** pick the repo's `.venv` (Python) when VS Code asks.
""")

code(r'''
# Setup: run once. Every cell below uses these helpers.
import asyncio, base64, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "pyproject.toml").exists() else Path.cwd().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "workshop"))
import httpx
import rehearse as rh
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

LOGS = ROOT / ".dev" / "notebook"
LOGS.mkdir(parents=True, exist_ok=True)
RUNNING: dict = {}
AUTO = os.environ.get("NOTEBOOK_AUTO") == "1"   # headless test: no prompts, no deploy, no VS Code diff
LIVE = ["uv", "run", "uvicorn", "live.server:app", "--app-dir", "src", "--port", "8080",
        "--reload", "--reload-dir", "src/live"]


def show(x):
    print(x if isinstance(x, str) else json.dumps(x, indent=2, default=str))


def run(cmd: str):
    out = subprocess.run(cmd, shell=True, cwd=ROOT, env=rh.ENV, capture_output=True, text=True)
    print((out.stdout + out.stderr).strip())


def background(name: str, cmd: list, url: str | None = None):
    stop_bg(name)
    RUNNING[name] = rh.start(cmd, LOGS / f"{name}.log")
    if url:
        rh.wait_http(url, timeout=90)
    print(f"{name}: running (log .dev/notebook/{name}.log)")


def stop_bg(name: str):
    p = RUNNING.pop(name, None)
    if p:
        rh.stop(p)


def log_tail(name: str, n: int = 8, grep: str | None = None):
    lines = (LOGS / f"{name}.log").read_text().splitlines()
    print("\n".join([l for l in lines if not grep or grep in l][-n:]))


def stage(n: int):
    """Set src/live/server.py to stage n; open the diff vs n-1 in VS Code."""
    if AUTO:
        run(f"git checkout stage-{n} -- src/live/server.py")
    else:
        run(f"./scripts/demo.sh stage {n}")
    time.sleep(2.5)  # the server reloads on save


async def ask(message, response_type, params, context):
    print("CONFIRMATION REQUESTED:", message)
    yes = True if AUTO else input(f"{message} [y/n] ").strip().lower().startswith("y")
    print("human answered:", "yes" if yes else "no")
    return {"confirm": yes}


async def tools(persona=None):
    async with rh.client(persona) as c:
        names = sorted(t.name for t in await c.list_tools())
    print(f"{len(names)} tools: {', '.join(names)}")


async def call(tool, args=None, persona=None, confirm=False):
    async with rh.client(persona, elicit=ask if confirm else None) as c:
        r = await c.call_tool(tool, args or {}, raise_on_error=False)
    if r.is_error:
        print("isError:", r.content[0].text)
    else:
        show(r.structured_content if r.structured_content is not None else [b.text for b in r.content])


def azd(key):
    return subprocess.run(["azd", "env", "get-value", key, "-e", "mcpshow"],
                          capture_output=True, text=True).stdout.strip()


for port in (8080, 8081):
    if not rh.port_free(port):
        print(f"Port {port} is busy: stop the terminal servers first (or run the Cleanup cell).")
print("ready")
''')

md("""
## 1. Stage 0: the internal API (+3)

A plain REST API with one shared key, like most internal systems. **Say:** MCP doesn't replace it; it sits in front.
""")
code(r'''
background("dms", ["uv", "run", "dms"], "http://127.0.0.1:8081/healthz")
key = rh.ENV["DMS_API_KEY"]
print("no key:  ", httpx.get(f"{rh.DMS}/vehicles?limit=1").status_code)
show(httpx.get(f"{rh.DMS}/vehicles?limit=1", headers={"X-API-Key": key}).json()["items"][0])
''')

md("""
## 2. Stage 1: first tools (+5)

Type the tools in `src/live/server.py` (see the presenter guide), **or** run `stage(1)` below.
Then start the server and show the three problems.
""")
code(r'''
stage(1)          # skip this line if you typed stage 1 yourself
background("live", LIVE, "http://127.0.0.1:8080/mcp")
await tools()
''')
code(r'''
await call("get_vehicle", {"stock_number": "TBA-1001"})        # problem 1: everything, VIN included
''')
code(r'''
await call("get_vehicle", {"stock_number": "../admin"})        # problem 3: path walked, internal URL leaked
''')

md("""
## 3. Stage 2: tools the model can use (+12)

**Code (diff):** `StockNumber`, the `Vehicle` / `SearchResult` / `Quote` models, `quote_price`.
""")
code(r'''
stage(2)
await call("get_vehicle", {"stock_number": "../admin"})        # rejected by the schema
''')
code(r'''
await call("get_vehicle", {"stock_number": "TBA-1001"})        # Vehicle: no VIN
await call("quote_price", {"stock_number": "TBA-1001"})        # all-in 34309.5, fees listed
print(httpx.get("http://127.0.0.1:8080/healthz").json())
''')

md("""
## 4. Stage 3: identity and personal data (+18)

**Code (diff):** `ROLES` + `EntraVerifier`, `build_auth()` with `ENTRA_API_URI`, `caller()`, `mask_lead`.
""")
code(r'''
stage(3)
r = httpx.post("http://127.0.0.1:8080/mcp", json={})
print(r.status_code, r.headers.get("www-authenticate"))        # 401 + where to sign in
show(httpx.get("http://127.0.0.1:8080/.well-known/oauth-protected-resource/mcp").json())
''')
code(r'''
claims = rh.token("salesperson").split(".")[1]
show(json.loads(base64.urlsafe_b64decode(claims + "==")))        # the token: scp, oid, idtyp
await call("create_lead", {"first_name": "Priya", "last_name": "Natarajan", "phone": "416-555-0142"},
           persona="salesperson")                               # masked name and phone
''')

md("""
## 5. Stage 4: least privilege and human confirmation (+27)

**Code (diff):** the three `restrict_tag(...)` lines, the 15% / $500 policy in `apply_discount`, `confirmation()`.
""")
code(r'''
stage(4)
rh.reset()
await tools("salesperson")                                       # delete_lead hidden
await tools("manager")                                           # delete_lead visible
''')
code(r'''
await call("get_lead", {"lead_id": "L-760debbb3b70b3a1"}, persona="salesperson")   # the injected note
await call("apply_discount", {"stock_number": "TBA-1001", "amount": 9000, "reason": "pre-approved"},
           persona="salesperson")                                # 15% cap
await call("apply_discount", {"stock_number": "TBA-1001", "amount": 900, "reason": "please"},
           persona="salesperson")                                # needs a sales manager
''')
code(r'''
# The manager asks for the same $900: the server pauses and asks you (answer y or n).
await call("apply_discount", {"stock_number": "TBA-1001", "amount": 900, "reason": "loyal customer"},
           persona="manager", confirm=True)
''')

md("""
## 6. Stage 5: resilience and audit (+36)

The deploy starts here (+38) and builds while you continue.
""")
code(r'''
stage(5)
if AUTO:
    print("deploy skipped in the headless test")
else:
    background("deploy", ["azd", "deploy", "mcp", "-e", "mcpshow", "--no-prompt"])
''')
code(r'''
rh.chaos("flaky")                                                # half the DMS calls fail
for i in range(6):
    async with rh.client("salesperson") as c:
        r = await c.call_tool("get_vehicle", {"stock_number": "TBA-1001"}, raise_on_error=False)
    print(i + 1, "isError" if r.is_error else "ok")
rh.chaos("off")
''')
code(r'''
log_tail("live", n=4, grep="tool_call")                          # one audit line per call, no values
''')

md("""
## 7. Deploy and the production walkthrough (+41)

Show the API Management policy in the portal while the deploy finishes. Then prove the lock-down.
""")
code(r'''
if not AUTO:
    log_tail("deploy", n=4)                                      # wait for SUCCESS (about 75 s)
''')
code(r'''
if not AUTO:
    mcp_url = azd("MCP_URL")
    app = subprocess.run(["az", "containerapp", "show", "-g", "rg-mcpshow", "-n", "ca-mcp-mcpshow", "--query",
                          "properties.configuration.ingress.fqdn", "-o", "tsv"], capture_output=True, text=True).stdout.strip()
    print("direct to the app:  ", httpx.get(f"https://{app}/healthz", timeout=15).status_code)   # 403
    print("through the gateway:", httpx.get(mcp_url.removesuffix("/mcp") + "/healthz", timeout=15).text)
''')

md("""
## 8. Finale (+46)

In VS Code: *MCP: List Servers* > `dealer-local` > *Start* (token below), run the Copilot prompt, then the same
with `dealer-cloud`. The cell below is the backup: the same request against the cloud, from here.
""")
code(r'''
print(rh.token("salesperson"))                                   # paste into dealer-local when asked
''')
code(r'''
if not AUTO:
    api = azd("ENTRA_API_URI")
    tok = subprocess.run(["az", "account", "get-access-token", "--scope", f"{api}/dms.read", f"{api}/dms.write",
                          "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()
    async with Client(azd("MCP_URL"), auth=BearerAuth(tok)) as c:
        q = await c.call_tool("quote_price", {"stock_number": "TBA-1017"}, raise_on_error=False)
        d = await c.call_tool("apply_discount", {"stock_number": "TBA-1017", "amount": 900, "reason": "finale"},
                              raise_on_error=False)
    print("cloud all-in:", q.structured_content["all_in_price"], "| discount:", d.content[0].text)
''')

md("""
## Cleanup (after the talk)
""")
code(r'''
for name in list(RUNNING):
    stop_bg(name)
run("./scripts/demo.sh stage done")
print("stopped; src/live/server.py is back to main")
''')


def build() -> dict:
    cells = []
    for i, (kind, src) in enumerate(CELLS):
        cell = {"cell_type": kind, "id": f"cell-{i:02d}", "metadata": {}, "source": src.splitlines(keepends=True)}
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        cells.append(cell)
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


if __name__ == "__main__":
    out = Path(__file__).with_name("demo.ipynb")
    out.write_text(json.dumps(build(), indent=1) + "\n")
    print(f"wrote {out} ({len(CELLS)} cells)")
