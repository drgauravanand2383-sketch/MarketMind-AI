"""Unit tests for BaseProvider."""

from __future__ import annotations

import pytest

from app.providers.base import BaseProvider
from app.providers.models import ProviderConfig


def test_base_provider_cannot_be_instantiated(sample_config: ProviderConfig) -> None:
    with pytest.raises(TypeError):
        BaseProvider(sample_config)  # type: ignore[abstract]


def test_concrete_provider_exposes_identity(
    stub_provider_class: type[BaseProvider], sample_config: ProviderConfig
) -> None:
    provider = stub_provider_class(sample_config)
    assert provider.provider_id == "stub"
    assert provider.provider_name == "Stub Provider"
    assert provider.version == "0.1.0"


def test_concrete_provider_exposes_injected_config(
    stub_provider_class: type[BaseProvider], sample_config: ProviderConfig
) -> None:
    provider = stub_provider_class(sample_config)
    assert provider.config is sample_config


async def test_fetch_returns_provider_result(
    stub_provider_class: type[BaseProvider], sample_config: ProviderConfig
) -> None:
    provider = stub_provider_class(sample_config)
    result = await provider.fetch(query="test")
    assert result.provider_id == "stub"
    assert result.success is True
    assert result.data == {"echo": {"query": "test"}}


async def test_health_check_returns_bool(
    stub_provider_class: type[BaseProvider], sample_config: ProviderConfig
) -> None:
    provider = stub_provider_class(sample_config)
    assert await provider.health_check() is True
