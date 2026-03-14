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
    field_boosts: Dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Per-field boost multipliers for the OpenSearch multi_match clause. "
            "Only populated for SEMANTIC queries. "
            "Keys: name, domain, industry, searchable_text, locality. "
            "Values: boost multiplier (e.g. 3.0 = 3x weight). "
            "Empty dict means fall back to hardcoded defaults."
        )
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
  - "united states" / "usa" / "us" / "america" → location_country="United States", location_state=null
  - "germany" → location_country="Germany"
  - "london" → location_country="United Kingdom", location_city="London"
  - "australia" → location_country="Australia", location_state=null
  - Always preserve the FULL English country name (e.g. "United States" not "US", "United Kingdom" not "UK")
- If query contains industry keywords, extract into "industry" key (e.g., "healthcare", "finance", "technology")
- If query contains year references (e.g., "founded before 2000", "established after 2010"), extract into "year_from" and "year_to"
- If query contains company size references (e.g., "startups", "large enterprises", "100-500 employees"), extract into "size_range" key
- If query contains funding or event references, set needs_external_data=true and external_data_type to 'funding' or 'events' accordingly
- If Country is mentioned without state, assume location_state=null but still classify as SEMANTIC (e.g., "tech companies in germany" → SEMANTIC with location_country="Germany", location_state=null)
- If any part of location is mentioned extract it, but do not let location alone determine SEMANTIC vs REGULAR (e.g., "california" alone should be REGULAR, but "apple in california" should be SEMANTIC)
- Extract industry as a canonical label (e.g. "technology", "healthcare", "finance")
- If query mentions country without state, extract country but do not assume state (e.g., "tech companies in united states" → location_country="United States", location_state=null)

FIELD BOOSTING (SEMANTIC queries only):
For SEMANTIC queries, you must also populate field_boosts — a dict controlling how much each OpenSearch field is weighted in the multi_match clause. The fields and their roles are:
  - "name":            the company's registered name  (boost high when user mentions a specific name pattern)
  - "domain":          the company's website domain   (boost high when user mentions web/tech/online presence)
  - "industry":        the industry label             (boost high when query is about an industry type)
  - "searchable_text": enriched text with taxonomy, tags, descriptions (boost high for broad conceptual queries)
  - "locality":        city/region where the company operates (boost high when query mentions a sub-country location)

Field boost rules:
  - Scale: use values between 1.0 (neutral) and 5.0 (very strong). Never use 0 or negative.
  - Every field must appear in field_boosts — do not omit any.
  - Default neutral value is 1.0. Use it for fields not relevant to the query intent.

Field boost examples:
  "AI companies in healthcare"
    → industry: 4.0, searchable_text: 3.0, name: 1.0, domain: 1.0, locality: 1.0
  "fintech startups in London"
    → industry: 3.0, locality: 3.0, searchable_text: 2.0, name: 1.0, domain: 1.0
  "companies like Stripe or Plaid"
    → name: 4.0, domain: 3.0, industry: 2.0, searchable_text: 2.0, locality: 1.0
  "sustainable energy companies"
    → industry: 4.0, searchable_text: 3.5, domain: 2.0, name: 1.0, locality: 1.0
  "B2B SaaS platforms with enterprise clients"
    → searchable_text: 4.0, industry: 3.0, domain: 2.0, name: 1.0, locality: 1.0
  "biotech firms near Boston"
    → industry: 3.0, locality: 4.0, searchable_text: 2.0, name: 1.0, domain: 1.0

For REGULAR or AGENTIC queries, return field_boosts as an empty dict {{}}.

Full country-name extraction examples:
  "tech companies in united states" → category=semantic, filters={{location_country="United States", location_state=null, industry="technology"}}, field_boosts={{industry:3.0, searchable_text:3.0, name:1.0, domain:1.0, locality:1.0}}
  "healthcare startups in usa" → category=semantic, filters={{location_country="United States", location_state=null, industry="healthcare"}}, field_boosts={{industry:4.0, searchable_text:3.0, name:1.0, domain:1.0, locality:1.0}}

Return structured JSON with confidence, filters, field_boosts, search_query, and reasoning."""

        user_prompt = f"""Classify this query: "{query}"

Return a JSON object with ALL of these keys:
- category: regular|semantic|agentic
- confidence: 0.0-1.0
- search_query: the cleaned query string with location/filter words stripped (e.g. "tech companies" not "tech companies in united states")
- filters: {{
    "location_country": "...",   // full English country name ("United States", "Germany") or null
    "location_state": "...",     // state/province or null
    "location_city": "...",      // city or null
    "industry": "...",           // canonical industry label or null
    "year_from": null,           // integer year or null
    "year_to": null,             // integer year or null
    "size_range": null           // e.g. "1-10", "startups", or null
  }}
- needs_external_data: true/false
- external_data_type: null or "news"|"funding"|"events"
- field_boosts: {{"name": 1.0, "domain": 1.0, "industry": 1.0, "searchable_text": 1.0, "locality": 1.0}}  // adjust values for SEMANTIC; return empty {{}} for REGULAR/AGENTIC
- reasoning: 1-2 sentence explanation"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
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
            field_boosts={},
            reasoning="Empty query - returning empty intent"
        )
    
    def _semantic_fallback_intent(self, query: str) -> QueryIntent:
        """Fallback for classification errors - default to semantic, use hardcoded defaults"""
        return QueryIntent(
            category=SearchIntent.SEMANTIC,
            confidence=0.5,
            filters={},
            search_query=query,
            needs_external_data=False,
            field_boosts={},  # empty → SemanticSearchStrategy will apply _DEFAULT_FIELD_BOOSTS
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
