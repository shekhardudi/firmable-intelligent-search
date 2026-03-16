"""
Search Orchestrator - Main coordinator for the intelligent search pipeline.
Routes queries through intent classification and strategically executes searches.
Manages observability, tracing, and hybrid result merging.
"""
import re
import structlog
import time
from functools import lru_cache
from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel
from enum import Enum

from app.config import get_settings, get_search_config
from app.services.intent_classifier import get_intent_classifier, SearchIntent, QueryIntent
from app.services.embedding_service import get_embedding_service
from app.services.opensearch_service import get_opensearch_service
from app.services.tool_service import ToolService
from app.services.search_strategies import (
    SearchContext, SearchResult, RegularSearchStrategy,
    SemanticSearchStrategy, AgenticSearchStrategy
)
from app.observability import generate_trace_id

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex pre-classifier — bypasses the LLM for obviously REGULAR queries.
# A query is REGULAR when it is clearly an exact name/domain lookup.
# ---------------------------------------------------------------------------

# Quoted exact phrase:  "Apple Inc"
_QUOTED_RE = re.compile(r'^"[^"]+"\s*$')

# Domain-style query:   google.com, stripe.io
_DOMAIN_RE = re.compile(
    r'^[\w.-]+\.(com|io|co|net|org|ai|app|tech|dev|biz|info)\b',
    re.IGNORECASE,
)

# Company legal suffix: Apple Inc, Stripe Ltd, Klarna AB
_COMPANY_SUFFIX_RE = re.compile(
    r'\b(inc\.?|incorporated|ltd\.?|limited|llc|corp\.?|corporation|'
    r'gmbh|plc|pty\s*ltd|s\.?a\.?|a\.?g\.?|b\.?v\.?|n\.?v\.?|'
    r's\.r\.l\.?|l\.?l\.?p\.?|holdings?)\b',
    re.IGNORECASE,
)

# Signals that disqualify regex-REGULAR → must go to LLM
_SEMANTIC_DISQUALIFY_RE = re.compile(
    r'\b(who|what|where|how|which|why|like|similar|comparable|'
    r'type\s+of|kind\s+of|innovative|leading|top|best|fastest?|'
    r'largest?|biggest?|growing|focused\s+on|specializ|dealing\s+in|'
    r'providing|offering|that\s+(do|make|sell|build|offer|provide|work))\b',
    re.IGNORECASE,
)

_AGENTIC_DISQUALIFY_RE = re.compile(
    r'\b(funded|funding|raised|series\s+[abcde]|ipo|acquired|acquisition|'
    r'merger|revenue|valuation|unicorn|investors?|news|recent|latest|announced)\b',
    re.IGNORECASE,
)

# Optional "in / from / based in / headquartered in <location>" suffix
_LOCATION_SUFFIX_RE = re.compile(
    r'\s+(?:in|from|based\s+in|headquartered\s+in)\s+(.+)$',
    re.IGNORECASE,
)


class IntelligentSearchResponse(BaseModel):
    """Response from the orchestrator"""
    query: str
    trace_id: str
    intent: Dict[str, Any]
    results: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    response_headers: Dict[str, str]


class SearchOrchestrator:
    """
    Orchestrates the complete intelligent search pipeline.
    
    Flow:
    1. Classify query intent (regular/semantic/agentic)
    2. Select appropriate search strategy
    3. Execute search with observability
    4. Merge and rank results
    5. Return with confidence/tracing headers
    """
    
    def __init__(self):
        """Initialize orchestrator with all dependencies"""
        self.settings = get_settings()
        self.classifier = get_intent_classifier()
        self.embeddings = get_embedding_service()
        self.opensearch = get_opensearch_service()
        
        # Initialize search strategies
        self.regular_strategy = RegularSearchStrategy(self.opensearch)
        self.semantic_strategy = SemanticSearchStrategy(self.opensearch, self.embeddings)
        _agentic_cfg = get_search_config().get("agentic", {})
        tool_service = ToolService(
            opensearch_service=self.opensearch,
            openai_api_key=self.settings.OPENAI_API_KEY,
            model=_agentic_cfg.get("model", "gpt-4o-mini"),
            tavily_key=get_settings().TAVILY_API_KEY,
            max_iterations=int(_agentic_cfg.get("agent_max_iterations", 8)),
        )
        self.agentic_strategy = AgenticSearchStrategy(self.opensearch, tool_service)
        
        logger.info("search_orchestrator_initialized")
    
    def search(
        self,
        query: str,
        limit: int = 20,
        page: int = 1,
        trace_id: Optional[str] = None,
        include_reasoning: bool = True,
        user_filters: Optional[Dict[str, Any]] = None
    ) -> IntelligentSearchResponse:
        """
        Execute intelligent search with automatic routing.
        
        Args:
            query: User's search query
            limit: Results per page
            page: Page number
            trace_id: Optional trace ID for observability
            include_reasoning: Include explanation for results
            user_filters: Filters explicitly selected by the user in the UI
                          (country, state, city, industry, year_from, year_to, size_range)
        
        Returns:
            IntelligentSearchResponse with results and metadata
        """
        trace_id = trace_id or generate_trace_id()
        start_time = time.time()
        
        logger.info(
            "intelligent_search_started",
            trace_id=trace_id,
            query=query[:100],
            limit=limit,
            page=page
        )
        
        try:
            # Step 1: Classify Intent
            # Fast regex pre-classifier runs first; LLM classifier is the fallback
            # for queries that are ambiguous or clearly semantic/agentic.
            intent = self._regex_classify(query)
            classified_by_regex = intent is not None
            if intent is None:
                intent = self.classifier.classify(query, trace_id)

            logger.info(
                "query_intent_determined",
                trace_id=trace_id,
                category=intent.category.value,
                confidence=intent.confidence,
                classified_by="regex" if classified_by_regex else "llm",
            )
            
            # Step 2: Build search context
            # Merge classifier filters with user-selected filters.
            # Strategy varies by intent:
            #  - REGULAR:  user filters are primary; classifier supplements missing keys
            #  - SEMANTIC: both sets applied as hard filters; user takes precedence
            #  - AGENTIC:  classifier + user filters passed in; applied as post-processing
            merged_filters = self._merge_filters(
                intent_filters=dict(intent.filters),
                user_filters=user_filters or {},
                intent_category=intent.category,
            )
            if intent.external_data_type:
                merged_filters["external_data_type"] = intent.external_data_type

            context = SearchContext(
                query=query,
                filters=merged_filters,
                optimized_query=intent.search_query,
                trace_id=trace_id,
                confidence=intent.confidence,
                limit=limit,
                page=page,
                include_reasoning=include_reasoning,
                field_boosts=intent.field_boosts or None,
            )
            
            # Step 3: Select and execute strategy
            results, search_metadata = self._execute_strategy(intent, context)
            
            # Step 4: Format response — normalize scores to [0, 1]
            max_score = max((r.relevance_score for r in results), default=1.0) or 1.0
            formatted_results = [self._format_result(r, include_reasoning, max_score) for r in results]
            
            # Step 5: Build response metadata
            response_time_ms = int((time.time() - start_time) * 1000)
            metadata = {
                "trace_id": trace_id,
                "query_classification": {
                    "category": intent.category.value,
                    "confidence": intent.confidence,
                    "reasoning": intent.reasoning,
                    "needs_external_data": intent.needs_external_data,
                    "classified_by": "regex" if classified_by_regex else "llm",
                },
                "search_execution": search_metadata,
                "total_results": len(formatted_results),
                "response_time_ms": response_time_ms,
                "page": page,
                "limit": limit
            }
            
            # Step 6: Build response headers for transparency
            response_headers = {
                "X-Trace-ID": trace_id,
                "X-Search-Logic": self._get_search_logic_header(intent),
                "X-Confidence": f"{intent.confidence:.2f}",
                "X-Response-Time-MS": str(response_time_ms),
                "X-Total-Results": str(len(formatted_results))
            }
            
            logger.info(
                "intelligent_search_completed",
                trace_id=trace_id,
                category=intent.category.value,
                results_returned=len(formatted_results),
                response_time_ms=response_time_ms
            )
            
            return IntelligentSearchResponse(
                query=query,
                trace_id=trace_id,
                intent=intent.model_dump(),
                results=formatted_results,
                metadata=metadata,
                response_headers=response_headers
            )
        
        except Exception as e:
            logger.error(
                "intelligent_search_failed",
                trace_id=trace_id,
                query=query[:100],
                error=str(e)
            )
            raise
    
    def _regex_classify(self, query: str) -> Optional[QueryIntent]:
        """
        Fast regex pre-classifier. Returns a REGULAR QueryIntent immediately
        for obvious exact/name-lookup queries, skipping the LLM entirely.
        Returns None when uncertain — the LLM classifier takes over.

        Matches on:
          - Quoted exact phrases: "Stripe Inc"
          - Domain-style queries: stripe.com
          - Company name with legal suffix: Stripe Ltd, Klarna AB

        Disqualifies (returns None) if semantic or agentic signal words are
        detected anywhere in the query.
        """
        q = query.strip()
        if not q:
            return None

        # Any conceptual or external-data signal → must use LLM
        if _SEMANTIC_DISQUALIFY_RE.search(q) or _AGENTIC_DISQUALIFY_RE.search(q):
            return None

        is_regular = (
            bool(_QUOTED_RE.match(q))
            or bool(_DOMAIN_RE.match(q))
            or bool(_COMPANY_SUFFIX_RE.search(q))
        )
        if not is_regular:
            return None

        # Extract optional "in <location>" suffix as a generic location filter.
        # Using the broad "location" key so search_strategies can match it
        # against country, state, or city without forcing a specific type here.
        filters: Dict[str, Any] = {}
        search_query = q
        loc_match = _LOCATION_SUFFIX_RE.search(q)
        if loc_match:
            filters["location"] = loc_match.group(1).strip()
            search_query = q[: loc_match.start()].strip()

        # Strip surrounding quotes so the raw term reaches OpenSearch
        if _QUOTED_RE.match(search_query):
            search_query = search_query.strip('"').strip()

        logger.info(
            "query_classified_by_regex",
            query=q[:100],
            search_query=search_query,
            filters=filters,
        )
        return QueryIntent(
            category=SearchIntent.REGULAR,
            confidence=0.95,
            filters=filters,
            search_query=search_query,
            needs_external_data=False,
            field_boosts={},
            reasoning="Regex pre-classifier: query matches exact/name-lookup pattern — LLM skipped",
        )

    def _merge_filters(
        self,
        intent_filters: Dict[str, Any],
        user_filters: Dict[str, Any],
        intent_category: SearchIntent,
    ) -> Dict[str, Any]:
        """
        Merge classifier-extracted filters with user-selected filters.

        User filters are normalised to the same key naming used by the
        classifier (location_country / location_state / location_city).

        For REGULAR queries:
            User filters take precedence, classifier fills in any remaining gaps.
        For SEMANTIC / AGENTIC queries:
            Same merge logic — user filters override classifier where they overlap,
            classifier contributes keys the user did not explicitly set.
        """
        # Normalise user filter keys to match classifier output format
        normalised_user: Dict[str, Any] = {}
        if user_filters.get("country"):
            normalised_user["location_country"] = user_filters["country"]
        if user_filters.get("state"):
            normalised_user["location_state"] = user_filters["state"]
        if user_filters.get("city"):
            normalised_user["location_city"] = user_filters["city"]
        if user_filters.get("industries"):
            normalised_user["industries"] = user_filters["industries"]
        elif user_filters.get("industry"):  # backward-compat: classifier outputs single string
            normalised_user["industry"] = user_filters["industry"]
        if user_filters.get("year_from"):
            normalised_user["year_from"] = user_filters["year_from"]
        if user_filters.get("year_to"):
            normalised_user["year_to"] = user_filters["year_to"]
        if user_filters.get("size_range"):
            normalised_user["size_range"] = user_filters["size_range"]

        # Classifier fills in gaps; user selection always wins on overlap
        merged = {**intent_filters, **normalised_user}

        logger.info(
            "filters_merged",
            intent=intent_category.value,
            classifier_keys=list(intent_filters.keys()),
            user_keys=list(normalised_user.keys()),
            merged_keys=list(merged.keys()),
        )
        return merged

    def _execute_strategy(
        self,
        intent: QueryIntent,
        context: SearchContext
    ) -> Tuple[List[SearchResult], Dict[str, Any]]:
        """Select and execute appropriate search strategy"""
        
        strategy_map = {
            SearchIntent.REGULAR: self.regular_strategy,
            SearchIntent.SEMANTIC: self.semantic_strategy,
            SearchIntent.AGENTIC: self.agentic_strategy,
        }
        
        strategy = strategy_map.get(intent.category, self.semantic_strategy)
        
        logger.info(
            "strategy_selected",
            trace_id=context.trace_id,
            strategy=strategy.get_strategy_type()
        )
        
        try:
            results, metadata = strategy.search(context)
            return results, metadata
        except Exception as e:
            # Fallback: try semantic search
            logger.warning(
                "strategy_failed_trying_fallback",
                trace_id=context.trace_id,
                failed_strategy=strategy.get_strategy_type(),
                error=str(e)
            )
            results, metadata = self.semantic_strategy.search(context)
            metadata["fallback"] = True
            return results, metadata
    
    def _format_result(self, result: SearchResult, include_reasoning: bool, max_score: float = 1.0) -> Dict[str, Any]:
        """Format SearchResult for API response"""
        normalized_score = round(result.relevance_score / max_score, 4) if max_score > 0 else 0.0
        formatted = {
            "id": result.company_id,
            "name": result.company_name,
            "domain": result.domain,
            "industry": result.industry,
            "country": result.country,
            "locality": result.locality,
            "relevance_score": normalized_score,
            "search_method": result.search_method,
            "ranking_source": result.ranking_source,
            "year_founded": result.year_founded,
            "size_range": result.size_range,
            "current_employee_estimate": result.current_employee_estimate,
        }
        
        if include_reasoning and result.matching_reason:
            formatted["matching_reason"] = result.matching_reason

        if result.event_data:
            formatted["event_data"] = result.event_data.model_dump()

        return formatted
    
    def _get_search_logic_header(self, intent: QueryIntent) -> str:
        """Generate X-Search-Logic header value"""
        logic_map = {
            SearchIntent.REGULAR: "Regular-BM25",
            SearchIntent.SEMANTIC: "Semantic-Hybrid-RRF",
            SearchIntent.AGENTIC: "Agentic-External-Tool"
        }
        return logic_map.get(intent.category, "Unknown")
    
    def basic_search(self, request):
        """
        Delegate basic structured search (with facets) to SearchService.
        Makes the orchestrator the single entry point for all search operations.
        """
        from app.services.search_service import get_search_service
        return get_search_service().basic_search(request)


# ============================================================================
# Singleton Pattern - Lazy Initialization
# ============================================================================


@lru_cache(maxsize=1)
def get_search_orchestrator() -> SearchOrchestrator:
    """
    Get or create search orchestrator instance (singleton).
    Used as a dependency in FastAPI endpoints.
    """
    return SearchOrchestrator()
