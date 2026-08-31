import re
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.app.observability.context import bind_context, clear_context
from backend.app.observability.logging import get_logger

logger = get_logger("rebutio.http")

SESSION_PATH_REGEX = re.compile(r"/api/sessions/([^/]+)")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware for correlation ID propagation and request lifecycle observability.
    Adds X-Request-ID header to responses and emits structured request logs.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        clear_context()
        start_time = time.perf_counter()

        # Inbound correlation ID or new request ID
        inbound_req_id = request.headers.get("x-request-id") or request.headers.get("x-correlation-id")
        if inbound_req_id and len(inbound_req_id) <= 64 and re.match(r"^[A-Za-z0-9_\-]+$", inbound_req_id):
            request_id = inbound_req_id
        else:
            request_id = f"req_{uuid.uuid4().hex[:12]}"

        # Extract session_id from URL path if present
        session_id = None
        match = SESSION_PATH_REGEX.search(request.url.path)
        if match:
            session_id = match.group(1)

        # Bind context variables
        bind_context(request_id=request_id, session_id=session_id)

        # Health check paths can be logged at debug level to avoid spam
        is_health = request.url.path in {"/health", "/ready"}
        if is_health:
            logger.debug(
                "http.request.started",
                method=request.method,
                path=request.url.path,
                request_id=request_id,
            )
        else:
            logger.info(
                "http.request.started",
                method=request.method,
                path=request.url.path,
                request_id=request_id,
                session_id=session_id,
            )

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            response.headers["X-Request-ID"] = request_id

            if is_health:
                logger.debug(
                    "http.request.completed",
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
            else:
                logger.info(
                    "http.request.completed",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
            return response

        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "http.request.failed",
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=duration_ms,
                exception_type=exc.__class__.__name__,
            )
            raise
        finally:
            clear_context()
