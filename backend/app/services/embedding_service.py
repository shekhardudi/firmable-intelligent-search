"""
Embedding Service - Generates vector embeddings using msmarco-distilbert-base-tas-b.
Supports local model loading for fast inference without API calls.
"""
import structlog
import os
from functools import lru_cache
from typing import Dict, List, Optional
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
logger = structlog.get_logger(__name__)


class EmbeddingService:
    """
    Generates embeddings using sentence-transformers and the local msmarco model.
    This model is specifically tuned for information retrieval and ranked well
    in the MTEB benchmark for retrieval tasks.
    """
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize embedding service with local model.
        
        Args:
            model_path: Path to local msmarco model directory.
                       If None, will use default location.
        """
        self.model_path = model_path or self._find_local_model()
        self._model = None  # Lazy-load model on first use
        self.embedding_dim = 768  # msmarco output dimension
        self._embed_cache: Dict[str, List[float]] = {}
        self._cache_maxsize = 512
        
        logger.info(
            "embedding_service_initialized",
            model_path=self.model_path,
            embedding_dim=self.embedding_dim
        )
    
    def _find_local_model(self) -> str:
        """Find local msmarco model directory"""
        # Check common locations
        workspace_root = Path(__file__).parent.parent.parent
        possible_paths = [
            workspace_root / "msmarco-distilbert-base-tas-b",
            workspace_root / "backend" / "msmarco-distilbert-base-tas-b",
            Path.home() / "models" / "msmarco-distilbert-base-tas-b",
        ]
        
        for path in possible_paths:
            if path.exists():
                logger.info("local_model_found", path=str(path))
                return str(path)
        
        # Default to the HuggingFace model
        default = "sentence-transformers/msmarco-distilbert-base-tas-b"
        logger.warning(
            "local_model_not_found_using_hf",
            fallback_model=default
        )
        return default
    
    @property
    def model(self):
        """Lazy-load the sentence-transformer model"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_path)
                logger.info("sentence_transformer_model_loaded")
            except Exception as e:
                logger.error("model_loading_failed", error=str(e))
                raise
        
        return self._model
    
    def embed(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
        
        Returns:
            Embedding vector as list of floats
        """
        if not text or not text.strip():
            logger.warning("empty_text_embedding_requested")
            return [0.0] * self.embedding_dim

        cache_key = text.strip()
        if cache_key in self._embed_cache:
            return self._embed_cache[cache_key]

        try:
            embedding = self.model.encode(text, convert_to_tensor=False)
            result = embedding.tolist() if isinstance(embedding, np.ndarray) else embedding
            if len(self._embed_cache) >= self._cache_maxsize:
                self._embed_cache.pop(next(iter(self._embed_cache)))
            self._embed_cache[cache_key] = result
            return result
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e), text=text[:100])
            raise
    
    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Generate embeddings for multiple texts efficiently.
        
        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing
        
        Returns:
            List of embedding vectors
        """
        if not texts:
            logger.warning("empty_texts_batch_embedding_requested")
            return []
        
        try:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                convert_to_tensor=False,
                show_progress_bar=False
            )
            
            # Convert to list of lists
            if isinstance(embeddings, np.ndarray):
                return embeddings.tolist()
            return embeddings
        
        except Exception as e:
            logger.error(
                "batch_embedding_generation_failed",
                error=str(e),
                batch_size=len(texts)
            )
            raise
    
    def get_embedding_dimension(self) -> int:
        """Get embedding vector dimension"""
        return self.embedding_dim


# ============================================================================
# Singleton Pattern - Lazy Initialization
# ============================================================================

@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """
    Get or create embedding service instance (singleton).
    Used as a dependency in FastAPI endpoints.
    """
    return EmbeddingService()
