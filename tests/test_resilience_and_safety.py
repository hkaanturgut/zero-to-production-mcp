"""Failure handling, secret hygiene, error masking, audit and rate limits."""

import asyncio
import json
import logging
import time

import httpx
import pytest
from conftest import DMS_KEY, always_yes
from fastmcp.exceptions import ToolError

from dms import app as dms_app
from server.backend.base import BackendUnavailable
from server.backend.mock_client import CircuitBreaker, MockDmsClient


@pytest.mark.parametrize("mode", ["errors", "slow"])
async def test_backend_outage_becomes_fast_retryable_tool_error(connect, mode):
    dms_app.State.chaos = mode
    started = time.perf_counter()
    async with connect() as c:
        with pytest.raises(ToolError, match="retryable"):
            await c.call_tool("search_inventory", {})
    assert time.perf_counter() - started < 5, "a slow backend must never hang the agent"


async def test_flaky_backend_is_absorbed_by_read_retries(connect):
    dms_app.State.chaos = "flaky"
    dms_app.random.seed(7)  # deterministic coin flips
    ok = 0
    async with connect() as c:
        for _ in range(10):
            try:
                await c.call_tool("get_vehicle", {"stock_number": "TBA-1001"})
                ok += 1
            except ToolError:
                pass
    assert ok >= 7  # 50% failure per attempt, 3 attempts: ~87% succeed


async def test_circuit_breaker_fails_fast_then_recovers():
    breaker = CircuitBreaker(threshold=2, reset_after_s=0.2)
    client = MockDmsClient(
        "http://dms",
        DMS_KEY,
        timeout_s=0.3,
        read_retries=0,
        transport=httpx.ASGITransport(app=dms_app.app),
        breaker=breaker,
    )
    dms_app.State.chaos = "errors"
    for _ in range(2):
        with pytest.raises(BackendUnavailable):
            await client.get_vehicle("TBA-1001")
    dms_app.State.chaos = "off"
    with pytest.raises(BackendUnavailable, match="temporarily unavailable"):
        await client.get_vehicle("TBA-1001")  # open: no call made
    await asyncio.sleep(0.25)
    assert (await client.get_vehicle("TBA-1001"))["stock_number"] == "TBA-1001"  # half-open probe
    await client.aclose()


async def test_writes_are_not_blindly_retried(connect):
    dms_app.State.chaos = "errors"
    async with connect() as c:
        with pytest.raises(ToolError, match="retryable"):
            await c.call_tool(
                "create_lead", {"first_name": "A", "last_name": "B", "phone": "416-555-0000"}
            )
    dms_app.State.chaos = "off"


async def _collect_all_outputs(connect) -> str:
    """Drive every tool, including failures, and return everything a client saw."""
    seen = []
    async with connect("manager", elicit=always_yes) as c:
        seen.append(str(await c.list_tools()))
        calls = [
            ("search_inventory", {}),
            ("get_vehicle", {"stock_number": "TBA-1001"}),
            ("quote_price", {"stock_number": "TBA-1001"}),
            ("estimate_payment", {"stock_number": "TBA-1001"}),
            ("create_lead", {"first_name": "A", "last_name": "B", "phone": "416-555-0000"}),
            ("apply_discount", {"stock_number": "TBA-1003", "amount": 700, "reason": "test"}),
            ("get_vehicle", {"stock_number": "TBA-9999"}),
        ]
        for name, args in calls:
            try:
                seen.append(str(await c.call_tool(name, args)))
            except Exception as exc:  # noqa: BLE001
                seen.append(repr(exc))
        dms_app.State.chaos = "errors"
        try:
            await c.call_tool("search_inventory", {})
        except Exception as exc:  # noqa: BLE001
            seen.append(repr(exc))
    return "\n".join(seen)


async def test_backend_secret_never_reaches_the_client(connect):
    output = await _collect_all_outputs(connect)
    assert DMS_KEY not in output
    assert "X-API-Key" not in output and "http://dms" not in output


async def test_audit_log_has_one_event_per_call_and_no_argument_values(connect, caplog):
    caplog.set_level(logging.INFO, logger="dealer.audit")
    async with connect("salesperson") as c:
        await c.call_tool(
            "create_lead", {"first_name": "Zed", "last_name": "Q", "phone": "416-555-7777"}
        )
    events = [json.loads(r.message) for r in caplog.records if r.name == "dealer.audit"]
    ev = next(e for e in events if e["tool"] == "create_lead")
    assert ev["caller_id"] == "demo-salesperson" and ev["outcome"] == "ok"
    assert ev["arg_names"] == ["first_name", "last_name", "phone"]
    assert "416-555-7777" not in caplog.text and "Zed" not in caplog.text


async def test_unexpected_errors_are_masked(server, connect, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("db at 10.0.0.12:5432 exploded, password=hunter2")

    monkeypatch.setattr(server.backend, "get_fees", boom)
    async with connect() as c:
        with pytest.raises(ToolError) as exc:
            await c.call_tool("quote_price", {"stock_number": "TBA-1001"})
    assert "10.0.0.12" not in str(exc.value) and "hunter2" not in str(exc.value)


async def test_rate_limit_per_caller(limited_server, connect):
    errors = 0
    async with connect("salesperson", url=limited_server.url) as c:
        for _ in range(6):
            try:
                await c.call_tool("get_vehicle", {"stock_number": "TBA-1001"})
            except Exception as exc:  # noqa: BLE001
                errors += "Rate limit" in str(exc)
    assert errors >= 1
