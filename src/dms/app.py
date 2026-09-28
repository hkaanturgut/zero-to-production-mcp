"""Mock dealer management system (DMS).

Stands in for the dealer's real internal API. It is deliberately a plain REST
service with a static API key, like most internal systems an MCP server wraps.
It must never be exposed to the internet; in Azure it runs with internal
ingress only.
"""

from __future__ import annotations

import asyncio
import hmac
import os
import random
import secrets
from dataclasses import asdict
from datetime import date, datetime, time
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dms.seed import DEALER_FEES, Lead, Store, TestDrive, build_store

ChaosMode = Literal["off", "slow", "errors", "flaky"]


class State:
    store: Store = build_store()
    chaos: ChaosMode = "off"


def _api_key() -> str:
    key = os.environ.get("DMS_API_KEY")
    if not key:
        raise RuntimeError("DMS_API_KEY must be set")
    return key


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    # Constant-time comparison to avoid timing side channels.
    if not x_api_key or not hmac.compare_digest(x_api_key, _api_key()):
        raise HTTPException(status_code=401, detail="invalid api key")


app = FastAPI(title="Mock DMS", docs_url=None, redoc_url=None, openapi_url=None)
Auth = Depends(require_api_key)


@app.middleware("http")
async def chaos_middleware(request: Request, call_next):
    """Inject failures on demand so the workshop can show resilience live."""
    if request.url.path.startswith(("/healthz", "/_chaos")):
        return await call_next(request)
    mode = State.chaos
    if mode == "slow":
        await asyncio.sleep(6)
    elif mode == "errors" or (mode == "flaky" and random.random() < 0.5):  # noqa: S311
        return JSONResponse({"detail": "upstream unavailable"}, status_code=503)
    return await call_next(request)


# ---------------------------------------------------------------- models


class LeadIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=40)
    last_name: str = Field(min_length=1, max_length=40)
    phone: str = Field(pattern=r"^\d{3}-\d{3}-\d{4}$")
    email: str | None = Field(default=None, max_length=120)
    stock_number: str | None = Field(default=None, pattern=r"^TBA-\d{4}$")
    note: str | None = Field(default=None, max_length=500)


class TestDriveIn(BaseModel):
    lead_id: str
    stock_number: str = Field(pattern=r"^TBA-\d{4}$")
    slot: datetime


class DiscountIn(BaseModel):
    amount: float = Field(gt=0)
    reason: str = Field(min_length=3, max_length=200)
    approved_by: str | None = None


class ChaosIn(BaseModel):
    mode: ChaosMode


# ---------------------------------------------------------------- helpers


def _idempotent(key: str | None, scope: str, produce):
    """Return the stored response for a repeated Idempotency-Key."""
    if not key:
        return produce()
    cache_key = f"{scope}:{key}"
    if cache_key not in State.store.idempotency:
        State.store.idempotency[cache_key] = produce()
    return State.store.idempotency[cache_key]


def _vehicle_or_404(stock: str):
    v = State.store.vehicles.get(stock)
    if not v:
        raise HTTPException(404, "vehicle not found")
    return v


def _lead_or_404(lead_id: str, owner: str | None, is_manager: bool) -> Lead:
    lead = State.store.leads.get(lead_id)
    # Same 404 for "missing" and "not yours": never confirm another user's ID exists.
    if not lead or lead.deleted or (not is_manager and lead.owner_oid != owner):
        raise HTTPException(404, "lead not found")
    return lead


def _slots_for(day: date) -> list[datetime]:
    taken = {td.slot for td in State.store.test_drives.values()}
    last = 17 if day.weekday() < 5 else 16
    if day.weekday() == 6:  # closed Sundays
        return []
    return [
        datetime.combine(day, time(h))
        for h in range(9, last + 1)
        if datetime.combine(day, time(h)) not in taken
    ]


# ---------------------------------------------------------------- routes


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/_chaos", dependencies=[Auth])
def set_chaos(body: ChaosIn):
    State.chaos = body.mode
    return {"chaos": State.chaos}


@app.post("/_reset", dependencies=[Auth])
def reset():
    State.store = build_store()
    State.chaos = "off"
    return {"reset": True}


@app.get("/vehicles", dependencies=[Auth])
def list_vehicles(
    make: str | None = None,
    model: str | None = None,
    body_type: str | None = None,
    drivetrain: str | None = None,
    max_price: float | None = None,
    max_km: int | None = None,
    min_year: int | None = None,
    include_sold: bool = False,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    items = [
        v
        for v in State.store.vehicles.values()
        if (include_sold or v.status == "available")
        and (not make or v.make.lower() == make.lower())
        and (not model or v.model.lower() == model.lower())
        and (not body_type or v.body_type == body_type)
        and (not drivetrain or v.drivetrain == drivetrain)
        and (max_price is None or v.list_price - v.discount <= max_price)
        and (max_km is None or v.km <= max_km)
        and (min_year is None or v.year >= min_year)
    ]
    items.sort(key=lambda v: v.list_price - v.discount)
    page = items[offset : offset + limit]
    return {"total": len(items), "items": [asdict(v) for v in page]}


@app.get("/vehicles/{stock}", dependencies=[Auth])
def get_vehicle(stock: str):
    return asdict(_vehicle_or_404(stock))


@app.get("/dealer/fees", dependencies=[Auth])
def fees():
    return {"fees": DEALER_FEES}


@app.post("/vehicles/{stock}/discount", dependencies=[Auth])
def apply_discount(
    stock: str, body: DiscountIn, idempotency_key: Annotated[str | None, Header()] = None
):
    def produce():
        v = _vehicle_or_404(stock)
        if v.status != "available":
            raise HTTPException(409, "vehicle not available")
        v.discount = body.amount
        v.discount_reason = body.reason
        return {"stock_number": stock, "discount": v.discount, "approved_by": body.approved_by}

    return _idempotent(idempotency_key, f"discount:{stock}", produce)


@app.post("/vehicles/{stock}/sold", dependencies=[Auth])
def mark_sold(stock: str):
    v = _vehicle_or_404(stock)
    if v.status == "sold":
        raise HTTPException(409, "already sold")
    v.status = "sold"
    return {"stock_number": stock, "status": v.status}


@app.get("/test-drives/slots", dependencies=[Auth])
def slots(day: date):
    return {"date": day.isoformat(), "slots": [s.isoformat() for s in _slots_for(day)]}


@app.post("/test-drives", dependencies=[Auth])
def book_test_drive(
    body: TestDriveIn,
    x_caller_oid: Annotated[str, Header()],
    x_caller_is_manager: Annotated[str, Header()] = "false",
    idempotency_key: Annotated[str | None, Header()] = None,
):
    def produce():
        _lead_or_404(body.lead_id, x_caller_oid, x_caller_is_manager == "true")
        v = _vehicle_or_404(body.stock_number)
        if v.status != "available":
            raise HTTPException(409, "vehicle not available")
        if body.slot not in _slots_for(body.slot.date()):
            raise HTTPException(409, "slot not available")
        bid = f"TD-{secrets.token_hex(6)}"
        State.store.test_drives[bid] = TestDrive(bid, body.lead_id, body.stock_number, body.slot)
        return {"booking_id": bid, "stock_number": body.stock_number, "slot": body.slot.isoformat()}

    return _idempotent(idempotency_key, "test_drive", produce)


@app.post("/leads", dependencies=[Auth])
def create_lead(
    body: LeadIn,
    x_caller_oid: Annotated[str, Header()],
    idempotency_key: Annotated[str | None, Header()] = None,
):
    def produce():
        # Unguessable ID: possession of an ID is never proof of ownership, but
        # it should not be enumerable either.
        lead_id = f"L-{secrets.token_hex(8)}"
        lead = Lead(
            lead_id=lead_id,
            owner_oid=x_caller_oid,
            created_at=datetime.now(),
            **body.model_dump(),
        )
        State.store.leads[lead_id] = lead
        return _lead_json(lead)

    return _idempotent(idempotency_key, f"lead:{x_caller_oid}", produce)


@app.get("/leads", dependencies=[Auth])
def list_leads(
    x_caller_oid: Annotated[str, Header()],
    x_caller_is_manager: Annotated[str, Header()] = "false",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
):
    mine = [
        _lead_json(lead)
        for lead in State.store.leads.values()
        if not lead.deleted and (x_caller_is_manager == "true" or lead.owner_oid == x_caller_oid)
    ]
    return {"total": len(mine), "items": mine[:limit]}


@app.get("/leads/{lead_id}", dependencies=[Auth])
def get_lead(
    lead_id: str,
    x_caller_oid: Annotated[str, Header()],
    x_caller_is_manager: Annotated[str, Header()] = "false",
):
    return _lead_json(_lead_or_404(lead_id, x_caller_oid, x_caller_is_manager == "true"))


@app.delete("/leads/{lead_id}", dependencies=[Auth])
def delete_lead(
    lead_id: str,
    x_caller_oid: Annotated[str, Header()],
    x_caller_is_manager: Annotated[str, Header()] = "false",
):
    lead = _lead_or_404(lead_id, x_caller_oid, x_caller_is_manager == "true")
    lead.deleted = True  # soft delete, recoverable from the audit trail
    return {"lead_id": lead_id, "deleted": True}


def _lead_json(lead: Lead) -> dict:
    data = asdict(lead)
    data["created_at"] = lead.created_at.isoformat()
    return data


def main() -> None:  # pragma: no cover
    import uvicorn

    _api_key()  # fail fast if not configured
    uvicorn.run(
        "dms.app:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 8081)),
    )
