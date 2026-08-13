"""Unit tests for ProviderRegistry."""

from __future__ import annotations

import pytest

from app.providers.base import BaseProvider
from app.providers.exceptions import ProviderAlreadyRegisteredError, ProviderNotRegisteredError
from app.providers.models import ProviderConfig
from app.providers.registry import ProviderRegistry


def test_register_and_get_provider_class(stub_provider_class: type[BaseProvider]) -> None:
    registry = ProviderRegistry()
    registry.register("stub", stub_provider_class)
    assert registry.get_provider_class("stub") is stub_provider_class


def test_register_as_decorator(stub_provider_class: type[BaseProvider]) -> None:
    registry = ProviderRegistry()

    @registry.register("stub")
    class DecoratedProvider(stub_provider_class):  # type: ignore[misc]
        pass

    assert registry.get_provider_class("stub") is DecoratedProvider


def test_duplicate_registration_raises(stub_provider_class: type[BaseProvider]) -> None:
    registry = ProviderRegistry()
    registry.register("stub", stub_provider_class)
    with pytest.raises(ProviderAlreadyRegisteredError):
        registry.register("stub", stub_provider_class)


def test_unregister_removes_provider(stub_provider_class: type[BaseProvider]) -> None:
    registry = ProviderRegistry()
    registry.register("stub", stub_provider_class)
    registry.unregister("stub")
    assert registry.is_registered("stub") is False


def test_unregister_unknown_id_is_a_no_op() -> None:
    registry = ProviderRegistry()
    registry.unregister("does-not-exist")


def test_get_unregistered_provider_raises() -> None:
    registry = ProviderRegistry()
    with pytest.raises(ProviderNotRegisteredError):
        registry.get_provider_class("does-not-exist")


def test_create_constructs_configured_instance(
    stub_provider_class: type[BaseProvider], sample_config: ProviderConfig
) -> None:
    registry = ProviderRegistry()
    registry.register("stub", stub_provider_class)

    provider = registry.create("stub", sample_config)

    assert isinstance(provider, stub_provider_class)
    assert provider.config is sample_config


def test_create_unregistered_provider_raises(sample_config: ProviderConfig) -> None:
    registry = ProviderRegistry()
    with pytest.raises(ProviderNotRegisteredError):
        registry.create("does-not-exist", sample_config)


def test_list_providers_returns_sorted_tuple(stub_provider_class: type[BaseProvider]) -> None:
    registry = ProviderRegistry()
    registry.register("zeta", stub_provider_class)
    registry.register("alpha", stub_provider_class)

    assert registry.list_providers() == ("alpha", "zeta")
