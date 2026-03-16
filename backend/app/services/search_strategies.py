"""
Search Strategy Pattern - Abstract base and implementations.
Allows different search backends to be plugged in based on query intent.
"""
import structlog
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from app.config import get_settings, get_search_config

logger = structlog.get_logger(__name__)


class EventData(BaseModel):
    """Structured event data attached to agentic search results."""
    event_type: str = "other"
    amount: Optional[str] = None
    round: Optional[str] = None
    date: Optional[str] = None
    summary: Optional[str] = None
    source_url: Optional[str] = None

    model_config = {"extra": "ignore"}


class SearchResult(BaseModel):
    """Unified search result across all strategies"""
    company_id: str
    company_name: str
    domain: str
    industry: str
    country: str
    locality: str
    relevance_score: float
    search_method: str  # 'regular', 'semantic', 'agentic'
    matching_reason: Optional[str] = None
    ranking_source: Optional[str] = None  # 'bm25', 'knn', 'hybrid', 'tool'
    year_founded: Optional[int] = None
    size_range: Optional[str] = None
    current_employee_estimate: Optional[int] = None
    event_data: Optional[EventData] = None


class SearchContext(BaseModel):
    """Context passed through the search pipeline"""
    query: str
    filters: Dict[str, Any]
    optimized_query: str
    trace_id: str
    confidence: float
    limit: int = 20
    page: int = 1
    include_reasoning: bool = True
    field_boosts: Optional[Dict[str, float]] = None  # LLM-extracted per-field boost multipliers (semantic only)


class SearchStrategy(ABC):
    """
    Abstract base class for search strategies.
    Implements Strategy Pattern for pluggable search implementations.
    """
    
    @abstractmethod
    def search(self, context: SearchContext) -> tuple[List[SearchResult], Dict[str, Any]]:
        """
        Execute search with this strategy.
        
        Args:
            context: SearchContext with query, filters, trace_id, etc.
        
        Returns:
            Tuple of (results, metadata)
            - results: List of SearchResult objects
            - metadata: Dict with execution details (time, score range, etc.)
        """
        pass
    
    @abstractmethod
    def get_strategy_type(self) -> str:
        """Return strategy type identifier"""
        pass

    def _get_score_range(self, results: List[SearchResult]) -> Dict[str, float]:
        """Calculate score range for metadata"""
        if not results:
            return {"min": 0, "max": 0}
        scores = [r.relevance_score for r in results]
        return {"min": min(scores), "max": max(scores)}

    @staticmethod
    def _boosts_to_fields(boosts: Dict[str, float]) -> List[str]:
        """Convert a boost dict to OpenSearch fields list format.
        Fields with boost 1.0 are emitted without a suffix (cleaner query).
        """
        return [f if b == 1.0 else f"{f}^{b:g}" for f, b in boosts.items()]

    @staticmethod
    def _build_filters(filters: Dict[str, Any]) -> List[Dict]:
        """
        Shared helper: convert the unified filters dict into OpenSearch filter clauses.
        Handles both new keys (location_country / location_state / location_city)
        and legacy key (location) for backward compatibility.
        """
        clauses: List[Dict] = []
        if not filters:
            return clauses

        # Location filters
        if country := filters.get("location_country"):
            clauses.append({
                "bool": {
                    "should": [
                        {"term": {"country": country.lower()}},
                        {"term": {"country_tags": country.lower()}},
                    ],
                    "minimum_should_match": 1,
                }
            })
        if state := filters.get("location_state"):
            clauses.append({"term": {"state": state.lower()}})
        if city := filters.get("location_city"):
            clauses.append({"term": {"city": city.lower()}})
        # Legacy 'location' key – match against country/state/city as a best-effort
        if loc := filters.get("location"):
            clauses.append({
                "multi_match": {
                    "query": loc,
                    "fields": ["country", "state", "city", "locality"],
                }
            })

        # Industry filter — handles both a list (from UI multi-select) and a single string
        # (from the LLM classifier).  For a list, build one should-clause per industry
        # and wrap them in an outer should so any match is sufficient.
        industries: List[str] = filters.get("industries") or []
        if not industries and filters.get("industry"):
            industries = [filters["industry"]]  # normalise single string to list
        if industries:
            per_industry = [
                {
                    "bool": {
                        "should": [
                            {"match": {"industry": {"query": ind, "fuzziness": "AUTO"}}},
                            {"term": {"industry_tags": ind.lower()}},
                            {"match": {"searchable_text": ind}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
                for ind in industries
            ]
            if len(per_industry) == 1:
                clauses.append(per_industry[0])
            else:
                clauses.append({"bool": {"should": per_industry, "minimum_should_match": 1}})

        # Year filters
        year_range: Dict[str, Any] = {}
        if year_from := filters.get("year_from"):
            year_range["gte"] = year_from
        if year_to := filters.get("year_to"):
            year_range["lte"] = year_to
        if year := filters.get("year"):
            year_range["gte"] = year
            year_range["lte"] = year
        if year_range:
            clauses.append({"range": {"year_founded": year_range}})

        # Size filter
        if size := filters.get("size_range"):
            clauses.append({"term": {"size_range": size}})

        return clauses


class RegularSearchStrategy(SearchStrategy):
    """
    Bucket 1: Fast Path - Lexical (BM25) search for exact matches.
    Best for: Specific names, acronyms, structured queries.
    """
    
    def __init__(self, opensearch_service):
        """Initialize with OpenSearch service dependency"""
        self.opensearch = opensearch_service
        self.strategy_type = "regular"
    
    def search(self, context: SearchContext) -> tuple[List[SearchResult], Dict[str, Any]]:
        """
        Execute BM25 lexical search on OpenSearch.
        """
        start_time = time.time()
        
        logger.info(
            "regular_search_started",
            trace_id=context.trace_id,
            query=context.query[:100]
        )
        
        # Build BM25 query
        query_body = self._build_bm25_query(context)
        
        try:
            # Execute search
            response = self.opensearch.search(
                index=get_settings().OPENSEARCH_INDEX_NAME,
                query=query_body["query"],
                size=context.limit,
                from_=(context.page - 1) * context.limit
            )
            
            # Process results
            results = self._process_results(response, context)
            
            execution_time = time.time() - start_time
            metadata = {
                "strategy": self.strategy_type,
                "total_hits": response.get("hits", {}).get("total", {}).get("value", 0),
                "returned": len(results),
                "execution_time_ms": int(execution_time * 1000),
                "score_range": self._get_score_range(results)
            }
            
            logger.info(
                "regular_search_completed",
                trace_id=context.trace_id,
                **metadata
            )
            
            return results, metadata
            
        except Exception as e:
            logger.error(
                "regular_search_failed",
                trace_id=context.trace_id,
                error=str(e)
            )
            raise
    
    def _build_bm25_query(self, context: SearchContext) -> Dict[str, Any]:
        """Build OpenSearch BM25 query with field boosts from config."""
        cfg = get_search_config().get("field_boosts", {}).get("bm25_regular", {})
        boosts = {
            "name": float(cfg.get("name", 2.0)),
            "domain": float(cfg.get("domain", 2.0)),
            "searchable_text": float(cfg.get("searchable_text", 1.0)),
            "industry": float(cfg.get("industry", 1.0)),
            "locality": float(cfg.get("locality", 1.0)),
        }
        must_clauses = []
        if context.optimized_query:
            must_clauses.append({
                "multi_match": {
                    "query": context.optimized_query,
                    "fields": self._boosts_to_fields(boosts),
                    "type": "best_fields",
                    "operator": "or",
                    "fuzziness": "AUTO",
                }
            })

        filter_clauses = self._build_filters(context.filters)
        return {
            "query": {
                "bool": {
                    "must": must_clauses if must_clauses else [{"match_all": {}}],
                    "filter": filter_clauses,
                }
            }
        }
    
    def _process_results(self, response: Dict, context: SearchContext) -> List[SearchResult]:
        """Convert OpenSearch response to SearchResult objects"""
        results = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            results.append(SearchResult(
                company_id=source.get("company_id", hit.get("_id")),
                company_name=source.get("name"),
                domain=source.get("domain"),
                industry=source.get("industry"),
                country=source.get("country"),
                locality=source.get("locality"),
                relevance_score=float(hit.get("_score", 0)),
                search_method=self.strategy_type,
                ranking_source="bm25",
                matching_reason="Matched on name, domain, industry fields",
                year_founded=source.get("year_founded"),
                size_range=source.get("size_range"),
                current_employee_estimate=source.get("current_employee_estimate"),
            ))
        return results
    
    def get_strategy_type(self) -> str:
        """Return strategy identifier"""
        return self.strategy_type


class SemanticSearchStrategy(SearchStrategy):
    """
    Bucket 2: Conceptual Path - Vector (k-NN) search with hybrid scoring.
    Best for: Natural language, synonyms, conceptual queries.
    """

    @property
    def _DEFAULT_FIELD_BOOSTS(self) -> Dict[str, float]:
        """Fallback field boosts loaded from search_config.yaml."""
        return dict(get_search_config().get("field_boosts", {}).get("defaults", {
            "name": 2.0, "domain": 1.0, "searchable_text": 2.0,
            "industry": 1.0, "locality": 1.0,
        }))

    @property
    def _RRF_K(self) -> int:  # type: ignore[override]
        return get_search_config().get("rrf", {}).get("k", 60)

    def __init__(self, opensearch_service, embedding_service):
        """Initialize with OpenSearch and embedding service"""
        self.opensearch = opensearch_service
        self.embeddings = embedding_service
        self.strategy_type = "semantic"

    def search(self, context: SearchContext) -> tuple[List[SearchResult], Dict[str, Any]]:
        """
        Execute hybrid semantic search using true Reciprocal Rank Fusion (RRF).

        Two independent OpenSearch queries are issued:
          1. BM25 (lexical) — multi_match with LLM-extracted field boosts
          2. k-NN (vector)  — cosine similarity using a BGE query embedding

        Results are merged with RRF:
          rrf_score(doc) = 1/(k + bm25_rank) + 1/(k + knn_rank)

        This avoids the scale-mismatch issue of combining raw BM25/L2 scores
        in a bool.should clause, and produces significantly better rankings.
        """
        start_time = time.time()

        logger.info(
            "semantic_search_started",
            trace_id=context.trace_id,
            query=context.query[:100]
        )

        try:
            # Generate BGE query embedding (with asymmetric retrieval prefix)
            embedding = self.embeddings.embed(context.optimized_query)

            # Over-fetch for both legs so RRF has enough candidates
            rrf_cfg = get_search_config().get("rrf", {})
            fetch_size = max(context.limit * rrf_cfg.get("fetch_multiplier", 4), 100)

            # --- BM25 leg ---
            bm25_response = self.opensearch.search(
                index=get_settings().OPENSEARCH_INDEX_NAME,
                body=self._build_bm25_query(context),
                size=fetch_size,
                from_=0,
            )

            # --- k-NN leg ---
            knn_response = self.opensearch.search(
                index=get_settings().OPENSEARCH_INDEX_NAME,
                body=self._build_knn_query(context, embedding),
                size=fetch_size,
                from_=0,
            )

            # --- RRF merge ---
            bm25_hits = bm25_response.get("hits", {}).get("hits", [])
            knn_hits = knn_response.get("hits", {}).get("hits", [])
            merged_hits = self._rrf_merge(bm25_hits, knn_hits)

            # Paginate after merge
            page_start = (context.page - 1) * context.limit
            page_hits = merged_hits[page_start: page_start + context.limit]

            results = self._process_rrf_results(page_hits, context)

            execution_time = time.time() - start_time
            effective_boosts = self._resolve_field_boosts(context)
            metadata = {
                "strategy": self.strategy_type,
                "total_hits": len(merged_hits),
                "returned": len(results),
                "execution_time_ms": int(execution_time * 1000),
                "embedding_dim": len(embedding) if embedding else 0,
                "score_range": self._get_score_range(results),
                "field_boosts_applied": effective_boosts,
                "bm25_candidates": len(bm25_hits),
                "knn_candidates": len(knn_hits),
            }

            logger.info(
                "semantic_search_completed",
                trace_id=context.trace_id,
                **metadata
            )

            return results, metadata

        except Exception as e:
            logger.error(
                "semantic_search_failed",
                trace_id=context.trace_id,
                error=str(e)
            )
            raise
    
    def _resolve_field_boosts(self, context: SearchContext) -> Dict[str, float]:
        """Merge LLM-extracted boosts with defaults.

        The classifier's values take precedence; any field not specified by the
        classifier falls back to _DEFAULT_FIELD_BOOSTS.  This guarantees all
        five fields are always present and the query never omits a field.
        """
        classifier_boosts = context.field_boosts or {}
        if not classifier_boosts:
            return dict(self._DEFAULT_FIELD_BOOSTS)
        # Start from defaults, override with whatever the classifier provided
        merged = dict(self._DEFAULT_FIELD_BOOSTS)
        for field, boost in classifier_boosts.items():
            if field in merged and isinstance(boost, (int, float)) and boost > 0:
                merged[field] = float(boost)
        return merged

    def _build_bm25_query(self, context: SearchContext) -> Dict[str, Any]:
        """BM25 leg — multi_match with LLM-extracted field boosts + filters."""
        filter_clauses = self._build_filters(context.filters)
        effective_boosts = self._resolve_field_boosts(context)
        boosted_fields = self._boosts_to_fields(effective_boosts)

        bool_query: Dict[str, Any] = {
            "must": [
                {
                    "multi_match": {
                        "query": context.optimized_query,
                        "fields": boosted_fields,
                        "type": "best_fields",
                        "operator": "or",
                    }
                }
            ]
        }
        if filter_clauses:
            bool_query["filter"] = filter_clauses

        return {"query": {"bool": bool_query}}

    def _build_knn_query(self, context: SearchContext, embedding: List[float]) -> Dict[str, Any]:
        """k-NN leg — cosine similarity on the BGE vector field + filters.

        OpenSearch requires `knn` to be the TOP-LEVEL query type — it cannot
        be nested inside a bool.must clause. Filters are placed INSIDE the knn
        clause (supported since OpenSearch 2.x) so that filtering is applied
        at the ANN candidate selection stage for efficiency.
        """
        filter_clauses = self._build_filters(context.filters)

        knn_params: Dict[str, Any] = {
            "vector": embedding,
            "k": get_search_config().get("rrf", {}).get("knn_k", 100),
        }
        if filter_clauses:
            knn_params["filter"] = {"bool": {"must": filter_clauses}}

        return {"query": {"knn": {"vector_embedding": knn_params}}}

    def _rrf_merge(
        self,
        bm25_hits: List[Dict],
        knn_hits: List[Dict],
        k: Optional[int] = None,
    ) -> List[Dict]:
        """
        Merge two ranked hit lists using Reciprocal Rank Fusion.

        rrf_score(doc) = sum over lists of 1 / (k + rank_in_list)

        Documents that appear in both lists get contributions from both.
        Documents that appear in only one list get a contribution from that list.
        """
        if k is None:
            k = self._RRF_K
        scores: Dict[str, float] = {}
        # Store the best _source for each doc (prefer knn as it has full source)
        sources: Dict[str, Dict] = {}

        for rank, hit in enumerate(bm25_hits, start=1):
            doc_id = hit["_id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            sources.setdefault(doc_id, hit)

        for rank, hit in enumerate(knn_hits, start=1):
            doc_id = hit["_id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            sources.setdefault(doc_id, hit)

        # Sort descending by RRF score and annotate each hit
        sorted_ids = sorted(scores, key=lambda d: scores[d], reverse=True)
        merged = []
        for doc_id in sorted_ids:
            hit = dict(sources[doc_id])
            hit["_rrf_score"] = scores[doc_id]
            merged.append(hit)
        return merged

    def _process_rrf_results(self, hits: List[Dict], context: SearchContext) -> List[SearchResult]:
        """Convert RRF-merged hits to SearchResult objects, using _rrf_score as relevance."""
        results = []
        for hit in hits:
            source = hit.get("_source", {})
            results.append(SearchResult(
                company_id=source.get("company_id", hit.get("_id")),
                company_name=source.get("name"),
                domain=source.get("domain"),
                industry=source.get("industry"),
                country=source.get("country"),
                locality=source.get("locality"),
                relevance_score=float(hit.get("_rrf_score", hit.get("_score", 0))),
                search_method=self.strategy_type,
                ranking_source="rrf_hybrid",
                matching_reason="Hybrid semantic + lexical match ranked by Reciprocal Rank Fusion",
                year_founded=source.get("year_founded"),
                size_range=source.get("size_range"),
                current_employee_estimate=source.get("current_employee_estimate"),
            ))
        return results
    
    def get_strategy_type(self) -> str:
        """Return strategy identifier"""
        return self.strategy_type


class AgenticSearchStrategy(SearchStrategy):
    """
    Bucket 3: External Path - Tool-based search for time-sensitive/external data.
    Best for: Recent news, funding, events, etc.
    Uses ReAct agent pattern with external tools.
    """
    
    def __init__(self, opensearch_service, tool_service):
        """Initialize with OpenSearch and tool service"""
        self.opensearch = opensearch_service
        self.tools = tool_service
        self.strategy_type = "agentic"
    
    def search(self, context: SearchContext) -> tuple[List[SearchResult], Dict[str, Any]]:
        """
        Execute agentic search using external tools/APIs.
        1. Call external tool (news, funding, etc.) via ToolService
        2. ToolService returns full OpenSearch source dicts already resolved
        3. Convert directly to SearchResult objects
        4. Apply any remaining user filters as post-processing
        """
        from app.config import get_settings
        if not get_settings().ENABLE_AGENTIC_SEARCH:
            raise NotImplementedError("Agentic search is disabled via ENABLE_AGENTIC_SEARCH setting")

        start_time = time.time()

        logger.info(
            "agentic_search_started",
            trace_id=context.trace_id,
            query=context.query[:100],
            data_type=context.filters.get("external_data_type")
        )
        
        try:
            # Call external tool — returns list of source dicts
            external_docs = self._call_external_tool(context)
            
            # Convert to SearchResult objects directly (no second OpenSearch lookup)
            results = self._docs_to_results(external_docs, context)
            
            # Apply user filters as post-processing (narrow down results)
            results = self._apply_post_filters(results, context)

            execution_time = time.time() - start_time
            metadata = {
                "strategy": self.strategy_type,
                "external_tool_used": context.filters.get("external_data_type"),
                "external_results": len(external_docs),
                "matching_companies": len(results),
                "execution_time_ms": int(execution_time * 1000),
                "score_range": self._get_score_range(results)
            }
            
            logger.info(
                "agentic_search_completed",
                trace_id=context.trace_id,
                **metadata
            )
            
            return results, metadata
            
        except Exception as e:
            logger.error(
                "agentic_search_failed",
                trace_id=context.trace_id,
                error=str(e)
            )
            raise
    
    def _call_external_tool(self, context: SearchContext) -> List[Dict]:
        """Call external tool (news API, funding database, etc.)"""
        data_type = context.filters.get("external_data_type", "news")

        if self.tools is None:
            raise NotImplementedError(
                f"No tool service configured for agentic search (data_type='{data_type}'). "
                "Provide a real tool_service when initializing AgenticSearchStrategy."
            )

        logger.info(
            "external_tool_called",
            trace_id=context.trace_id,
            tool_type=data_type,
            query=context.query[:100]
        )

        return self.tools.call(data_type, context.query)

    def _docs_to_results(self, docs: List[Dict], context: SearchContext) -> List[SearchResult]:
        """Convert ToolService source dicts directly to SearchResult objects."""
        results = []
        data_type = context.filters.get("external_data_type", "external")
        for doc in docs:
            event = doc.get("_event_data")
            if event and event.get("summary"):
                date_suffix = f" ({event['date']})" if event.get("date") else ""
                matching_reason = f"{event['summary']}{date_suffix}"
            else:
                matching_reason = f"Identified via {data_type} data for query: {context.query[:60]}"
            results.append(SearchResult(
                company_id=doc.get("company_id", doc.get("_id", "")),
                company_name=doc.get("name", ""),
                domain=doc.get("domain", ""),
                industry=doc.get("industry", ""),
                country=doc.get("country", ""),
                locality=doc.get("locality", ""),
                relevance_score=float(doc.get("_score", 1.0)),
                search_method=self.strategy_type,
                ranking_source="tool",
                matching_reason=matching_reason,
                event_data=event,
            ))
        return results

    def _apply_post_filters(self, results: List[SearchResult], context: SearchContext) -> List[SearchResult]:
        """
        Apply user-selected filters as post-processing on agentic results.
        This is a soft filter — we narrow down what the external tool returned.
        """
        filters = context.filters
        if not filters:
            return results

        filtered = []
        for r in results:
            # Country filter
            if country := filters.get("location_country"):
                if country.lower() not in (r.country or "").lower():
                    continue
            # Industry filter (loose match against the industry string)
            if industry := filters.get("industry"):
                if industry.lower() not in (r.industry or "").lower():
                    continue
            filtered.append(r)

        if not filtered:
            logger.warning(
                "post_filter_dropped_all",
                result_count=len(results),
                filters=filters,
            )
            return []
        return filtered

    def get_strategy_type(self) -> str:
        """Return strategy identifier"""
        return self.strategy_type
