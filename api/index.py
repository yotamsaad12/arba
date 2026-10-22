"""Vercel entry point: the whole Arba API as one Python function.

vercel.json sends every /api/... request here; FastAPI routes it by its original path. The
backend is installed as a package from requirements.txt.

If the API can't even start (a missing package, a bad setting), every request answers with
the reason instead of Vercel's bare FUNCTION_INVOCATION_FAILED page, so the deployment can be
fixed without digging through logs. Only the error type and message are shown.
"""

import logging
import traceback

# Bound at module top level so Vercel's Python builder detects the ASGI entrypoint even
# when the import below fails; the real app replaces it when the backend imports cleanly.
app = None

try:
    from app.main import app
except Exception as exc:  # noqa: BLE001 - shown on every request until fixed
    logging.getLogger("arba").error("API failed to start:\n%s", traceback.format_exc())
    _reason = f"{type(exc).__name__}: {exc}".encode()

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            return
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": b"Arba API failed to start: " + _reason})


__all__ = ["app"]
