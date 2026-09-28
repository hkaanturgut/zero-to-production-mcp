"""HTTP client for the mock DMS, with the resilience a real backend needs.

* Hard timeouts on every call, so a slow backend never hangs the agent.
* Bounded retries with jittered backoff, for reads only. Writes are retried by
  the agent at most, and they carry an idempotency key so a retry is safe.
* A small circuit breaker: after repeated failures we fail fast for a while
  instead of piling more load onto a struggling backend.
* Backend details (hostnames, bodies, stack traces) never leave this module.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import date, datetime
from typing import Any

import httpx

from server.backend.base import BackendUnavailable, Conflict, NotFound

log = logging.getLogger("dealer.backend")


class CircuitBreaker:
    def __init__(self, threshold: int = 5, reset_after_s: float = 30.0) -> None:
        self.threshold = threshold
        self.reset_after_s = reset_after_s
        self.failures = 0
        self.opened_at: float | None = None

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        if time.monotonic() - self.opened_at >= self.reset_after_s:
            return True  # half-open: let one request probe the backend
        return False

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()


class MockDmsClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_s: float = 3.0,
        read_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-API-Key": api_key},
            timeout=httpx.Timeout(timeout_s, connect=2.0),
            transport=transport,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )
        self._read_retries = read_retries
        self._timeout_s = timeout_s
        self.breaker = breaker or CircuitBreaker()

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------ core

    async def _request(
        self, method: str, path: str, *, headers: dict | None = None, **kw: Any
    ) -> dict:
        if not self.breaker.allow():
            raise BackendUnavailable(
                "The dealer system is temporarily unavailable. Try again shortly."
            )
        attempts = 1 + (self._read_retries if method == "GET" else 0)
        for attempt in range(attempts):
            try:
                # httpx timeouts are per phase (connect, read...). This is the
                # total budget for one attempt, whatever the backend does.
                async with asyncio.timeout(self._timeout_s):
                    resp = await self._client.request(method, path, headers=headers, **kw)
            except (httpx.TransportError, TimeoutError) as exc:  # timeouts, connection errors
                log.warning(
                    "dms transport error", extra={"path": path, "error": type(exc).__name__}
                )
                resp = None
            if resp is not None and resp.status_code < 500:
                self.breaker.success()
                return self._handle(resp)
            self.breaker.failure()
            if attempt + 1 < attempts:
                await asyncio.sleep(0.2 * (2**attempt) + random.uniform(0, 0.1))  # noqa: S311
        raise BackendUnavailable("The dealer system did not respond in time. Try again shortly.")

    @staticmethod
    def _handle(resp: httpx.Response) -> dict:
        if resp.status_code == 404:
            raise NotFound("not found")
        if resp.status_code == 409:
            raise Conflict(resp.json().get("detail", "conflict"))
        if resp.status_code in (401, 403):
            # Our service credential is wrong. Log it; never tell the model why.
            log.error("dms rejected service credential", extra={"status": resp.status_code})
            raise BackendUnavailable("The dealer system is temporarily unavailable.")
        if resp.status_code == 422:
            raise Conflict("the dealer system rejected the request")
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _caller(caller_id: str, is_manager: bool = False) -> dict:
        return {"X-Caller-Oid": caller_id, "X-Caller-Is-Manager": str(is_manager).lower()}

    # ------------------------------------------------------------ API

    async def search_vehicles(self, *, limit: int, offset: int, **filters: Any) -> dict:
        params = {k: v for k, v in filters.items() if v is not None}
        return await self._request(
            "GET", "/vehicles", params={**params, "limit": limit, "offset": offset}
        )

    async def get_vehicle(self, stock_number: str) -> dict:
        return await self._request("GET", f"/vehicles/{stock_number}")

    async def get_fees(self) -> list[dict]:
        return (await self._request("GET", "/dealer/fees"))["fees"]

    async def test_drive_slots(self, day: date) -> list[str]:
        return (await self._request("GET", "/test-drives/slots", params={"day": day.isoformat()}))[
            "slots"
        ]

    async def create_lead(self, lead: dict, *, caller_id: str, idempotency_key: str) -> dict:
        return await self._request(
            "POST",
            "/leads",
            json=lead,
            headers={**self._caller(caller_id), "Idempotency-Key": idempotency_key},
        )

    async def get_lead(self, lead_id: str, *, caller_id: str, is_manager: bool) -> dict:
        return await self._request(
            "GET", f"/leads/{lead_id}", headers=self._caller(caller_id, is_manager)
        )

    async def book_test_drive(
        self,
        *,
        lead_id: str,
        stock_number: str,
        slot: datetime,
        caller_id: str,
        is_manager: bool,
        idempotency_key: str,
    ) -> dict:
        return await self._request(
            "POST",
            "/test-drives",
            json={"lead_id": lead_id, "stock_number": stock_number, "slot": slot.isoformat()},
            headers={**self._caller(caller_id, is_manager), "Idempotency-Key": idempotency_key},
        )

    async def apply_discount(
        self,
        stock_number: str,
        *,
        amount: float,
        reason: str,
        approved_by: str | None,
        idempotency_key: str,
    ) -> dict:
        return await self._request(
            "POST",
            f"/vehicles/{stock_number}/discount",
            json={"amount": amount, "reason": reason, "approved_by": approved_by},
            headers={"Idempotency-Key": idempotency_key},
        )

    async def mark_sold(self, stock_number: str) -> dict:
        return await self._request("POST", f"/vehicles/{stock_number}/sold")

    async def delete_lead(self, lead_id: str, *, caller_id: str, is_manager: bool) -> dict:
        return await self._request(
            "DELETE", f"/leads/{lead_id}", headers=self._caller(caller_id, is_manager)
        )
