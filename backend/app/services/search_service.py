"""
Core search service orchestrating all search operations.
Coordinates OpenSearch, LLM, caching, and result processing.
"""
import structlog
import time
from functools import lru_cache
from typing import Dict, List, Any, Optional, Tuple
from app.services.opensearch_service import get_opensearch_service
from app.services.llm_service import get_llm_service
from app.services.embedding_service import get_embedding_service
from app.models.search import (
    BasicSearchRequest, BasicSearchResponse, CompanySearchResult,
    IntelligentSearchRequest, IntelligentSearchResponse,
    SemanticSearchRequest, CompanySearchResult as CompanySearchResult,
    QueryUnderstanding, SearchFacets, FacetValue, Company
)
from app.config import get_settings
import json

logger = structlog.get_logger(__name__)


class SearchService:
    """Main search service"""
    
    def __init__(self):
        """Initialize search service"""
        self.settings = get_settings()
        self.opensearch = get_opensearch_service()
        self.llm = get_llm_service()
        self.embeddings = get_embedding_service()
        self.index_name = self.settings.OPENSEARCH_INDEX_NAME
    
    # ========================================================================
    # Basic Structured Search
    # ========================================================================
    
    def basic_search(self, request: BasicSearchRequest) -> BasicSearchResponse:
        """
        Perform structured company search with filters.
        Fast path using OpenSearch only.
        """
        start_time = time.time()
        
        try:
            # Build OpenSearch query
            query = self._build_filter_query(request)
            
            # Build aggregations for facets
            aggs = self._build_aggregations()
            
            # Execute search
            from_ = (request.page - 1) * request.limit
            response = self.opensearch.search_with_aggs(
                index=self.index_name,
                query=query,
                aggs=aggs,
                size=request.limit,
                from_=from_
            )
            
            # Process results
            results = self._process_search_results(response)
            facets = self._process_facets(response.get("aggregations", {}))
            
            search_time_ms = int((time.time() - start_time) * 1000)
            
            logger.info("basic_search_completed",
                       total_hits=response["hits"]["total"].get("value", 0),
                       results_returned=len(results),
                       time_ms=search_time_ms)
            
            return BasicSearchResponse(
                total=response["hits"]["total"].get("value", 0),
                page=request.page,
                limit=request.limit,
                results=results,
                facets=facets,
                search_time_ms=search_time_ms
            )
            
        except Exception as e:
            logger.error("basic_search_failed", error=str(e))
            raise
    
    def _build_filter_query(self, request: BasicSearchRequest) -> Dict[str, Any]:
        """Build OpenSearch query from filter request"""
        filters = []
        must_queries = []
        
        # Text search
        if request.q:
            must_queries.append({
                "multi_match": {
                    "query": request.q,
                    "fields": [
                        "name^3",           # Boost name matches
                        "domain^2",
                        "industry",
                        "locality"
                    ],
                    "type": "best_fields",
                    "operator": "or"
                }
            })
        
        # Industry filter
        if request.industry:
            filters.append({
                "terms": {
                    "industry.keyword": request.industry
                }
            })
        
        # Country filter
        if request.country:
            filters.append({
                "term": {
                    "country.keyword": request.country
                }
            })
        
        # Locality filter
        if request.locality:
            filters.append({
                "match": {
                    "locality": {
                        "query": request.locality,
                        "operator": "and"
                    }
                }
            })
        
        # Year founded range
        if request.year_from or request.year_to:
            year_filter = {}
            if request.year_from:
                year_filter["gte"] = request.year_from
            if request.year_to:
                year_filter["lte"] = request.year_to
            filters.append({"range": {"year_founded": year_filter}})
        
        # Company size filter
        if request.size:
            size_ranges = self._map_size_to_ranges(request.size)
            filters.append({
                "terms": {
                    "size_range.keyword": size_ranges
                }
            })
        
        # Combine filters
        if filters or must_queries:
            query = {"bool": {}}
            if must_queries:
                query["bool"]["must"] = must_queries if len(must_queries) > 1 else must_queries[0]
            if filters:
                query["bool"]["filter"] = filters
            return query
        
        return {"match_all": {}}
    
    def _map_size_to_ranges(self, sizes: List[str]) -> List[str]:
        """Map size categories to actual ranges"""
        size_mapping = {
            "small": ["1-10", "11-50", "51-200"],
            "medium": ["201-500", "501-1000", "1001-5000", "5001-10000"],
            "large": ["10001+"],
            "enterprise": ["10001+"]
        }
        
        ranges = []
        for size in sizes:
            ranges.extend(size_mapping.get(size.lower(), []))
        
        return list(set(ranges))  # Remove duplicates
    
    def _build_aggregations(self) -> Dict[str, Any]:
        """Build aggregations for faceted search"""
        return {
            "industries": {
                "terms": {
                    "field": "industry.keyword",
                    "size": 20
                }
            },
            "countries": {
                "terms": {
                    "field": "country.keyword",
                    "size": 50
                }
            },
            "sizes": {
                "terms": {
                    "field": "size_range.keyword",
                    "size": 10
                }
            },
            "years": {
                "range": {
                    "field": "year_founded",
                    "ranges": [
                        {"to": 1990},
                        {"from": 1990, "to": 2000},
                        {"from": 2000, "to": 2010},
                        {"from": 2010, "to": 2020},
                        {"from": 2020}
                    ]
                }
            }
        }
    
    def _process_search_results(self, opensearch_response: Dict[str, Any]) -> List[CompanySearchResult]:
        """Convert OpenSearch results to CompanySearchResult objects"""
        results = []
        
        for hit in opensearch_response["hits"]["hits"]:
            source = hit["_source"]
            
            company = Company(
                id=source.get("company_id", hit["_id"]),
                name=source.get("name"),
                domain=source.get("domain"),
                year_founded=source.get("year_founded"),
                industry=source.get("industry"),
                size_range=source.get("size_range"),
                country=source.get("country"),
                locality=source.get("locality"),
                linkedin_url=source.get("linkedin_url"),
                current_employee_estimate=source.get("current_employee_estimate"),
                total_employee_estimate=source.get("total_employee_estimate")
            )
            
            result = CompanySearchResult(
                company=company,
                relevance_score=hit.get("_score", 0) / 10.0,  # Normalize to 0-1
                matching_reason=None
            )
            
            results.append(result)
        
        return results
    
    def _process_facets(self, aggs: Dict[str, Any]) -> SearchFacets:
        """Convert aggregations to SearchFacets"""
        return SearchFacets(
            industries=[
                FacetValue(name=b["key"], count=b["doc_count"])
                for b in aggs.get("industries", {}).get("buckets", [])
            ],
            countries=[
                FacetValue(name=b["key"], count=b["doc_count"])
                for b in aggs.get("countries", {}).get("buckets", [])
            ],
            size_ranges=[
                FacetValue(name=b["key"], count=b["doc_count"])
                for b in aggs.get("sizes", {}).get("buckets", [])
            ]
        )
    
    # ========================================================================
    # Intelligent Search with LLM
    # ========================================================================
    
    def intelligent_search(self, request: IntelligentSearchRequest) -> IntelligentSearchResponse:
        """
        Intelligent search using LLM for query understanding.
        Extracts entities and applies smart filtering.
        """
        start_time = time.time()
        
        try:
            # Step 1: Classify query using LLM
            query_understanding = self._classify_and_understand_query(request.query)
            
            # Step 2: Build search request from understanding
            search_request = self._build_search_request_from_understanding(
                query_understanding,
                request
            )
            
            # Step 3: Execute search
            search_response = self.basic_search(search_request)
            
            # Step 4: Enhance results with explanations
            results = self._enhance_results_with_explanations(
                search_response.results,
                request.query,
                query_understanding
            )
            
            search_time_ms = int((time.time() - start_time) * 1000)
            
            logger.info("intelligent_search_completed",
                       intent=query_understanding.intent,
                       results=len(results),
                       time_ms=search_time_ms)
            
            return IntelligentSearchResponse(
                query_understanding=query_understanding,
                results=results[:request.max_results],
                search_time_ms=search_time_ms,
                query_classified=True,
                facets=search_response.facets
            )
            
        except Exception as e:
            logger.error("intelligent_search_failed", error=str(e))
            raise
    
    def _classify_and_understand_query(self, query: str) -> QueryUnderstanding:
        """Use LLM to understand and classify query"""
        try:
            classification = self.llm.classify_query(query)
            
            return QueryUnderstanding(
                intent=classification.get("intent", "filtered_search"),
                entities=classification.get("entities", {}),
                confidence=classification.get("confidence", 0.5)
            )
        except Exception as e:
            logger.error("query_understanding_failed", error=str(e))
            # Fallback to simple parsing
            return QueryUnderstanding(
                intent="filtered_search",
                entities={"keywords": [query]},
                confidence=0.3
            )
    
    def _build_search_request_from_understanding(
        self,
        understanding: QueryUnderstanding,
        original_request: IntelligentSearchRequest
    ) -> BasicSearchRequest:
        """Build structured search request from LLM understanding"""
        entities = understanding.entities
        
        return BasicSearchRequest(
            q=entities.get("keywords", [""])[0] if entities.get("keywords") else "",
            industry=entities.get("industries", None),
            country=entities.get("locations", [None])[0] if entities.get("locations") else None,
            year_from=entities.get("year_range", [None, None])[0] if entities.get("year_range") else None,
            year_to=entities.get("year_range", [None, None])[1] if entities.get("year_range") else None,
            limit=min(original_request.max_results, 100)
        )
    
    def _enhance_results_with_explanations(
        self,
        results: List[CompanySearchResult],
        query: str,
        understanding: QueryUnderstanding
    ) -> List[CompanySearchResult]:
        """Add semantic explanations to results"""
        if not self.settings.ENABLE_SEMANTIC_SEARCH:
            return results
        
        enhanced = []
        for result in results[:10]:  # Limit to top 10 for efficiency
            try:
                explanation = self.llm.generate_semantic_explanation(
                    result.company.name,
                    result.company.industry,
                    query
                )
                result.matching_reason = explanation
            except Exception as e:
                logger.debug("explanation_generation_failed", error=str(e))
                result.matching_reason = None
            
            enhanced.append(result)
        
        return enhanced + results[10:]  # Append remaining results
    
    # ========================================================================
    # Semantic Vector Search
    # ========================================================================
    
    def semantic_search(self, request: SemanticSearchRequest) -> List[CompanySearchResult]:
        """
        Semantic search using vector embeddings.
        Finds companies semantically similar to the query.
        """
        start_time = time.time()
        
        try:
            # Generate embedding using local SentenceTransformer (msmarco-distilbert-base-tas-b)
            query_embedding = self.embeddings.embed(request.query)
            
            # Vector search in OpenSearch
            vector_results = self.opensearch.vector_search(
                index=self.index_name,
                vector_field="vector_embedding",
                query_vector=query_embedding,
                k=request.top_k,
                min_score=request.similarity_threshold
            )
            
            # Convert to CompanySearchResult
            results = []
            for result in vector_results:
                company = Company(**result["source"])
                results.append(CompanySearchResult(
                    company=company,
                    relevance_score=result["score"],
                    matching_reason=f"Semantically similar to: {request.query}"
                ))
            
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info("semantic_search_completed",
                       results=len(results),
                       time_ms=elapsed_ms)
            
            return results
            
        except Exception as e:
            logger.error("semantic_search_failed", error=str(e))
            return []


@lru_cache(maxsize=1)
def get_search_service() -> SearchService:
    """Get or create search service singleton"""
    return SearchService()
