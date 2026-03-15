"""
Structured logging configuration and HTTP request logging middleware.
"""
import time
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


def generate_trace_id() -> str:
    """Generate a short, URL-safe trace ID (12 hex chars).

    Used everywhere a new trace needs to be minted — orchestrator, classifier,
    and the HTTP middleware when no ``X-Trace-ID`` header is provided.
    Client-supplied ``X-Trace-ID`` header values are always passed through
    unchanged regardless of their format.
    """
    return uuid.uuid4().hex[:12]


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog for JSON output with standard processors."""
    import logging
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs every HTTP request with method, path, status, and duration."""

    _log = structlog.get_logger(__name__)

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or generate_trace_id()
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        self._log.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            trace_id=trace_id,
        )
        response.headers["X-Trace-ID"] = trace_id
        return response
