"""Request tracing and conservative browser security headers."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{time.perf_counter() - started:.4f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


class UploadSizeLimitMiddleware:
    """Bound upload bodies before multipart parsing, including chunked requests.

    The route separately enforces the PDF byte limit; the body limit allows 64 KiB
    for multipart fields. A reverse proxy should enforce the same ingress limit.
    """

    def __init__(self, app: Any, *, maximum_bytes: int) -> None:
        self.app = app
        self.maximum_bytes = maximum_bytes

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("path") != "/api/v1/documents/upload":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = self.maximum_bytes + 1
        if length > self.maximum_bytes:
            response = JSONResponse(status_code=413, content={"detail": "Upload body exceeds the configured limit"})
            await response(scope, receive, send)
            return
        received = 0
        oversized = False
        rejected = False

        async def limited_receive() -> Any:
            nonlocal received, oversized
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.maximum_bytes:
                    oversized = True
                    raise HTTPException(status_code=413, detail="Upload body exceeds the configured limit")
            return message

        async def limited_send(message: Any) -> None:
            nonlocal rejected
            if not oversized:
                await send(message)
            elif message["type"] == "http.response.start" and not rejected:
                # Multipart parsing can translate receive errors into 400. Keep
                # the ingress limit's 413 status only when that limit was hit.
                rejected = True
                await JSONResponse(status_code=413, content={
                    "detail": "Upload body exceeds the configured limit",
                })(scope, receive, send)

        await self.app(scope, limited_receive, limited_send)
