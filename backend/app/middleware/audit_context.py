"""Attach a per-request correlation id to logs + responses.

A correlation id is honoured if provided by the client (`X-Request-Id`), else
generated. It propagates to every log line and into the OTel span attributes.
"""

from __future__ import annotations

from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-Id"


class AuditContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        token = structlog.contextvars.bind_contextvars(
            request_id=rid,
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else None,
        )
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars(*token)  # type: ignore[arg-type]
        response.headers[REQUEST_ID_HEADER] = rid
        return response
