"""
Intent Classifier Service - Routes queries to the appropriate search bucket.
Uses GPT-4o-mini with Instructor for deterministic, structured output.
"""
import structlog
import json
from functools import lru_cache
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime
import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
from app.config import get_settings

logger = structlog.get_logger(__name__)


class SearchIntent(str, Enum):
    """Query intent categories for routing"""
    REGULAR = "regular"
    SEMANTIC = "semantic"
    AGENTIC = "agentic"


class QueryIntent(BaseModel):
    """Structured intent output from classifier"""
    category: SearchIntent = Field(
        description="Query routing bucket: 'regular' for exact/name searches, "
        "'semantic' for conceptual/synonym queries, 'agentic' for external data"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Classification confidence score (0-1)"
    )
    filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted structured filters: location, industry, year, etc."
    )
    search_query: str = Field(
        description="Optimized query string for OpenSearch"
    )
    needs_external_data: bool = Field(
        default=False,
        description="True if query requires external APIs (news, funding, etc.)"
    )
    external_data_type: Optional[str] = Field(
        default=None,
        description="Type of external data needed: 'news', 'funding', 'events', etc."
    )
    reasoning: str = Field(
        description="Brief reasoning for the classification decision"
    )


class IntentClassifier:
    """
    Classifies search queries into buckets using GPT-4o-mini + Instructor.
    Ensures deterministic, structured routing decisions.
    """
    
    def __init__(self):
        """Initialize classifier with Instructor-patched OpenAI client"""
        self.settings = get_settings()
        
        # Create base OpenAI client
        self.client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        
        # Patch with Instructor for structured outputs
        self.client = instructor.from_openai(self.client)
        self.model = self.settings.OPENAI_MINI_MODEL
        self.confidence_threshold = self.settings.CLASSIFIER_CONFIDENCE_THRESHOLD
        self.timeout = self.settings.CLASSIFIER_TIMEOUT
        
        logger.info(
            "intent_classifier_initialized",
            model=self.model,
            confidence_threshold=self.confidence_threshold
        )
        self._classify_cache: Dict[str, QueryIntent] = {}
        self._cache_maxsize = 256
    
    def classify(self, query: str, trace_id: Optional[str] = None) -> QueryIntent:
        """
        Classify a query and route to appropriate search bucket.
        
        Args:
            query: User's search query
            trace_id: Optional trace ID for observability
        
        Returns:
            QueryIntent with category, filters, and reasoning
        """
        if not query or not query.strip():
            logger.warning("empty_query_received", trace_id=trace_id)
            return self._empty_query_intent()

        cache_key = query.strip().lower()
        if cache_key in self._classify_cache:
            logger.info("classification_cache_hit", query=query[:100])
            return self._classify_cache[cache_key]

        trace_id = trace_id or self._generate_trace_id()
        
        system_prompt = """You are an intelligent query router for a company search system.
Your job is to classify queries into exactly one of three buckets:

1. REGULAR: Simple, structured queries for EXACT name/acronym matches
   - User is searching for a specific company by name (e.g., "Apple", "Microsoft", "IBM")
   - Single keywords or acronyms (e.g., "FAANG", "TSMC")
   - Use OpenSearch BM25 (lexical search) - fast, precise
   - NOTE: these queries rarely have descriptive adjectives or industry concepts

2. SEMANTIC: Natural language with CONCEPTUAL or DESCRIPTIVE intent
   - Queries describing a type of company (e.g., "green energy companies", "fintech startups")
   - Multi-concept queries (e.g., "AI companies in healthcare", "SaaS companies in Europe")
   - Vague or exploratory (e.g., "companies like Netflix", "sustainable tech firms")
   - Requires vector embeddings and semantic understanding
   - IMPORTANT: SEMANTIC queries CAN and often DO include location or industry filters
     (e.g., "clean energy companies in Germany" → SEMANTIC with location_country=Germany)
   - "tech companies in california" → SEMANTIC with location_country="United States", location_state="California"

3. AGENTIC: Queries needing EXTERNAL/TIME-SENSITIVE data
   - Recent events (e.g., "companies that raised funding recently")
   - News-based queries (e.g., "tech news this week")
   - Real-time data (e.g., "trending startups now", "companies that IPO'd last month")
   - Meta-questions about data (e.g., "what data do you have?")

CRITICAL RULES:
- If query contains time-sensitive keywords (recent, latest, today, this month, last X months, news, IPO, funding round), classify as AGENTIC
- If query is vague, conceptual, or describes a TYPE of company, classify as SEMANTIC
- If query is exclusively a specific company name or acronym with no descriptive context, classify as REGULAR
- Always extract location into THREE separate keys: location_country, location_state, location_city
  - "california" → location_country="United States", location_state="California"
  - "new york" → location_country="United States", location_state="New York" (or location_city="New York" if clearly a city)
  - "germany" → location_country="Germany"
  - "london" → location_country="United Kingdom", location_city="London"
- Extract industry as a canonical label (e.g. "technology", "healthcare", "finance")
- Provide a normalized search_query string stripping location/filter values

Return structured JSON with confidence, filters, and reasoning."""

        user_prompt = f"""Classify this query: "{query}"

Return a JSON object with:
- category: regular|semantic|agentic
- confidence: 0.0-1.0
- filters: {{
    "location_country": "...",   // country name or null
    "location_state": "...",     // state/province or null
    "location_city": "...",      // city or null
    "industry": "...",           // industry label or null
    "year_from": null,
    "year_to": null,
    "size_range": null
  }}
- search_query: normalized query string (strip location/filter words)
- needs_external_data: true/false
- external_data_type: null or 'news'|'funding'|'events'
- reasoning: 1-2 sentence explanation of classification"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_model=QueryIntent,
                timeout=self.timeout
            )
            
            logger.info(
                "query_classified",
                trace_id=trace_id,
                query=query[:100],
                category=response.category.value,
                confidence=response.confidence,
                reasoning=response.reasoning
            )

            if len(self._classify_cache) >= self._cache_maxsize:
                self._classify_cache.pop(next(iter(self._classify_cache)))
            self._classify_cache[cache_key] = response

            return response
            
        except Exception as e:
            logger.error(
                "classification_failed",
                trace_id=trace_id,
                query=query[:100],
                error=str(e)
            )
            # Fallback: return semantic for safety
            return self._semantic_fallback_intent(query)
    
    def _empty_query_intent(self) -> QueryIntent:
        """Return intent for empty/None queries"""
        return QueryIntent(
            category=SearchIntent.REGULAR,
            confidence=1.0,
            filters={},
            search_query="",
            needs_external_data=False,
            reasoning="Empty query - returning empty intent"
        )
    
    def _semantic_fallback_intent(self, query: str) -> QueryIntent:
        """Fallback for classification errors - default to semantic"""
        return QueryIntent(
            category=SearchIntent.SEMANTIC,
            confidence=0.5,
            filters={},
            search_query=query,
            needs_external_data=False,
            reasoning="Classification error - defaulting to semantic search"
        )
    
    @staticmethod
    def _generate_trace_id() -> str:
        """Generate a unique trace ID"""
        from uuid import uuid4
        return f"trace_{uuid4().hex[:12]}"


# ============================================================================
# Singleton Pattern - Lazy Initialization
# ============================================================================

@lru_cache(maxsize=1)
def get_intent_classifier() -> IntentClassifier:
    """
    Get or create intent classifier instance (singleton).
    Used as a dependency in FastAPI endpoints.
    """
    return IntentClassifier()
