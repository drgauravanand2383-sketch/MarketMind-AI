"""Embedding Provider: abstraction for calling an external embedding API.

No real API call is implemented — concrete providers (e.g. wrapping the
Claude API or another embedding service) will subclass
BaseEmbeddingProvider in a future sprint.
"""

from app.providers.embedding.models import (
    EmbeddingChunkResult,
    EmbeddingProviderConfig,
    EmbeddingResult,
    EmbeddingVector,
    FailedEmbeddingRequest,
)
from app.providers.embedding.provider import BaseEmbeddingProvider

__all__ = [
    "BaseEmbeddingProvider",
    "EmbeddingProviderConfig",
    "EmbeddingVector",
    "FailedEmbeddingRequest",
    "EmbeddingChunkResult",
    "EmbeddingResult",
]
