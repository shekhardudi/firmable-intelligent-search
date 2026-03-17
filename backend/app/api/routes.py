"""
API route handlers for intelligent search endpoints.
Uses the new orchestrator-based architecture with intent classification,
strategy routing, and hybrid search.
"""
import functools
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Query, HTTPException, Header, Response
from typing import List, Optional, Dict, Any
import asyncio
import structlog
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.orchestrator import get_search_orchestrator
from app.models.search import BasicSearchRequest, BasicSearchResponse
from app.observability import log_search_execution
import time as _time
from app.observability.metrics import get_search_metrics
logger = structlog.get_logger(__name__)

_THREAD_POOL = ThreadPoolExecutor(max_workers=128)

router = APIRouter(prefix="/api/search", tags=["search"])


# ============================================================================
# Request Models
# ============================================================================

class UserFilters(BaseModel):
    """
    Filters explicitly selected by the user in the UI.
    These are always respected, regardless of search intent.
    """
    country: Optional[str] = Field(None, description="Filter by country (e.g. 'United States')")
    state: Optional[str] = Field(None, description="Filter by state/province (e.g. 'California')")
    city: Optional[str] = Field(None, description="Filter by city (e.g. 'San Francisco')")
    industries: Optional[List[str]] = Field(None, description="Filter by industries (multi-select, exact names)")
    year_from: Optional[int] = Field(None, ge=1800, le=2100, description="Founded from year")
    year_to: Optional[int] = Field(None, ge=1800, le=2100, description="Founded to year")
    size_range: Optional[str] = Field(None, description="Company size range (e.g. '51-200')")


class SearchRequest(BaseModel):
    """Standard search request model"""
    query: str = Field(..., description="Search query", min_length=1, max_length=500)
    limit: int = Field(20, ge=1, le=100, description="Results per page")
    page: int = Field(1, ge=1, description="Page number")
    include_reasoning: bool = Field(True, description="Include explanation for results")
    include_trace: bool = Field(False, description="Include detailed trace information")
    filters: Optional[UserFilters] = Field(
        None,
        description=(
            "Optional filters selected by the user. "
            "For regular search these are used as hard filters. "
            "For semantic/agentic they are merged with classifier-extracted filters "
            "(user selection takes precedence)."
        )
    )


class CompanyResult(BaseModel):
    """Company search result"""
    id: str
    name: str
    domain: str
    industry: str
    country: str
    locality: str
    relevance_score: float = Field(ge=0, le=1)
    search_method: str
    ranking_source: str
    matching_reason: Optional[str] = None
    year_founded: Optional[int] = None
    size_range: Optional[str] = None
    current_employee_estimate: Optional[int] = None
    event_data: Optional[Dict[str, Any]] = None
    linkedin_profile: Optional[Dict[str, Any]] = None


class SearchMetadata(BaseModel):
    """Search execution metadata"""
    trace_id: str
    query_classification: Dict[str, Any]
    search_execution: Dict[str, Any]
    total_results: int
    response_time_ms: int
    page: int
    limit: int


class SearchResponse(BaseModel):
    """Standard search response model"""
    query: str
    results: List[CompanyResult]
    metadata: SearchMetadata
    status: str = "success"


# ============================================================================
# Intelligent Search Endpoints 
# ============================================================================

@router.post(
    "/intelligent",
    response_model=SearchResponse,
    summary="Intelligent AI-powered search",
    description="Smart routing with intent classification and hybrid search"
)
async def intelligent_search(
    request: SearchRequest,
    trace_id: Optional[str] = Header(None, description="Optional trace ID for correlation"),
    response: Response = None,
):
    """
    Intelligent search with automatic query classification and strategy routing.
    
    The system will:
    1. **Classify Intent**: Determine if query is regular (exact), semantic (conceptual),
       or agentic (external data)
    2. **Select Strategy**: Route to appropriate search backend:
       - Regular: Fast BM25 lexical search
       - Semantic: Vector k-NN search with hybrid RRF scoring
       - Agentic: External tools (news, funding, etc.)
    3. **Execute Search**: Run the selected strategy
    4. **Return Results**: With confidence scores and reasoning
    
    Response Headers:
    - `X-Trace-ID`: Unique request ID for tracing
    - `X-Search-Logic`: Search method used (Regular-BM25, Semantic-Hybrid-RRF, or Agentic-External-Tool)
    - `X-Confidence`: Classification confidence (0.0-1.0)
    - `X-Response-Time-MS`: Total response time
    - `X-Total-Results`: Number of results returned
    
    Example requests:
    
    **Regular query** (Short, specific):
    ```json
    {
        "query": "Apple Inc",
        "limit": 10
    }
    ```
    
    **Semantic query** (Natural language, conceptual):
    ```json
    {
        "query": "Tech companies in France",
        "limit": 20
    }
    ```
    
    **Agentic query** (Time-sensitive, external data):
    ```json
    {
        "query": "companies that raised funding recently",
        "limit": 15
    }
    ```
    """
    try:
        _metrics = get_search_metrics()
        # Initialize orchestrator
        orchestrator = get_search_orchestrator()

        _metrics["active_search_requests"].add(1)
        _t0 = _time.perf_counter()
        try:
            _search_fn = functools.partial(
                orchestrator.search,
                request.query,
                request.limit,
                request.page,
                trace_id,
                request.include_reasoning,
                request.filters.model_dump(exclude_none=True) if request.filters else {},
            )
            orch_response = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(_THREAD_POOL, _search_fn),
                timeout=get_settings().SEARCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Search timed out.")
        finally:
            _metrics["active_search_requests"].add(-1)

        _query_type = orch_response.intent.get("category", "unknown") if orch_response.intent else "unknown"
        _duration_ms = int((_time.perf_counter() - _t0) * 1000)
        _attrs = {"query_type": _query_type}
        _metrics["search_requests_total"].add(1, _attrs)
        _metrics["search_latency_ms"].record(_duration_ms, _attrs)
        
        # Create response with metadata
        search_response = SearchResponse(
            query=request.query,
            results=[CompanyResult(**r) for r in orch_response.results],
            metadata={
                "trace_id": orch_response.trace_id,
                "query_classification": orch_response.intent,
                "search_execution": orch_response.metadata.get("search_execution", {}),
                "total_results": len(orch_response.results),
                "response_time_ms": orch_response.metadata.get("response_time_ms", 0),
                "page": request.page,
                "limit": request.limit
            },
            status="success"
        )
        
        # Add response headers for transparency
        for header_name, header_value in orch_response.response_headers.items():
            response.headers[header_name] = str(header_value)
        
        # Log observability data
        log_search_execution(
            trace_id=orch_response.trace_id,
            strategy=orch_response.intent.get("category"),
            query=request.query,
            total_results=len(orch_response.results),
            execution_time_ms=orch_response.metadata["response_time_ms"],
            score_info=orch_response.metadata["search_execution"].get("score_range", {}),
        )
        
        logger.info(
            "intelligent_search_completed",
            trace_id=orch_response.trace_id,
            query=request.query[:100],
            results=len(orch_response.results),
            response_time_ms=orch_response.metadata["response_time_ms"]
        )
        
        return search_response
        
    except Exception as e:
        logger.error("intelligent_search_failed", error=str(e), query=request.query[:100])
        raise HTTPException(
            status_code=500,
            detail="Search failed. See server logs for details."
        )


# ============================================================================
# Basic Structured Search Endpoint (delegates to SearchService via Orchestrator)
# ============================================================================


@router.post(
    "/basic",
    response_model=BasicSearchResponse,
    summary="Basic structured company search with facets",
    description="Fast BM25 search with filters and aggregated facets"
)
async def basic_search(request: BasicSearchRequest):
    """
    Structured company search supporting filters for industry, country,
    locality, year range, and company size. Returns results with faceted
    aggregations (industries, countries, sizes, year ranges).
    """
    try:
        orchestrator = get_search_orchestrator()
        return await asyncio.to_thread(orchestrator.basic_search, request)
    except Exception as e:
        logger.error("basic_search_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Basic search failed. See server logs for details.")


# ============================================================================
# Health & Diagnostics
# ============================================================================

@router.get("/health", tags=["diagnostics"])
async def health_check():
    """Check if the search service is healthy"""
    try:
        orchestrator = get_search_orchestrator()
        return {
            "status": "healthy",
            "service": "search-orchestrator",
            "version": "2.0.0"
        }
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.get("/top-queries", tags=["diagnostics"])
async def top_queries(limit: int = Query(10, ge=1, le=100, description="Number of top queries to return")):
    """Return the most frequently searched queries with hit counts."""
    from app.services.cache_service import get_cache_service
    cache = get_cache_service()
    return {
        "top_queries": cache.get_top_queries(limit),
        "storage": "redis" if cache.is_available else "in_memory",
        "note": "in_memory counts reset on server restart" if not cache.is_available else None,
    }


@router.get("/features", tags=["diagnostics"])
async def get_features():
    """Get available features and capabilities"""
    from app.config import get_settings
    settings = get_settings()
    
    return {
        "features": {
            "query_classification": settings.ENABLE_QUERY_CLASSIFICATION,
            "semantic_search": settings.ENABLE_SEMANTIC_SEARCH,
            "agentic_search": settings.ENABLE_AGENTIC_SEARCH,
            "result_caching": settings.ENABLE_CACHING,
            "tracing": settings.ENABLE_TRACING,
        },
        "models": {
            "classifier": settings.OPENAI_MINI_MODEL,
            "embedding": "msmarco-distilbert-base-tas-b",
            "embedding_dimension": 768
        },
        "search_strategies": [
            {
                "name": "Regular",
                "type": "regular",
                "description": "Fast BM25 lexical search",
                "best_for": "Specific names, acronyms, metadata",
                "latency_ms": "10-50"
            },
            {
                "name": "Semantic",
                "type": "semantic",
                "description": "Vector k-NN with hybrid RRF scoring",
                "best_for": "Conceptual queries, synonyms, exploration",
                "latency_ms": "50-200"
            },
            {
                "name": "Agentic",
                "type": "agentic",
                "description": "External tool-based search",
                "best_for": "Time-sensitive queries, external data",
                "latency_ms": "100-500+"
            }
        ]
    }
