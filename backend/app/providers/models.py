"""Framework-level data models shared by every provider.

ProviderConfig and ProviderResult define the common configuration and
result shape every provider (RSS, NSE, BSE, NewsAPI, Moneycontrol, Reuters,
Bloomberg, Yahoo Finance, and future sources) uses. No provider-specific
fields are modeled here — provider-specific settings and payloads live in
`extra` / `data`, keeping this framework provider-agnostic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ProviderConfig", "ProviderResult"]


class ProviderConfig(BaseModel):
    """Common configuration shared by every provider.

    Fields specific to one provider type (e.g. an RSS feed URL, a NewsAPI
    key) are not modeled here; they belong in `extra`, keeping this base
    config provider-agnostic while still validating the fields every
    provider needs regardless of source.
    """

    model_config = ConfigDict(extra="forbid")

    provider_id: str
    enabled: bool = True
    timeout: float = 10.0
    retry_attempts: int = 0
    rate_limit_per_minute: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ProviderResult(BaseModel):
    """Common result shape returned by every provider's `fetch`.

    `data` carries whatever a specific provider fetched, in whatever shape
    that provider defines — this framework does not interpret it.
    """

    model_config = ConfigDict(extra="forbid")

    provider_id: str
    fetched_at: datetime
    success: bool
    data: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
