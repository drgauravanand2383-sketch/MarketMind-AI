"""Provider-independent data shapes for the rate limiting abstraction
(Sprint 60). No concrete rate limiter ships this sprint — mirrors
`app.providers.embedding.provider.BaseEmbeddingProvider`, which has
shipped as an interface with zero concrete implementations since Sprint
55 (`app/bootstrap.py`'s own `build_embedding_provider` documents this as
an accepted, intentional pattern in this codebase: "No concrete
BaseEmbeddingProvider implementation exists yet... explicitly deferred").
A production implementation (in-memory, Redis, or otherwise) is out of
this sprint's explicit scope ("No Redis. No external implementation.").
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["RateLimitScope", "RateLimitRule", "RateLimitDecision"]


class RateLimitScope(StrEnum):
    """The dimension a rate limit is keyed by."""

    PER_USER = "PER_USER"
    PER_IP = "PER_IP"
    PER_ROUTE = "PER_ROUTE"


class RateLimitRule(BaseModel):
    """One configured limit: a short burst allowance plus a longer
    sustained rate, each expressed as (max requests, window). A caller
    composes the lookup `key` itself (e.g. `f"{scope}:{route}:{user_id}"`)
    — this model only describes the *limit*, not identity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: RateLimitScope
    burst_limit: int = Field(gt=0, description="Maximum requests allowed within burst_window_seconds.")
    burst_window_seconds: float = Field(gt=0)
    sustained_limit: int = Field(gt=0, description="Maximum requests allowed within sustained_window_seconds.")
    sustained_window_seconds: float = Field(gt=0)


class RateLimitDecision(BaseModel):
    """The outcome of one `RateLimiter.check()` call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    scope: RateLimitScope
    limit: int = Field(gt=0, description="The limit this decision was evaluated against.")
    remaining: int = Field(ge=0, description="Requests still permitted before the limit is reached.")
    retry_after_seconds: float | None = Field(
        default=None, ge=0, description="Set when `allowed` is False — how long until a retry may succeed."
    )
