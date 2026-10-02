"""Every live-coding checkpoint must run. If a stage breaks, the runbook breaks."""

import importlib.util
import os
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from conftest import DMS_KEY, _free_port, always_yes, token
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.exceptions import ToolError

from dms import app as dms_app

STAGES = Path(__file__).parent.parent / "workshop" / "stages"


def _run(app) -> str:
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}"


@pytest.fixture(scope="module")
def dms_url():
    return _run(dms_app.app)


@pytest.fixture(scope="module")
def stage(dms_url, keys, tmp_path_factory):
    pub = tmp_path_factory.mktemp("livekeys") / "pub.pem"
    pub.write_text(keys.public_key)
    started = {}

    def _stage(n: int) -> str:
        if n in started:
            return started[n]
        os.environ.update(
            DMS_BASE_URL=dms_url,
            DMS_API_KEY=DMS_KEY,
            AUTH_MODE="local",
            LOCAL_JWT_PUBLIC_KEY=str(pub),
            PUBLIC_BASE_URL="http://127.0.0.1",
        )
        spec = importlib.util.spec_from_file_location(f"stage_{n}", STAGES / f"stage_{n}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        started[n] = _run(mod.app) + "/mcp"
        return started[n]

    return _stage


def client(url, keys=None, persona=None, elicit=None):
    auth = BearerAuth(token(keys, persona)) if persona else None
    return Client(url, auth=auth, elicitation_handler=elicit)


def test_live_server_on_main_is_stage_5():
    live = Path(__file__).parent.parent / "src" / "live" / "server.py"
    assert live.read_text() == (STAGES / "stage_5.py").read_text()


async def test_stage_1_first_tools(stage):
    async with client(stage(1)) as c:
        assert {t.name for t in await c.list_tools()} == {"search_inventory", "get_vehicle"}
        car = (await c.call_tool("get_vehicle", {"stock_number": "TBA-1001"})).structured_content
    assert "vin" in car  # the stage-2 lesson: raw backend dumps leak data


async def test_stage_2_contracts(stage):
    async with client(stage(2)) as c:
        q = (await c.call_tool("quote_price", {"stock_number": "TBA-1001"})).structured_content
        car = (await c.call_tool("get_vehicle", {"stock_number": "TBA-1001"})).structured_content
        with pytest.raises(ToolError):
            await c.call_tool("get_vehicle", {"stock_number": "../admin"})
    assert "HST and licensing" in q["disclosure"] and "vin" not in car


async def test_stage_3_auth(stage, keys):
    with pytest.raises(Exception):  # noqa: B017 - any refusal is fine, 401 is checked in test_auth
        async with client(stage(3)) as c:
            await c.list_tools()
    async with client(stage(3), keys, "salesperson") as c:
        lead = (
            await c.call_tool(
                "create_lead", {"first_name": "Ana", "last_name": "Lee", "phone": "416-555-0101"}
            )
        ).structured_content
    assert lead["phone"] == "***-***-0101"


async def test_stage_4_scopes_and_confirmation(stage, keys):
    async with client(stage(4), keys, "salesperson", always_yes) as c:
        assert "delete_lead" not in {t.name for t in await c.list_tools()}
        with pytest.raises(ToolError, match="sales manager"):
            await c.call_tool(
                "apply_discount", {"stock_number": "TBA-1001", "amount": 900, "reason": "x" * 5}
            )
    async with client(stage(4), keys, "manager", always_yes) as c:
        await c.call_tool(
            "apply_discount",
            {"stock_number": "TBA-1001", "amount": 900, "reason": "loyal customer"},
        )
    assert dms_app.State.store.vehicles["TBA-1001"].discount == 900


async def test_stage_5_failures(stage, keys):
    dms_app.State.chaos = "errors"
    started = time.perf_counter()
    async with client(stage(5), keys, "salesperson") as c:
        with pytest.raises(ToolError, match="retryable"):
            await c.call_tool("search_inventory", {})
    assert time.perf_counter() - started < 5
