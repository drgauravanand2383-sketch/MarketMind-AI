"""Errors raised by PennyMicrocapIntelligenceAgent.

Mirrors `app.agents.company_research.agent`'s own four-tier hierarchy —
see `app.agents.global_markets_research.exceptions` for the identical
sibling used by the main-category agent.
"""

from __future__ import annotations

from app.global_markets.models import ReportCategory

__all__ = [
    "PennyMicrocapIntelligenceAgentError",
    "PromptRenderingError",
    "LLMGenerationError",
    "ResponseParsingError",
    "ReportValidationError",
]


class PennyMicrocapIntelligenceAgentError(Exception):
    """Base class for every AGT-007 error."""

    def __init__(self, message: str, *, category: ReportCategory | None = None) -> None:
        self.category = category
        super().__init__(message)


class PromptRenderingError(PennyMicrocapIntelligenceAgentError):
    """Raised when rendering the Penny/Micro-cap Intelligence prompt fails."""


class LLMGenerationError(PennyMicrocapIntelligenceAgentError):
    """Raised when LLMService.generate() fails — timeout, auth, rate limit, provider unavailable, or config."""


class ResponseParsingError(PennyMicrocapIntelligenceAgentError):
    """Raised when the LLM's response isn't valid JSON, or doesn't match the expected narrative schema."""


class ReportValidationError(PennyMicrocapIntelligenceAgentError):
    """Raised when the parsed narrative fails this agent's own validation
    (e.g. an empty summary, a missing risk_note, or an ungrounded ticker/rank reference)."""
