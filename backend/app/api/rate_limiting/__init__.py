"""Rate Limiting Abstraction (Sprint 60) — provider-independent
interfaces for per-user, per-IP, and per-route rate limiting with burst
and sustained allowances. No concrete implementation ships this sprint
("No Redis. No external implementation.") — see `app.api.rate_limiting
.models`'s own module docstring for the precedent this follows.
"""

from app.api.rate_limiting.limiter import RateLimiter
from app.api.rate_limiting.models import RateLimitDecision, RateLimitRule, RateLimitScope

__all__ = ["RateLimiter", "RateLimitScope", "RateLimitRule", "RateLimitDecision"]
