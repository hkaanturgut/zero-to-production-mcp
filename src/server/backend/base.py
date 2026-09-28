"""The only way out of the MCP server.

Tools depend on this Protocol, never on HTTP. Swapping the mock DMS for a real
dealer system means writing one new class; auth, policy and tools don't change.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol


class BackendError(Exception):
    """Base class for backend failures. Messages are safe to show the model."""


class BackendUnavailable(BackendError):
    """Timeout, 5xx or open circuit. The caller may retry later."""


class NotFound(BackendError):
    pass


class Conflict(BackendError):
    pass


class DmsBackend(Protocol):
    async def search_vehicles(self, *, limit: int, offset: int, **filters: Any) -> dict: ...

    async def get_vehicle(self, stock_number: str) -> dict: ...

    async def get_fees(self) -> list[dict]: ...

    async def test_drive_slots(self, day: date) -> list[str]: ...

    async def create_lead(self, lead: dict, *, caller_id: str, idempotency_key: str) -> dict: ...

    async def get_lead(self, lead_id: str, *, caller_id: str, is_manager: bool) -> dict: ...

    async def book_test_drive(
        self,
        *,
        lead_id: str,
        stock_number: str,
        slot: datetime,
        caller_id: str,
        is_manager: bool,
        idempotency_key: str,
    ) -> dict: ...

    async def apply_discount(
        self,
        stock_number: str,
        *,
        amount: float,
        reason: str,
        approved_by: str | None,
        idempotency_key: str,
    ) -> dict: ...

    async def mark_sold(self, stock_number: str) -> dict: ...

    async def delete_lead(self, lead_id: str, *, caller_id: str, is_manager: bool) -> dict: ...

    async def aclose(self) -> None: ...
