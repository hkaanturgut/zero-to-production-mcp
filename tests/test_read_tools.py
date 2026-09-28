"""Read tools: correctness, pagination, input validation."""

from datetime import date, timedelta

import pytest
from fastmcp.exceptions import ToolError


async def test_search_filters_and_sorts(connect):
    async with connect() as c:
        r = (
            await c.call_tool(
                "search_inventory", {"body_type": "suv", "drivetrain": "awd", "max_price": 25000}
            )
        ).structured_content
    assert r["results"], "expected matches"
    prices = [v["price"] for v in r["results"]]
    assert prices == sorted(prices)
    assert all(
        v["body_type"] == "suv" and v["drivetrain"] == "awd" and v["price"] <= 25000
        for v in r["results"]
    )
    assert "vin" not in r["results"][0], "data minimisation: VIN is not needed to shop"


async def test_search_paginates(connect):
    async with connect() as c:
        p1 = (await c.call_tool("search_inventory", {})).structured_content
        p2 = (await c.call_tool("search_inventory", {"page": 2})).structured_content
    assert len(p1["results"]) == 10 and p1["has_more"]
    assert {v["stock_number"] for v in p1["results"]}.isdisjoint(
        v["stock_number"] for v in p2["results"]
    )


async def test_sold_cars_hidden_from_search(connect):
    async with connect() as c:
        r = (await c.call_tool("search_inventory", {"page": 1})).structured_content
        allc = [
            v
            for p in (1, 2, 3, 4)
            for v in (await c.call_tool("search_inventory", {"page": p})).structured_content[
                "results"
            ]
        ]
    assert r["total"] == len(allc) < 40


async def test_quote_is_all_in_and_itemized(connect):
    async with connect() as c:
        q = (await c.call_tool("quote_price", {"stock_number": "TBA-1001"})).structured_content
    assert q["all_in_price"] == round(
        q["vehicle_price"] - q["discount"] + sum(f["amount"] for f in q["fees"]), 2
    )
    assert "HST and licensing are extra" in q["disclosure"]


async def test_payment_estimate_never_promises_approval(connect):
    async with connect() as c:
        e = (
            await c.call_tool(
                "estimate_payment",
                {"stock_number": "TBA-1001", "term_months": 60, "down_payment": 5000},
            )
        ).structured_content
    assert e["monthly_payment"] > 0
    assert "Not an offer or approval" in e["disclaimer"]


@pytest.mark.parametrize("stock", ["1001", "TBA-1", "'; DROP TABLE cars;--", "../../etc/passwd"])
async def test_invalid_stock_numbers_rejected_before_backend(connect, stock):
    async with connect() as c:
        with pytest.raises(ToolError):
            await c.call_tool("get_vehicle", {"stock_number": stock})


async def test_unknown_vehicle_gives_actionable_error(connect):
    async with connect() as c:
        with pytest.raises(ToolError, match="not found"):
            await c.call_tool("get_vehicle", {"stock_number": "TBA-9999"})


async def test_slots_limited_to_next_30_days(connect):
    async with connect() as c:
        with pytest.raises(ToolError, match="30 days"):
            await c.call_tool(
                "check_test_drive_slots", {"day": (date.today() + timedelta(days=60)).isoformat()}
            )
