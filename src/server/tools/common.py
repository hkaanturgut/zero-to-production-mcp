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


def confirmation(
    ctx: Context, *, message: str, state: dict[str, Any]
) -> mcp_types.InputRequiredResult | None:
    """Ask the human to confirm, using the 2026-07-28 multi round-trip flow.

    Round 1: returns an InputRequiredResult; the client shows the question.
    Round 2: the client retries the same call with the answer. We check the
    answer, and check that the arguments still match what was confirmed
    (the framework seals request_state, so it cannot be forged).

    Returns None when confirmed; raises ToolError when declined or tampered.
    """
    responses = ctx.input_responses
    if not responses:
        return mcp_types.InputRequiredResult(
            input_requests={
                "confirm": mcp_types.ElicitRequest(
                    params=mcp_types.ElicitRequestFormParams(
                        message=message,
                        requested_schema={
                            "type": "object",
                            "properties": {
                                "confirm": {
                                    "type": "boolean",
                                    "title": "Confirm",
                                    "description": message,
                                }
                            },
                            "required": ["confirm"],
                        },
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
