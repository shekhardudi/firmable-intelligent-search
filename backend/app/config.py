"""
Configuration management for the search application.
Handles environment variables and application settings.
"""
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic_settings import BaseSettings
import os
import yaml


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # API Configuration
    API_TITLE: str = "Firmable Intelligent Company Search API"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = "AI-powered company search with semantic understanding"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    
    # OpenSearch Configuration
    OPENSEARCH_HOST: str = "localhost"
    OPENSEARCH_PORT: int = 9200
    OPENSEARCH_USER: str = "admin"
    OPENSEARCH_PASSWORD: str = "MySecurePassword123!"
    OPENSEARCH_SCHEME: str = "https"
    OPENSEARCH_VERIFY_CERTS: bool = False
    OPENSEARCH_INDEX_NAME: str = "companies-new"
    OPENSEARCH_SIZE_LIMIT: int = 10000
    
    # OpenAI Configuration
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: Optional[str] = None
    OPENAI_API_VERSION: Optional[str] = None
    OPENAI_DEPLOYMENT_NAME: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4-turbo"
    OPENAI_MINI_MODEL: str = "gpt-4o-mini"  # For Intent Classification
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-large"
    OPENAI_EMBEDDING_DIMENSION: int = 8192
    OPENAI_REQUEST_TIMEOUT: int = 30
    
    # Claude Configuration (Optional)
    ANTHROPIC_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-3-opus-20240229"
    
    # Database Configuration
    DATABASE_URL: str = "postgresql://firmable_user:password123@localhost:5432/firmable_search"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT: int = 30
    
    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL: int = 3600  # 1 hour default TTL
    CACHE_ENABLED: bool = True
    
    # Search Configuration
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100
    SEARCH_TIMEOUT: int = 30  # seconds
    MIN_CONFIDENCE_SCORE: float = 0.5
    SEMANTIC_SIMILARITY_THRESHOLD: float = 0.7
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 100
    RATE_LIMIT_OPENAI_REQUESTS_PER_MINUTE: int = 1800  # 30 RPS


    # Performance Tuning
    MAX_CONCURRENT_OPENSEARCH_REQUESTS: int = 50
    MAX_CONCURRENT_LLM_REQUESTS: int = 10
    REQUEST_QUEUE_SIZE: int = 1000
    
    # Features
    ENABLE_SEMANTIC_SEARCH: bool = True
    ENABLE_AGENTIC_SEARCH: bool = True
    ENABLE_QUERY_CLASSIFICATION: bool = True
    ENABLE_CACHING: bool = True
    
    # Intent Classifier Configuration
    CLASSIFIER_CONFIDENCE_THRESHOLD: float = 0.7
    CLASSIFIER_TIMEOUT: int = 10  # seconds
    
    # Hybrid Search Configuration
    LEXICAL_WEIGHT: float = 0.4  # BM25 weight
    SEMANTIC_WEIGHT: float = 0.6  # Vector search weight
    MIN_SEMANTIC_SCORE: float = 0.3
    
    # Tracing & Observability
    ENABLE_TRACING: bool = True

    # OpenTelemetry — app sends to OTel Collector via OTLP/gRPC
    OTLP_ENDPOINT: str = "http://localhost:4317"
    OTEL_SERVICE_NAME: str = "firmable-search"

    # Search config file path (relative to backend/ directory or absolute)
    SEARCH_CONFIG_PATH: str = "search_config.yaml"

    class Config:
        env_file = ".env"
        case_sensitive = True
        
    @property
    def opensearch_url(self) -> str:
        """Construct OpenSearch connection URL"""
        scheme = self.OPENSEARCH_SCHEME
        user = self.OPENSEARCH_USER
        password = self.OPENSEARCH_PASSWORD
        host = self.OPENSEARCH_HOST
        port = self.OPENSEARCH_PORT
        return f"{scheme}://{user}:{password}@{host}:{port}"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT == "development"


@lru_cache()
def get_settings() -> Settings:
    """Dependency injection for settings"""
    return Settings(
        OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", ""),
        ANTHROPIC_API_KEY=os.getenv("ANTHROPIC_API_KEY", "")
    )


@lru_cache(maxsize=1)
def get_search_config() -> Dict[str, Any]:
    """Load and cache search_config.yaml from the backend directory."""
    settings = get_settings()
    config_path = Path(settings.SEARCH_CONFIG_PATH)
    if not config_path.is_absolute():
        # Resolve relative to the backend/ directory (parent of app/)
        config_path = Path(__file__).parent.parent / config_path
    with config_path.open() as fh:
        return yaml.safe_load(fh)
