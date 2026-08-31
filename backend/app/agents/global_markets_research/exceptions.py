"""Errors raised by GlobalMarketsResearchAgent.

Mirrors `app.agents.company_research.agent`'s own four-tier hierarchy:
never leaks a raw `LLMServiceError`/prompt-framework/pydantic exception —
every failure is translated into one of the typed errors below.
"""

from __future__ import annotations

from app.global_markets.models import ReportCategory

__all__ = [
    "GlobalMarketsResearchAgentError",
    "PromptRenderingError",
    "LLMGenerationError",
    "ResponseParsingError",
    "ReportValidationError",
]


class GlobalMarketsResearchAgentError(Exception):
    """Base class for every AGT-006 error."""

    def __init__(self, message: str, *, category: ReportCategory | None = None) -> None:
        self.category = category
        super().__init__(message)


class PromptRenderingError(GlobalMarketsResearchAgentError):
    """Raised when rendering the Global Markets Research prompt fails."""


class LLMGenerationError(GlobalMarketsResearchAgentError):
    """Raised when LLMService.generate() fails — timeout, auth, rate limit, provider unavailable, or config."""


class ResponseParsingError(GlobalMarketsResearchAgentError):
    """Raised when the LLM's response isn't valid JSON, or doesn't match the expected narrative schema."""


class ReportValidationError(GlobalMarketsResearchAgentError):
    """Raised when the parsed narrative fails this agent's own validation
    (e.g. an empty summary, or a commentary referencing an ungrounded ticker/rank)."""
