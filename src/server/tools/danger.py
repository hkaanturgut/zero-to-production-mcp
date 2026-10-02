"""Manager-only tools (permission: dms.manager). Always confirmed by a human."""

from __future__ import annotations

from fastmcp import Context, FastMCP
from pydantic import BaseModel

from server.auth import current_caller
from server.tools.common import DESTRUCTIVE, MANAGER_TAG, Deps, call_backend, confirmation
from server.tools.read import StockNumber
from server.tools.write import LeadId


class SoldResult(BaseModel):
    stock_number: str
    status: str


class DeleteResult(BaseModel):
    lead_id: str
    deleted: bool


def register(mcp: FastMCP, deps: Deps) -> None:
    @mcp.tool(tags={MANAGER_TAG}, annotations=DESTRUCTIVE)
    async def mark_vehicle_sold(stock_number: StockNumber, ctx: Context) -> SoldResult:
        """Mark a car as sold and remove it from the lot. Manager only; asks for confirmation."""
        caller = current_caller()
        v = await call_backend(lambda: deps.backend.get_vehicle(stock_number))
        ask = await confirmation(
            ctx,
            message=f"Mark {v['year']} {v['make']} {v['model']} ({stock_number}) as SOLD?",
            state={"tool": "mark_vehicle_sold", "stock": stock_number, "by": caller.id},
        )
        if ask is not None:
            return ask  # type: ignore[return-value]
        return SoldResult(**await call_backend(lambda: deps.backend.mark_sold(stock_number)))

    @mcp.tool(tags={MANAGER_TAG}, annotations=DESTRUCTIVE)
    async def delete_lead(lead_id: LeadId, ctx: Context) -> DeleteResult:
        """Delete a lead (soft delete, kept in the audit trail).

        Manager only; always asks for confirmation.
        """
        caller = current_caller()
        ask = await confirmation(
            ctx,
            message=f"Delete lead {lead_id}? This removes it from every salesperson's list.",
            state={"tool": "delete_lead", "lead": lead_id, "by": caller.id},
        )
        if ask is not None:
            return ask  # type: ignore[return-value]
        res = await call_backend(
            lambda: deps.backend.delete_lead(lead_id, caller_id=caller.id, is_manager=True)
        )
        return DeleteResult(**res)
