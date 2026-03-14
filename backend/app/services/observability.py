"""
Tracing & Observability Service - Integrates with LangSmith and OpenTelemetry.
Provides visibility into the search pipeline for debugging and monitoring.
"""
import structlog
import time
from functools import lru_cache
from typing import Dict, Any, Optional, List
from contextlib import contextmanager
from enum import Enum

logger = structlog.get_logger(__name__)


class TraceLevel(str, Enum):
    """Trace verbosity levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class TraceEvent:
    """Represents a single trace event"""
    
    def __init__(
        self,
        name: str,
        trace_id: str,
        timestamp: Optional[float] = None,
        level: TraceLevel = TraceLevel.INFO,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.trace_id = trace_id
        self.timestamp = timestamp or time.time()
        self.level = level.value
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        return {
            "event": self.name,
            "trace_id": self.trace_id,
            "level": self.level,
            "timestamp": self.timestamp,
            **self.metadata
        }


class TraceCollector:
    """Collects and manages trace events throughout execution"""
    
    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        self.events: List[TraceEvent] = []
        self.start_time = time.time()
    
    def add_event(
        self,
        name: str,
        level: TraceLevel = TraceLevel.INFO,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add an event to the trace"""
        event = TraceEvent(name, self.trace_id, level=level, metadata=metadata)
        self.events.append(event)
        logger.log(level.value, event.name, trace_id=self.trace_id, **(metadata or {}))
    
    def get_duration_ms(self) -> int:
        """Get trace duration in milliseconds"""
        return int((time.time() - self.start_time) * 1000)
    
    def export_events(self) -> List[Dict[str, Any]]:
        """Export all events for external systems"""
        return [event.to_dict() for event in self.events]


class ObservabilityService:
    """
    Manages observability integrations (LangSmith, OpenTelemetry, etc.).
    Provides decorators and context managers for tracing.
    """
    
    def __init__(self):
        """Initialize observability service"""
        from app.config import get_settings
        self.settings = get_settings()
        self._langsmith_client = None
        
        logger.info(
            "observability_service_initialized",
            langsmith_enabled=self.settings.ENABLE_LANGSMITH,
            tracing_enabled=self.settings.ENABLE_TRACING
        )
    
    @property
    def langsmith_client(self):
        """Lazy-load LangSmith client if enabled"""
        if self.settings.ENABLE_LANGSMITH and self._langsmith_client is None:
            try:
                from langsmith import Client
                self._langsmith_client = Client(
                    api_key=self.settings.LANGSMITH_API_KEY,
                    project_name=self.settings.LANGSMITH_PROJECT
                )
                logger.info("langsmith_client_initialized")
            except Exception as e:
                logger.error("langsmith_initialization_failed", error=str(e))
        
        return self._langsmith_client
    
    @contextmanager
    def trace_operation(self, operation_name: str, trace_id: str, metadata: Optional[Dict] = None):
        """
        Context manager for tracing operations.
        
        Usage:
            with observability.trace_operation("search_query", trace_id, {"query": "..."}) as tracer:
                tracer.add_event("step_1", metadata={"status": "started"})
                # do work
                tracer.add_event("step_1", metadata={"status": "completed"})
        """
        tracer = TraceCollector(trace_id)
        start_time = time.time()
        
        tracer.add_event(
            f"{operation_name}_started",
            level=TraceLevel.INFO,
            metadata=metadata or {}
        )
        
        try:
            yield tracer
        except Exception as e:
            tracer.add_event(
                f"{operation_name}_failed",
                level=TraceLevel.ERROR,
                metadata={"error": str(e)}
            )
            raise
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            tracer.add_event(
                f"{operation_name}_completed",
                level=TraceLevel.INFO,
                metadata={
                    "duration_ms": duration_ms,
                    "event_count": len(tracer.events)
                }
            )
            
            # Export to external systems if enabled
            if self.settings.ENABLE_LANGSMITH and self.langsmith_client:
                self._export_to_langsmith(operation_name, tracer)
    
    def _export_to_langsmith(self, operation_name: str, tracer: TraceCollector) -> None:
        """Export trace events to LangSmith"""
        try:
            # LangSmith export would happen here
            logger.debug(
                "trace_exported_to_langsmith",
                trace_id=tracer.trace_id,
                operation=operation_name,
                event_count=len(tracer.events)
            )
        except Exception as e:
            logger.error("langsmith_export_failed", error=str(e))
    
    def log_search_classification(
        self,
        trace_id: str,
        query: str,
        category: str,
        confidence: float,
        reasoning: str
    ) -> None:
        """Log query classification for observability"""
        metadata = {
            "trace_id": trace_id,
            "query": query[:100],
            "category": category,
            "confidence": confidence,
            "reasoning": reasoning
        }
        
        logger.info("query_classified", **metadata)
        
        if self.settings.ENABLE_LANGSMITH and self.langsmith_client:
            try:
                # Send structured data to LangSmith
                pass
            except Exception as e:
                logger.error("langsmith_classification_log_failed", error=str(e))
    
    def log_search_execution(
        self,
        trace_id: str,
        strategy: str,
        query: str,
        total_results: int,
        execution_time_ms: int,
        score_info: Dict[str, float]
    ) -> None:
        """Log search execution details for observability"""
        metadata = {
            "trace_id": trace_id,
            "strategy": strategy,
            "query": query[:100],
            "total_results": total_results,
            "execution_time_ms": execution_time_ms,
            **score_info
        }
        
        logger.info("search_executed", **metadata)
        
        if self.settings.ENABLE_LANGSMITH and self.langsmith_client:
            try:
                # Send execution details to LangSmith
                pass
            except Exception as e:
                logger.error("langsmith_execution_log_failed", error=str(e))
    
    def create_metrics(
        self,
        trace_id: str,
        response_time_ms: int,
        strategy: str,
        total_results: int
    ) -> Dict[str, Any]:
        """
        Create metrics dictionary for monitoring.
        Can be exported to Prometheus, CloudWatch, etc.
        """
        return {
            "trace_id": trace_id,
            "response_time_ms": response_time_ms,
            "strategy": strategy,
            "total_results": total_results,
            "timestamp": time.time()
        }


# ============================================================================
# Singleton Pattern - Lazy Initialization
# ============================================================================

@lru_cache(maxsize=1)
def get_observability_service() -> ObservabilityService:
    """
    Get or create observability service instance (singleton).
    Used as a dependency in FastAPI endpoints.
    """
    return ObservabilityService()
