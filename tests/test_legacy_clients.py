"""Handshake-era clients (2025-11-25) still get the same confirmation rules."""

import pytest
from conftest import always_no, always_yes, token
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.exceptions import ToolError

from dms import app as dms_app


def legacy(server, keys, persona, elicit):
    return Client(
        f"{server.url}/mcp",
        auth=BearerAuth(token(keys, persona)),
        elicitation_handler=elicit,
        mode="legacy",
    )


async def test_legacy_client_confirms_big_discount(server, keys):
    async with legacy(server, keys, "manager", always_yes) as c:
        r = await c.call_tool(
            "apply_discount", {"stock_number": "TBA-1001", "amount": 900, "reason": "loyal"}
        )
    assert r.structured_content["discount"] == 900


async def test_legacy_client_decline_changes_nothing(server, keys):
    async with legacy(server, keys, "manager", always_no) as c:
        with pytest.raises(ToolError, match="did not confirm"):
            await c.call_tool(
                "apply_discount", {"stock_number": "TBA-1001", "amount": 900, "reason": "loyal"}
            )
    assert dms_app.State.store.vehicles["TBA-1001"].discount == 0
