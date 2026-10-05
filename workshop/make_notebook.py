"""Builds workshop/demo.ipynb (build and run locally, then connect your chat), azure.ipynb (the
deployed version) and deploy-azure.ipynb (deploy your own copy). No terminal needed.

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
# Zero to Production MCP: build it locally

Run each cell in order with ▶ (or *Run All*). Everything runs on your machine: the cells start the dealer
system and the MCP server, switch stages and make every call; their logs are in `.dev/notebook/`. At the end
you connect GitHub Copilot to the server you just built. No Azure needed: the deployed version is
[azure.ipynb](azure.ipynb). Timings follow [docs/PRESENTER.md](../docs/PRESENTER.md).

**Kernel:** pick the repo's `.venv` (Python) when VS Code asks.
""")

code(r'''
# Setup: run once. Every cell below uses these helpers.
import base64, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "pyproject.toml").exists() else Path.cwd().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "workshop"))
VENV = ROOT / ".venv"
if Path(sys.prefix).resolve() != VENV.resolve():
    raise RuntimeError(
        f"Wrong kernel: this notebook needs the repo's .venv, but it's running {sys.executable}. "
        "Top right: click the kernel name > Select Another Kernel > Python Environments > .venv "
        "(run ./scripts/demo.sh setup first if .venv doesn't exist), then run this cell again.")
import httpx
import rehearse as rh

LOGS = ROOT / ".dev" / "notebook"
LOGS.mkdir(parents=True, exist_ok=True)
RUNNING: dict = {}
AUTO = os.environ.get("NOTEBOOK_AUTO") == "1"   # headless test: no prompts, no VS Code diff
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
        run(f"git checkout stage-{n} -- src/live/server.py 2>/dev/null"
            f" || git checkout origin/stage-{n} -- src/live/server.py")
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


for port in (8080, 8081):
    if not rh.port_free(port):
        print(f"Port {port} is busy: run the Cleanup cell at the bottom (it frees both ports), then this cell again.")
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

**Code (diff):** `attempts = 3 if method == "GET" else 1`, the `asyncio.timeout(1.5)` block,
`AuditMiddleware` and `RateLimitingMiddleware`.
""")
code(r'''
stage(5)
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
## 7. Connect your chat to the server you built (+41)

The server from stage 5 is still running on `http://127.0.0.1:8080/mcp`. Now a real client uses it.

1. Run the cell below: fresh demo data and a **salesperson** token.
2. VS Code: *MCP: List Servers* > `dealer-local` > *Start*, and paste the token when asked.
3. Copilot Chat, **Agent** mode:
   > A customer wants an AWD SUV under $25,000 with under 100,000 km. Find the best match, give me the
   > all-in price, save her as a lead (Priya Natarajan, 416-555-0142), and apply a $900 discount.

**Expected:** TBA-1017 (2021 Tiguan), all-in **$20,209.50**, the lead saved with a masked phone, and
**"Discounts over $500 need a sales manager."** If Copilot picks another car, use it: the model chooses,
the server keeps every choice safe.
""")
code(r'''
rh.reset()
print(rh.token("salesperson"))                                   # paste into dealer-local when asked
''')

md("""
Every call Copilot made went through the server you built: one audit line each, argument names only.
""")
code(r'''
log_tail("live", n=10, grep="tool_call")
''')

md("""
**Now as a manager:** *MCP: Reset Cached Inputs*, then restart `dealer-local` and paste the manager token below.
Ask Copilot to apply the same $900 discount to TBA-1017: VS Code asks you to confirm before the server applies it,
and `delete_lead` now shows in the tool list.
""")
code(r'''
print(rh.token("manager"))
''')

md("""
## 8. Look inside with MCP Inspector (optional)

**What:** the official debugging client from the MCP project. A web page that connects to your server, lists its
tools and lets you call them by hand through a form built from each tool's schema. There is no model in it: you
are the client, so you see exactly what Copilot sees, without the model's choices in between.

**Why and when:** while building a tool (schemas, results, errors); when Copilot does something odd (replay its
call: if the server answers correctly, the prompt or the tool description is the problem); to check permissions
(another persona, another tool list) and auth (no token: 401 and where to sign in).

**How:** run the cell below; Inspector opens in your browser, already connected with a salesperson token.
*Tools* > pick a tool > fill the form > *Run Tool*. The right panel's *Protocol* tab shows the raw JSON-RPC.
Natural-language prompts belong in Copilot: Inspector's *Prompts* tab lists MCP prompt templates (this server has none).

| Tool | Arguments | Shows |
| --- | --- | --- |
| `quote_price` | `TBA-1017` | all-in 20209.5, every fee: the math lives in the server |
| `get_vehicle` | `../admin` | rejected by the schema before it reaches the dealer system |
| `create_lead` | Priya, Natarajan, `416-555-0142` | name and phone come back masked |
| `apply_discount` | `TBA-1001`, `900`, `loyal customer` | salesperson: needs a sales manager. As manager: a confirmation prompt |

Inspector and Copilot are separate clients: Inspector doesn't see Copilot's calls, the audit log above shows both.
""")
code(r'''
if not AUTO:
    background("inspector", ["./scripts/demo.sh", "inspector", "salesperson"], "http://127.0.0.1:6274")
    log_tail("inspector", n=3, grep="6274")                      # the URL, if the browser didn't open
''')
code(r'''
# Same page as a manager: delete_lead appears, the $900 discount asks you to confirm.
if not AUTO:
    background("inspector", ["./scripts/demo.sh", "inspector", "manager"], "http://127.0.0.1:6274")
''')

md("""
**Next:** the same server, deployed in Azure behind API Management: [azure.ipynb](azure.ipynb).
""")

md("""
## Cleanup (after the talk)
""")
code(r'''
# Run All reaches this cell too: it asks first, so Copilot keeps its server unless you say y.
if AUTO or input("Stop the local servers and Inspector (Copilot loses dealer-local)? [y/N] ").strip().lower().startswith("y"):
    for name in list(RUNNING):
        stop_bg(name)
    run("lsof -ti tcp:8080,8081,6274,6275 -sTCP:LISTEN | xargs kill 2>/dev/null")  # also orphans from an earlier kernel
    run("./scripts/demo.sh stage done")
    print("stopped; src/live/server.py is back to main")
else:
    print("still running: dealer-local on :8080, the dealer system on :8081")
''')


def build(cells_in: list) -> dict:
    cells = []
    for i, (kind, src) in enumerate(cells_in):
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
    from make_azure_notebook import AZURE_CELLS
    from make_deploy_notebook import DEPLOY_CELLS

    for name, cells in (("demo.ipynb", CELLS), ("azure.ipynb", AZURE_CELLS), ("deploy-azure.ipynb", DEPLOY_CELLS)):
        out = Path(__file__).with_name(name)
        out.write_text(json.dumps(build(cells), indent=1) + "\n")
        print(f"wrote {out} ({len(cells)} cells)")
