"""Write tools: masking, idempotency, ownership."""

import pytest
from fastmcp.exceptions import ToolError

from dms import app as dms_app

LEAD = {
    "first_name": "Priya",
    "last_name": "Natarajan",
    "phone": "416-555-0142",
    "email": "priya@example.com",
    "stock_number": "TBA-1004",
}


async def test_create_lead_returns_masked_data(connect):
    async with connect() as c:
        lead = (await c.call_tool("create_lead", LEAD)).structured_content
    assert lead["name"] == "Priya N."
    assert lead["phone"] == "***-***-0142"
    assert lead["email"] == "p***@example.com"
    stored = dms_app.State.store.leads[lead["lead_id"]]
    assert stored.phone == "416-555-0142", "full data stays in the backend"


async def test_retrying_create_lead_does_not_duplicate(connect):
    async with connect() as c:
        a = (await c.call_tool("create_lead", LEAD)).structured_content
        b = (await c.call_tool("create_lead", LEAD)).structured_content
    assert a["lead_id"] == b["lead_id"]
    assert sum(1 for x in dms_app.State.store.leads.values() if x.last_name == "Natarajan") == 1


async def test_cannot_read_another_salespersons_lead(connect):
    others = [lid for lid, x in dms_app.State.store.leads.items() if x.owner_oid == "someone-else"]
    async with connect("salesperson") as c:
        with pytest.raises(ToolError, match="not found"):
            await c.call_tool("get_lead", {"lead_id": others[0]})
    async with connect("manager") as c:
        assert (await c.call_tool("get_lead", {"lead_id": others[0]})).structured_content[
            "lead_id"
        ] == others[0]


async def test_book_test_drive_end_to_end(connect):
    async with connect() as c:
        lead = (await c.call_tool("create_lead", LEAD)).structured_content
        from datetime import date, timedelta

        day = date.today() + timedelta(days=2)
        if day.weekday() == 6:
            day += timedelta(days=1)
        slots = (
            await c.call_tool("check_test_drive_slots", {"day": day.isoformat()})
        ).structured_content["available"]
        booking = (
            await c.call_tool(
                "book_test_drive",
                {"lead_id": lead["lead_id"], "stock_number": "TBA-1004", "slot": slots[0]},
            )
        ).structured_content
        again = (
            await c.call_tool(
                "book_test_drive",
                {"lead_id": lead["lead_id"], "stock_number": "TBA-1004", "slot": slots[0]},
            )
        ).structured_content
        after = (
            await c.call_tool("check_test_drive_slots", {"day": day.isoformat()})
        ).structured_content["available"]
    assert booking["booking_id"] == again["booking_id"], "idempotent retry"
    assert slots[0] not in after


@pytest.mark.parametrize(
    "bad", [{"phone": "4165550142"}, {"email": "not-an-email"}, {"first_name": "x" * 41}]
)
async def test_create_lead_validates_input(connect, bad):
    async with connect() as c:
        with pytest.raises(ToolError):
            await c.call_tool("create_lead", {**LEAD, **bad})
