"""Unit tests for ProviderConfig and ProviderResult."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.providers.models import ProviderConfig, ProviderResult


def test_provider_config_defaults() -> None:
    config = ProviderConfig(provider_id="rss")
    assert config.enabled is True
    assert config.timeout == 10.0
    assert config.retry_attempts == 0
    assert config.rate_limit_per_minute is None
    assert config.extra == {}


def test_provider_config_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(provider_id="rss", feed_url="https://example.com/feed.xml")


def test_provider_config_accepts_provider_specific_settings_via_extra() -> None:
    config = ProviderConfig(provider_id="rss", extra={"feed_url": "https://example.com/feed.xml"})
    assert config.extra["feed_url"] == "https://example.com/feed.xml"


def test_provider_result_defaults() -> None:
    result = ProviderResult(
        provider_id="rss",
        fetched_at=datetime.now(UTC),
        success=True,
    )
    assert result.data is None
    assert result.metadata == {}
    assert result.error is None


def test_provider_result_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ProviderResult(
            provider_id="rss",
            fetched_at=datetime.now(UTC),
            success=True,
            unexpected_field="value",
        )
