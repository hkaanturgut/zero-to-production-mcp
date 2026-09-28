"""Read tools (permission: dms.read). No side effects, safe to retry."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from server.domain import finance, pricing
from server.tools.common import READ_ONLY, READ_TAG, Deps, call_backend

StockNumber = Annotated[
    str, Field(pattern=r"^TBA-\d{4}$", description="Stock number, e.g. TBA-1001")
]
BodyType = Literal["sedan", "suv", "truck", "hatchback", "minivan", "wagon"]
Drivetrain = Literal["fwd", "rwd", "awd", "4wd"]
PAGE_SIZE = 10


class VehicleSummary(BaseModel):
    stock_number: str
    year: int
    make: str
    model: str
    trim: str
    body_type: str
    drivetrain: str
    km: int
    price: float = Field(
        description="Vehicle price before fees. Use quote_price for the all-in price."
    )
    certified: bool


class SearchResult(BaseModel):
    results: list[VehicleSummary]
    page: int
    total: int
    has_more: bool


class VehicleDetail(VehicleSummary):
    colour: str
    carfax_available: bool
    status: str


class FeeLine(BaseModel):
    label: str
    amount: float


class Quote(BaseModel):
    stock_number: str
    vehicle_price: float
    discount: float
    fees: list[FeeLine]
    all_in_price: float
    hst_estimate: float
    total_with_hst: float
    disclosure: str


class PaymentEstimate(BaseModel):
    stock_number: str
    financed_amount: float
    term_months: int
    apr_percent: float
    monthly_payment: float
    biweekly_payment: float
    total_interest: float
    disclaimer: str


class Slots(BaseModel):
    date: str
    available: list[str]


def _summary(v: dict) -> VehicleSummary:
    return VehicleSummary(price=v["list_price"] - v.get("discount", 0), **v)


def register(mcp: FastMCP, deps: Deps) -> None:
    @mcp.tool(tags={READ_TAG}, annotations=READ_ONLY)
    async def search_inventory(
        make: Annotated[str | None, Field(max_length=30)] = None,
        model: Annotated[str | None, Field(max_length=30)] = None,
        body_type: BodyType | None = None,
        drivetrain: Drivetrain | None = None,
        max_price: Annotated[int | None, Field(ge=1000, le=200_000)] = None,
        max_km: Annotated[int | None, Field(ge=0, le=500_000)] = None,
        min_year: Annotated[int | None, Field(ge=2000, le=2030)] = None,
        page: Annotated[int, Field(ge=1, le=20)] = 1,
    ) -> SearchResult:
        """Search available cars on the lot. Returns up to 10 per page, cheapest first.

        Use this to find candidates. Prices here exclude fees: always call
        quote_price before telling a customer what a car costs.
        """
        data = await call_backend(
            lambda: deps.backend.search_vehicles(
                limit=PAGE_SIZE,
                offset=(page - 1) * PAGE_SIZE,
                make=make,
                model=model,
                body_type=body_type,
                drivetrain=drivetrain,
                max_price=max_price,
                max_km=max_km,
                min_year=min_year,
            )
        )
        return SearchResult(
            results=[_summary(v) for v in data["items"]],
            page=page,
            total=data["total"],
            has_more=page * PAGE_SIZE < data["total"],
        )

    @mcp.tool(tags={READ_TAG}, annotations=READ_ONLY)
    async def get_vehicle(stock_number: StockNumber) -> VehicleDetail:
        """Get full details for one car by stock number."""
        v = await call_backend(lambda: deps.backend.get_vehicle(stock_number))
        return VehicleDetail(price=v["list_price"] - v.get("discount", 0), **v)

    @mcp.tool(tags={READ_TAG}, annotations=READ_ONLY)
    async def quote_price(stock_number: StockNumber) -> Quote:
        """Quote the all-in price for a car: price, every dealer fee, any discount, HST estimate.

        This is the only correct source for what a car costs. Never add fees or
        tax yourself.
        """
        v = await call_backend(lambda: deps.backend.get_vehicle(stock_number))
        if v["status"] != "available":
            raise ToolError(f"{stock_number} is not available (status: {v['status']}).")
        fees = await call_backend(deps.backend.get_fees)
        return Quote(
            stock_number=stock_number,
            **pricing.all_in_quote(v["list_price"], fees, v.get("discount", 0)),
        )

    @mcp.tool(tags={READ_TAG}, annotations=READ_ONLY)
    async def estimate_payment(
        stock_number: StockNumber,
        term_months: Literal[36, 48, 60, 72, 84] = 60,
        down_payment: Annotated[float, Field(ge=0, le=200_000)] = 0,
    ) -> PaymentEstimate:
        """Estimate monthly and bi-weekly loan payments for a car, including HST.

        An estimate only. Never tell a customer they are approved.
        """
        v = await call_backend(lambda: deps.backend.get_vehicle(stock_number))
        fees = await call_backend(deps.backend.get_fees)
        quote = pricing.all_in_quote(v["list_price"], fees, v.get("discount", 0))
        try:
            est = finance.estimate(quote["total_with_hst"], down_payment, term_months)
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        return PaymentEstimate(stock_number=stock_number, **est)

    @mcp.tool(tags={READ_TAG}, annotations=READ_ONLY)
    async def check_test_drive_slots(day: date) -> Slots:
        """List open one-hour test-drive slots for a date in the next 30 days. Closed Sundays."""
        today = date.today()
        if not today <= day <= today + timedelta(days=30):
            raise ToolError("Pick a date between today and 30 days from now.")
        slots = await call_backend(lambda: deps.backend.test_drive_slots(day))
        return Slots(date=day.isoformat(), available=slots)
