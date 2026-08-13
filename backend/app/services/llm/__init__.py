"""LLM Service — the single entry point every AI-powered agent uses to generate completions.

`LLMService` (service.py) hides provider-specific implementations behind
`BaseLLMProvider` (`app.providers.anthropic.provider`); `LLMRequest`/
`LLMResponse` (models.py) are its own typed shapes, independent of any
provider or SDK model.
"""

from app.services.llm.models import (
    ConversationMessage,
    ConversationRole,
    LLMHealthStatus,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from app.services.llm.service import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMService,
    LLMServiceError,
    LLMTimeoutError,
)

__all__ = [
    "ConversationRole",
    "ConversationMessage",
    "LLMRequest",
    "TokenUsage",
    "LLMResponse",
    "LLMHealthStatus",
    "LLMServiceError",
    "LLMConfigurationError",
    "LLMProviderUnavailableError",
    "LLMTimeoutError",
    "LLMAuthenticationError",
    "LLMRateLimitError",
    "LLMService",
]
