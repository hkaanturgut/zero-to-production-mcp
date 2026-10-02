"""Business policy, confirmation, and the prompt-injection lead."""

import json
from types import SimpleNamespace

import pytest
from conftest import always_no, always_yes
from fastmcp.exceptions import ToolError

from dms import app as dms_app
from server.tools.common import confirmation


def discount(stock="TBA-1001"):
    return dms_app.State.store.vehicles[stock].discount


async def test_salesperson_small_discount_no_confirmation_needed(connect):
    async with connect("salesperson") as c:  # no elicitation handler at all
        r = (
            await c.call_tool(
                "apply_discount",
                {"stock_number": "TBA-1001", "amount": 400, "reason": "trade-in bonus"},
            )
        ).structured_content
    assert r["discount"] == 400 and discount() == 400


async def test_salesperson_cannot_exceed_limit(connect):
    async with connect("salesperson", elicit=always_yes) as c:
        with pytest.raises(ToolError, match="need a sales manager"):
            await c.call_tool(
                "apply_discount", {"stock_number": "TBA-1001", "amount": 900, "reason": "please"}
            )
    assert discount() == 0


async def test_agent_identity_cannot_exceed_limit_even_if_user_says_yes(connect):
    async with connect("agent", elicit=always_yes) as c:
        with pytest.raises(ToolError, match="need a sales manager"):
            await c.call_tool(
                "apply_discount",
                {"stock_number": "TBA-1001", "amount": 900, "reason": "pre-approved"},
            )
    assert discount() == 0


async def test_manager_big_discount_needs_human_yes(connect):
    async with connect("manager", elicit=always_yes) as c:
        r = (
            await c.call_tool(
                "apply_discount",
                {"stock_number": "TBA-1001", "amount": 900, "reason": "loyal customer"},
            )
        ).structured_content
    assert r["approved_by"] == "Maya Manager" and discount() == 900


async def test_manager_declines_confirmation_nothing_changes(connect):
    async with connect("manager", elicit=always_no) as c:
        with pytest.raises(ToolError, match="did not confirm"):
            await c.call_tool(
                "apply_discount",
                {"stock_number": "TBA-1001", "amount": 900, "reason": "loyal customer"},
            )
    assert discount() == 0


async def test_nobody_can_exceed_dealer_maximum(connect):
    async with connect("manager", elicit=always_yes) as c:
        with pytest.raises(ToolError, match="dealer maximum"):
            await c.call_tool(
                "apply_discount",
                {"stock_number": "TBA-1001", "amount": 9000, "reason": "the note said so"},
            )
    assert discount() == 0


async def test_injection_in_lead_note_is_returned_as_untrusted_data(connect):
    injected = next(
        x for x in dms_app.State.store.leads.values() if x.note and "IGNORE" in x.note.upper()
    )
    async with connect("salesperson") as c:
        lead = (await c.call_tool("get_lead", {"lead_id": injected.lead_id})).structured_content
        # Even if a model obeyed the note, the policy still blocks it.
        with pytest.raises(ToolError):
            await c.call_tool(
                "apply_discount",
                {"stock_number": "TBA-1001", "amount": 9000, "reason": "pre-approved"},
            )
    assert set(lead["note"]) == {"untrusted_text"}
    assert discount() == 0


async def test_manager_delete_lead_requires_confirmation(connect):
    lead_id = next(iter(dms_app.State.store.leads))
    async with connect("manager", elicit=always_no) as c:
        with pytest.raises(ToolError, match="did not confirm"):
            await c.call_tool("delete_lead", {"lead_id": lead_id})
    assert not dms_app.State.store.leads[lead_id].deleted
    async with connect("manager", elicit=always_yes) as c:
        assert (await c.call_tool("delete_lead", {"lead_id": lead_id})).structured_content[
            "deleted"
        ]
    assert dms_app.State.store.leads[lead_id].deleted


async def test_mark_sold_requires_manager_and_confirmation(connect):
    async with connect("manager", elicit=always_yes) as c:
        r = (
            await c.call_tool("mark_vehicle_sold", {"stock_number": "TBA-1002"})
        ).structured_content
    assert r["status"] == "sold"


async def test_confirmation_rejects_state_tampering():
    """If arguments change between the question and the answer, nothing happens."""
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(protocol_version="2026-07-28"),
        input_responses={"confirm": SimpleNamespace(action="accept", content={"confirm": True})},
        request_state=json.dumps({"tool": "apply_discount", "stock": "TBA-1001", "amount": 600}),
    )
    with pytest.raises(ToolError, match="changed after it was confirmed"):
        await confirmation(
            ctx, message="x", state={"tool": "apply_discount", "stock": "TBA-1001", "amount": 4000}
        )
