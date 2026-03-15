"""
OpenTelemetry tracing setup.

Registers a global TracerProvider that exports spans via OTLP/gRPC.
Call configure_tracing() once at startup (before serving requests).
"""
import structlog
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

logger = structlog.get_logger(__name__)


def configure_tracing(service_name: str, otlp_endpoint: str) -> None:
    """
    Set up OTLP/gRPC span exporter and install as the global TracerProvider.

    Args:
        service_name: Logical service name embedded in every span.
        otlp_endpoint: OTLP collector gRPC address, e.g. "http://otel-collector:4317".
    """
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        resource = Resource.create({SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info("tracing_configured", service=service_name, endpoint=otlp_endpoint)
    except Exception as exc:
        # Tracing is non-fatal — app continues without it.
        logger.warning("tracing_configuration_failed", error=str(exc))


def get_tracer(name: str) -> trace.Tracer:
    """Return a tracer scoped to *name* (typically ``__name__``)."""
    return trace.get_tracer(name)


def instrument_fastapi(app) -> None:
    """
    Attach OTel auto-instrumentation to a FastAPI app.
    Must be called after configure_tracing().
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("fastapi_instrumentation_applied")
    except Exception as exc:
        logger.warning("fastapi_instrumentation_failed", error=str(exc))
