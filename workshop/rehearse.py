"""Executable rehearsal: runs every "Show" step of the stage runbook and checks the result.

    uv run python workshop/rehearse.py            # all stages + local finale
    uv run python workshop/rehearse.py --stage 4  # one stage

Starts the mock DMS on :8081 and each stage's server on :8080 exactly like
`scripts/demo.sh`, from workshop/stages/stage_N.py. Prints PASS/FAIL per step
so you know, before you're on stage, that every line of the runbook works.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

ROOT = Path(__file__).resolve().parent.parent
STAGES = ROOT / "workshop" / "stages"
DMS, MCP = "http://127.0.0.1:8081", "http://127.0.0.1:8080/mcp"
RESULTS: list[tuple[str, bool, str]] = []


def env() -> dict:
    e = dict(os.environ)
    if (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                e.setdefault(k, v)
    e.setdefault("DMS_API_KEY", "rehearsal-" + os.urandom(8).hex())
    e.update(DMS_BASE_URL=DMS, AUTH_MODE="local", PUBLIC_BASE_URL="http://127.0.0.1:8080",
             LOCAL_JWT_PUBLIC_KEY=str(ROOT / ".dev" / "jwt_public.pem"),
             PYTHONPATH=str(ROOT / "src"))
    return e


ENV = env()


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))


def token(persona: str) -> str:
    out = subprocess.run(["uv", "run", "dev-token", persona], cwd=ROOT, env=ENV,
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def wait_http(url: str, timeout: float = 20) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=1)
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"{url} did not come up")


def start(cmd: list[str], log: Path, cwd: Path = ROOT) -> subprocess.Popen:
    return subprocess.Popen(cmd, cwd=cwd, env=ENV, stdout=log.open("w"), stderr=subprocess.STDOUT,
                            start_new_session=True)


def stop(p: subprocess.Popen) -> None:
    try:
        os.killpg(p.pid, signal.SIGTERM)
        p.wait(timeout=5)
    except Exception:  # noqa: BLE001
        pass


def chaos(mode: str) -> None:
    httpx.post(f"{DMS}/_chaos", json={"mode": mode}, headers={"X-API-Key": ENV["DMS_API_KEY"]})


def reset() -> None:
    httpx.post(f"{DMS}/_reset", headers={"X-API-Key": ENV["DMS_API_KEY"]})


class StageServer:
    """Runs workshop/stages/stage_N.py as live/server.py, like `demo.sh live`."""

    def __init__(self, n: int, tmp: Path):
        self.n, self.dir = n, tmp / f"s{n}"
        (self.dir / "live").mkdir(parents=True, exist_ok=True)
        (self.dir / "live" / "__init__.py").write_text("")
        shutil.copy(STAGES / f"stage_{n}.py", self.dir / "live" / "server.py")
        self.log = tmp / f"stage_{n}.log"

    def __enter__(self):
        self.p = start([sys.executable, "-m", "uvicorn", "live.server:app", "--app-dir", str(self.dir),
                        "--port", "8080"], self.log)
        wait_http("http://127.0.0.1:8080/mcp")
        return self

    def __exit__(self, *exc):
        stop(self.p)
        time.sleep(0.3)


def client(persona: str | None = None, elicit=None, legacy: bool = False) -> Client:
    kw = {"elicitation_handler": elicit}
    if persona:
        kw["auth"] = BearerAuth(token(persona))
    if legacy:
        kw["mode"] = "legacy"
    return Client(MCP, **kw)


async def yes(*_):
    return {"confirm": True}


async def no(*_):
    return {"confirm": False}


async def err(c: Client, tool: str, args: dict) -> str:
    try:
        await c.call_tool(tool, args)
        return ""
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def discount(stock: str = "TBA-1001") -> float:
    r = httpx.get(f"{DMS}/vehicles/{stock}", headers={"X-API-Key": ENV["DMS_API_KEY"]})
    return r.json()["discount"]


# ----------------------------------------------------------------------------- stages


async def stage0(_tmp):
    r = httpx.get(f"{DMS}/vehicles?limit=1")
    check("DMS without key is 401", r.status_code == 401)
    r = httpx.get(f"{DMS}/vehicles?limit=1", headers={"X-API-Key": ENV["DMS_API_KEY"]})
    check("DMS with key returns a car with a VIN", "vin" in r.json()["items"][0])


async def stage1(tmp):
    with StageServer(1, tmp):
        async with client() as c:
            names = {t.name for t in await c.list_tools()}
            check("two tools, no auth needed", names == {"search_inventory", "get_vehicle"}, str(names))
            car = (await c.call_tool("get_vehicle", {"stock_number": "TBA-1001"})).structured_content
            check("raw dump includes the VIN (problem 1)", "vin" in car)
            e = await err(c, "get_vehicle", {"stock_number": "../admin"})
            check("../admin walks to /admin and leaks the internal URL (problem 3)",
                  "127.0.0.1:8081/admin" in e, e[:120])


async def stage2(tmp):
    with StageServer(2, tmp):
        async with client() as c:
            tools = {t.name: t for t in await c.list_tools()}
            enum = tools["search_inventory"].input_schema["properties"]["body_type"]
            check("enums in the input schema", "suv" in json.dumps(enum))
            check("output schema on every tool", all(t.output_schema for t in tools.values()))
            e = await err(c, "get_vehicle", {"stock_number": "../admin"})
            check("../admin rejected by validation", "pattern" in e or "validation" in e.lower(), e[:120])
            car = (await c.call_tool("get_vehicle", {"stock_number": "TBA-1001"})).structured_content
            check("no VIN in the result", "vin" not in car)
            q = (await c.call_tool("quote_price", {"stock_number": "TBA-1001"})).structured_content
            check("all-in quote for TBA-1001 is $34,309.50", q["all_in_price"] == 34309.5, str(q["all_in_price"]))
            check("disclosure says HST and licensing extra", "HST and licensing" in q["disclosure"])


async def stage3(tmp):
    with StageServer(3, tmp):
        r = httpx.post(MCP)
        check("no token: 401 with resource_metadata",
              r.status_code == 401 and "resource_metadata" in r.headers.get("www-authenticate", ""))
        prm = httpx.get("http://127.0.0.1:8080/.well-known/oauth-protected-resource/mcp").json()
        check("PRM names the issuer and scopes",
              prm["authorization_servers"] == ["https://dev.local/dealer-mcp"]
              and prm["scopes_supported"] == ["dms.read", "dms.write"], str(prm))
        async with client("salesperson") as c:
            lead = (await c.call_tool("create_lead", {"first_name": "Priya", "last_name": "Natarajan",
                                                      "phone": "416-555-0142"})).structured_content
            check("lead phone comes back masked", lead["phone"] == "***-***-0142", str(lead["phone"]))
            e = await err(c, "get_vehicle", {"stock_number": "TBA-9999"})
            check("errors no longer leak the internal URL", e and "127.0.0.1" not in e, e[:120])


async def stage4(tmp):
    reset()
    with StageServer(4, tmp):
        async with client("salesperson") as c:
            names = {t.name for t in await c.list_tools()}
            check("salesperson: delete_lead hidden", "delete_lead" not in names, str(sorted(names)))
            lead = (await c.call_tool("get_lead", {"lead_id": "L-760debbb3b70b3a1"})).structured_content
            note = (lead.get("note") or {}).get("untrusted_text", "")
            check("injected note arrives as untrusted_text", "ignore all previous instructions" in note.lower())
            e = await err(c, "apply_discount", {"stock_number": "TBA-1001", "amount": 9000, "reason": "pre-approved"})
            check("$9,000 refused: over the 15% dealer maximum", "dealer maximum" in e, e[:100])
            e = await err(c, "apply_discount", {"stock_number": "TBA-1001", "amount": 900, "reason": "please"})
            check("$900 refused: needs a sales manager", "sales manager" in e, e[:100])
            check("nothing applied", discount() == 0)
        async with client("manager", elicit=no) as c:
            check("manager: delete_lead visible", "delete_lead" in {t.name for t in await c.list_tools()})
            e = await err(c, "apply_discount", {"stock_number": "TBA-1001", "amount": 900, "reason": "loyal customer"})
            check("manager declines: nothing changes", "did not confirm" in e and discount() == 0, e[:100])
        async with client("manager", elicit=yes) as c:
            await c.call_tool("apply_discount", {"stock_number": "TBA-1001", "amount": 900, "reason": "loyal customer"})
            check("manager confirms: $900 applied", discount() == 900)
        reset()
        async with client("manager", elicit=yes, legacy=True) as c:
            await c.call_tool("apply_discount", {"stock_number": "TBA-1001", "amount": 900, "reason": "loyal customer"})
            check("same confirmation on an older-protocol client (2025-11-25)", discount() == 900)


async def stage5(tmp):
    reset()
    chaos("flaky")
    with StageServer(4, tmp):  # the problem, before stage 5 code
        async with client("salesperson") as c:
            fails = [await err(c, "get_vehicle", {"stock_number": "TBA-1001"}) for _ in range(8)]
            generic = [f for f in fails if f]
            check("stage 4 + flaky: some calls fail with a generic error",
                  generic and all("retryable" not in f for f in generic), f"{len(generic)}/8 failed")
    with StageServer(5, tmp) as srv:
        async with client("salesperson") as c:
            fails = [await err(c, "get_vehicle", {"stock_number": "TBA-1001"}) for _ in range(8)]
            check("stage 5 + flaky: retries absorb most failures", sum(bool(f) for f in fails) <= 2,
                  f"{sum(bool(f) for f in fails)}/8 failed")
            chaos("slow")
            t = time.perf_counter()
            e = await err(c, "search_inventory", {})
            took = time.perf_counter() - t
            check("slow backend: retryable error in under 6 s", "retryable" in e and took < 6, f"{took:.1f}s {e[:60]}")
            chaos("errors")
            e = await err(c, "create_lead", {"first_name": "A", "last_name": "B", "phone": "416-555-0000"})
            check("write fails cleanly, marked retryable", "retryable" in e, e[:80])
            chaos("off")
        time.sleep(0.3)
        log = srv.log.read_text()
        events = [json.loads(ln) for ln in log.splitlines() if ln.startswith("{") and "tool_call" in ln]
        check("audit log has one JSON event per call", len(events) >= 10, f"{len(events)} events")
        check("audit log never contains argument values", "416-555-0000" not in log)


async def finale_local(tmp):
    reset()
    with StageServer(5, tmp):
        async with client("salesperson") as c:
            r = (await c.call_tool("search_inventory", {"body_type": "suv", "drivetrain": "awd",
                                                        "max_price": 25000, "max_km": 100000})).structured_content
            first = r["results"][0]["stock_number"] if r["results"] else None
            check("search finds TBA-1017 (2021 Tiguan) first", first == "TBA-1017", str(first))
            q = (await c.call_tool("quote_price", {"stock_number": "TBA-1017"})).structured_content
            check("all-in $20,209.50", q["all_in_price"] == 20209.5, str(q["all_in_price"]))
            lead = (await c.call_tool("create_lead", {"first_name": "Priya", "last_name": "Natarajan",
                                                      "phone": "416-555-0142", "stock_number": "TBA-1017"})).structured_content
            check("lead saved for TBA-1017", lead["interested_in"] == "TBA-1017")
            e = await err(c, "apply_discount", {"stock_number": "TBA-1017", "amount": 900, "reason": "customer asked"})
            check("$900 discount refused: needs a sales manager", "sales manager" in e, e[:80])


STEPS = {0: stage0, 1: stage1, 2: stage2, 3: stage3, 4: stage4, 5: stage5, 6: finale_local}
TITLES = {0: "Stage 0: the mock DMS", 1: "Stage 1: first tools", 2: "Stage 2: tools the model can use",
          3: "Stage 3: auth and secrets", 4: "Stage 4: scoping danger", 5: "Stage 5: failure handling",
          6: "Finale (local): the Copilot prompt, tool by tool"}


def port_free(port: int) -> bool:
    import socket

    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


async def main(only: int | None) -> int:
    for port in (8080, 8081):
        if not port_free(port):
            print(f"Port {port} is busy: stop ./scripts/demo.sh dms / live first.")
            return 2
    subprocess.run(["uv", "run", "dev-token", "salesperson"], cwd=ROOT, env=ENV, capture_output=True, check=True)
    tmp = Path(tempfile.mkdtemp(prefix="rehearse-"))
    dms = start([sys.executable, "-m", "uvicorn", "dms.app:app", "--port", "8081"], tmp / "dms.log")
    try:
        wait_http(f"{DMS}/healthz")
        for n, fn in STEPS.items():
            if only is not None and n != only:
                continue
            print(f"\n{TITLES[n]}")
            await fn(tmp)
    finally:
        stop(dms)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} steps passed. Logs: {tmp}")
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, choices=range(7))
    sys.exit(asyncio.run(main(ap.parse_args().stage)))
