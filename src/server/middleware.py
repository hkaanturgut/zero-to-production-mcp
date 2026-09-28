"""Cross-cutting concerns applied to every tool call."""

from __future__ import annotations

import json
import logging
import time
import uuid

from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware, MiddlewareContext

audit_log = logging.getLogger("dealer.audit")


def caller_key(context: MiddlewareContext) -> str:
    """Rate-limit bucket: one per verified caller, never per IP or argument."""
    token = get_access_token()
    if token is None:
        return "anonymous"
    claims = token.claims or {}
    return str(claims.get("oid") or claims.get("sub") or "anonymous")


class AuditMiddleware(Middleware):
    """One structured audit event per tool call, for success and failure alike.

    Records who, what, outcome and duration. Argument *names* are logged, never
    values: values can hold personal data, and logs are read by more people
    than the database is.
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        correlation_id = uuid.uuid4().hex
        started = time.perf_counter()
        token = get_access_token()
        claims = (token.claims or {}) if token else {}
        params = context.message
        event = {
            "event": "tool_call",
            "correlation_id": correlation_id,
            "tool": getattr(params, "name", None),
            "arg_names": sorted((getattr(params, "arguments", None) or {}).keys()),
            "caller_id": claims.get("oid") or claims.get("sub"),
            "caller_kind": "app" if claims.get("idtyp") == "app" else "user",
            "permissions": sorted(token.scopes) if token else [],
        }
        try:
            result = await call_next(context)
            outcome = (
                "input_required"
                if getattr(result, "result_type", None) == "input_required"
                else "ok"
            )
            if getattr(result, "is_error", False) or getattr(result, "isError", False):
                outcome = "tool_error"
            event["outcome"] = outcome
            return result
        except Exception as exc:
            event["outcome"] = "denied" if "Authorization" in type(exc).__name__ else "error"
            event["error_type"] = type(exc).__name__
            raise
        finally:
            event["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
            audit_log.info(json.dumps(event))
