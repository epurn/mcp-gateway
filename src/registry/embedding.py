"""Embedding generation for tool descriptions using Sentence Transformers."""

import asyncio
from functools import lru_cache
from typing import List

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Get or create the embedding model (cached singleton).
    
    Returns:
        Loaded SentenceTransformer model
        
    Raises:
        RuntimeError: If sentence-transformers is not installed
    """
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        raise RuntimeError(
            "sentence-transformers not installed. "
            "Install with: pip install sentence-transformers"
        )
    
    # all-MiniLM-L6-v2: 384 dimensions, lightweight, fast
    # Downloads automatically on first use (~80MB)
    return SentenceTransformer('all-MiniLM-L6-v2')


async def generate_embedding(text: str) -> list[float]:
    """Generate embedding vector for tool description.
    
    Args:
        text: Tool description to embed
        
    Returns:
        384-dimensional embedding vector
    """
    model = get_embedding_model()
    
    # Run in thread pool to avoid blocking event loop
    loop = asyncio.get_event_loop()
    embedding = await loop.run_in_executor(
        None,
        model.encode,
        text
    )
    
    return embedding.tolist()


async def batch_generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts (batch optimization).
    
    Args:
        texts: List of tool descriptions to embed
        
    Returns:
        List of 384-dimensional embedding vectors
    """
    model = get_embedding_model()
    
    # Run in thread pool to avoid blocking event loop
    loop = asyncio.get_event_loop()
    embeddings = await loop.run_in_executor(
        None,
        model.encode,
        texts
    )
    
    return [emb.tolist() for emb in embeddings]
