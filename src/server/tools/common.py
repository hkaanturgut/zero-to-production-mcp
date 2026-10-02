"""Shared helpers for tools: dependencies, idempotency, confirmation, errors."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import mcp_types
from fastmcp import Context
from fastmcp.exceptions import ToolError
from mcp_types.version import MODERN_PROTOCOL_VERSIONS
from pydantic import BaseModel

from server.auth import Caller
from server.backend.base import BackendError, BackendUnavailable, DmsBackend
from server.config import Settings

T = TypeVar("T")

# Tags decide which permission a tool needs (see server/app.py AuthMiddleware).
READ_TAG, WRITE_TAG, MANAGER_TAG = "read", "write", "manager"

READ_ONLY = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}
WRITE = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
DESTRUCTIVE = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": False,
}


@dataclass
class Deps:
    backend: DmsBackend
    settings: Settings


def idempotency_key(caller: Caller, tool: str, args: dict[str, Any]) -> str:
    """Same caller + same tool + same arguments = same key.

    If an agent retries a write after a timeout, the backend sees the same key
    and returns the original result instead of doing the work twice.
    """
    canonical = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(f"{caller.id}|{tool}|{canonical}".encode()).hexdigest()[:32]


async def call_backend(fn: Callable[[], Awaitable[T]]) -> T:
    """Run a backend call and turn backend failures into messages the model can act on."""
    try:
        return await fn()
    except BackendUnavailable as exc:
        raise ToolError(f"{exc} (retryable)") from None
    except BackendError as exc:
        raise ToolError(str(exc)) from None


class Confirm(BaseModel):
    confirm: bool


def _modern(ctx: Context) -> bool:
    """True on 2026-07-28 connections (multi round-trip); False on handshake-era ones."""
    rc = getattr(ctx, "request_context", None)
    return rc is not None and getattr(rc, "protocol_version", None) in MODERN_PROTOCOL_VERSIONS


async def confirmation(
    ctx: Context, *, message: str, state: dict[str, Any]
) -> mcp_types.InputRequiredResult | None:
    """Ask the human to confirm before a destructive or costly action.

    2026-07-28 clients (stateless): multi round-trip.
      Round 1 returns an InputRequiredResult; the client shows the question.
      Round 2 the client retries the same call with the answer. We check the
      answer and that the arguments still match what was confirmed (the
      framework seals request_state, so it cannot be forged).
    Handshake-era clients (2025-11-25 and earlier): classic elicitation over
      the open session, same question, same rules.

    Returns None when confirmed; raises ToolError when declined or tampered.
    """
    if not _modern(ctx):
        answer = await ctx.elicit(message, response_type=Confirm)
        if getattr(answer, "action", None) != "accept" or not answer.data.confirm:
            raise ToolError("The user did not confirm. Nothing was changed.")
        return None

    responses = ctx.input_responses
    if not responses:
        return mcp_types.InputRequiredResult(
            input_requests={
                "confirm": mcp_types.ElicitRequest(
                    params=mcp_types.ElicitRequestFormParams(
                        message=message,
                        requested_schema=Confirm.model_json_schema(),
                    )
                )
            },
            request_state=json.dumps(state, sort_keys=True, default=str),
        )

    confirmed_state = json.loads(ctx.request_state or "{}")
    if confirmed_state != json.loads(json.dumps(state, sort_keys=True, default=str)):
        raise ToolError("The request changed after it was confirmed. Nothing was done; ask again.")
    answer = responses.get("confirm")
    content = getattr(answer, "content", None) or {}
    if getattr(answer, "action", None) != "accept" or content.get("confirm") is not True:
        raise ToolError("The user did not confirm. Nothing was changed.")
    return None
