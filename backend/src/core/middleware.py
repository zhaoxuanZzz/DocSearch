import logging
import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def request_id_middleware(request: Request, call_next: Callable) -> Response:
    """Inject a unique request ID into each request."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start_time = time.monotonic()

    response = await call_next(request)

    duration_ms = (time.monotonic() - start_time) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        },
    )
    return response


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Unified error response format."""
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail if isinstance(exc.detail, str) else exc.detail.get("error", "ERROR"),
                "message": exc.detail if isinstance(exc.detail, str) else exc.detail.get("message", str(exc.detail)),
                "request_id": getattr(request.state, "request_id", None),
            },
        )
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred.",
            "request_id": getattr(request.state, "request_id", None),
        },
    )
