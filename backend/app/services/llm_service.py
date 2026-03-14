"""
LLM service for query understanding, classification, and semantic operations.
Handles OpenAI API interactions.
"""
import json
from functools import lru_cache
from typing import Dict, List, Any, Optional
from openai import OpenAI, AzureOpenAI
import structlog
from app.config import get_settings
from tenacity import retry, stop_after_attempt, wait_exponential
import asyncio

logger = structlog.get_logger(__name__)


class LLMService:
    """Service for LLM operations"""
    
    def __init__(self):
        """Initialize LLM client"""
        self.settings = get_settings()
        self._client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize OpenAI or Azure OpenAI client"""
        try:
            # Check if using Azure OpenAI
            if self.settings.OPENAI_API_BASE and "azure" in self.settings.OPENAI_API_BASE.lower():
                self._client = AzureOpenAI(
                    api_key=self.settings.OPENAI_API_KEY,
                    api_version=self.settings.OPENAI_API_VERSION or "2024-02-15-preview",
                    azure_endpoint=self.settings.OPENAI_API_BASE,
                )
                logger.info("azure_openai_client_initialized")
            else:
                # Use standard OpenAI
                self._client = OpenAI(
                    api_key=self.settings.OPENAI_API_KEY,
                )
                logger.info("openai_client_initialized")
        except Exception as e:
            logger.error("llm_client_initialization_failed", error=str(e))
            raise
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def classify_query(self, query: str) -> Dict[str, Any]:
        """
        Use LLM to classify the query intent and extract parameters.
        
        Returns:
            {
                "intent": "filtered_search|semantic_search|complex_query",
                "entities": {
                    "industries": [...],
                    "locations": [...],
                    "year_range": [from, to],
                    "size_range": [min, max],
                    "keywords": [...]
                },
                "confidence": 0.95,
                "explanation": "..."
            }
        """
        try:
            system_prompt = """You are an expert query classifier for a company search system.
Analyze the user query and extract:
1. Search intent (filtered_search, semantic_search, complex_query, funding_query)
2. Entities (industries, locations, year ranges, company sizes, keywords)
3. Confidence score (0-1)

Return a JSON object with these fields."""
            
            user_message = f"""Classify this query: "{query}"
            
Return JSON with: intent, entities, confidence"""
            
            response = self._client.chat.completions.create(
                model=self.settings.OPENAI_DEPLOYMENT_NAME or self.settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            logger.info("query_classified", 
                       intent=result.get("intent"),
                       confidence=result.get("confidence"))
            return result
            
        except Exception as e:
            logger.error("query_classification_failed", error=str(e), query=query)
            raise
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text.
        Uses text-embedding-3-large for rich semantic representation.
        """
        try:
            response = self._client.embeddings.create(
                model=self.settings.OPENAI_EMBEDDING_MODEL,
                input=text,
                encoding_format="float"
            )
            
            embedding = response.data[0].embedding
            logger.debug("embedding_generated", 
                        text_length=len(text),
                        embedding_dimension=len(embedding))
            return embedding
            
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e), text=text[:100])
            raise
    
    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts efficiently"""
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                response = self._client.embeddings.create(
                    model=self.settings.OPENAI_EMBEDDING_MODEL,
                    input=batch,
                    encoding_format="float"
                )
                
                for item in response.data:
                    embeddings.append(item.embedding)
                
                logger.debug("batch_embeddings_generated", 
                           batch_size=len(batch),
                           total_so_far=len(embeddings))
                
            except Exception as e:
                logger.error("batch_embedding_failed", error=str(e))
                raise
        
        return embeddings
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate_semantic_explanation(
        self,
        company_name: str,
        company_industry: str,
        query: str
    ) -> str:
        """
        Generate a semantic explanation of why a company matches a query.
        """
        try:
            response = self._client.chat.completions.create(
                model=self.settings.OPENAI_DEPLOYMENT_NAME or self.settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a search relevance expert. Provide a one-line explanation of why a company matches a search query."
                    },
                    {
                        "role": "user",
                        "content": f"Company: {company_name} ({company_industry})\nQuery: {query}\nWhy is this company relevant?"
                    }
                ],
                temperature=0.5,
                max_tokens=100
            )
            
            explanation = response.choices[0].message.content.strip()
            return explanation
            
        except Exception as e:
            logger.error("semantic_explanation_failed", error=str(e))
            return f"Matched query: {query}"
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def extract_query_entities(self, query: str) -> Dict[str, Any]:
        """
        Extract structured entities from query.
        Returns: industries, locations, year_range, company_sizes, keywords
        """
        try:
            response = self._client.chat.completions.create(
                model=self.settings.OPENAI_DEPLOYMENT_NAME or self.settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": """Extract entities from company search queries. Return JSON with:
- industries: list of industry keywords
- locations: list of locations (country/city)
- year_range: [min_year, max_year] or null
- employee_range: [min, max] or null
- keywords: other relevant keywords"""
                    },
                    {
                        "role": "user",
                        "content": f"Query: {query}"
                    }
                ],
                temperature=0.2,
                max_tokens=300,
                response_format={"type": "json_object"}
            )
            
            entities = json.loads(response.choices[0].message.content)
            logger.debug("entities_extracted", 
                        industries=len(entities.get("industries", [])),
                        locations=len(entities.get("locations", [])))
            return entities
            
        except Exception as e:
            logger.error("entity_extraction_failed", error=str(e))
            return {"industries": [], "locations": [], "keywords": []}
    
    def health_check(self) -> bool:
        """Check if LLM service is available"""
        try:
            response = self._client.models.list()
            logger.debug("llm_health_check_passed")
            return True
        except Exception as e:
            logger.error("llm_health_check_failed", error=str(e))
            return False


@lru_cache(maxsize=1)
def get_llm_service() -> LLMService:
    """Get or create LLM service singleton"""
    return LLMService()
