"""Tests for ConfigurationService.

Covers typed section access, the flat `get(key, default)` lookup
required by `ConfigurationInterface`, and injection into AgentRuntime in
place of `app.bootstrap.SettingsConfiguration`.
"""

from __future__ import annotations

import logging

import pytest

from app.bootstrap import EmptyKnowledgeHub, EmptyToolRegistry, InProcessMemory, NoOpEventBus
from app.config.models import AnthropicSettings, AppConfig, PostgreSQLSettings
from app.config.service import ConfigurationService
from app.core.runtime import AgentRuntime, ConfigurationInterface

_LOGGER = logging.getLogger("test.config")


def _config(**overrides: object) -> AppConfig:
    overrides.setdefault("anthropic", AnthropicSettings(_env_file=None, api_key="sk-test-key"))
    return AppConfig(**overrides)


# --- Typed section access -----------------------------------------------------------


def test_typed_properties_expose_each_section() -> None:
    service = ConfigurationService(_config())

    assert service.postgres.host == "localhost"
    assert service.redis.port == 6379
    assert service.chromadb.collection_name == "marketmind_knowledge"
    assert service.anthropic.api_key.get_secret_value() == "sk-test-key"
    assert service.embedding_provider.provider_id == "default"
    assert service.rss.user_agent == "MarketMind-AI/1.0"
    assert service.logging.level == "INFO"
    assert service.llm.provider == "anthropic"
    assert service.scheduler.enabled is True
    assert service.api.v1_prefix == "/api/v1"


def test_loads_from_environment_when_no_config_is_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-key")
    monkeypatch.setenv("POSTGRES_HOST", "env-host")

    service = ConfigurationService()

    assert service.postgres.host == "env-host"
    assert service.anthropic.api_key.get_secret_value() == "sk-env-key"


# --- get(key, default) -----------------------------------------------------------


def test_get_resolves_dotted_path() -> None:
    config = _config(postgres=PostgreSQLSettings(_env_file=None, host="db.internal"))
    service = ConfigurationService(config)

    assert service.get("postgres.host") == "db.internal"


def test_get_returns_default_for_unknown_section() -> None:
    service = ConfigurationService(_config())
    assert service.get("nonexistent.field", "fallback") == "fallback"


def test_get_returns_default_for_unknown_field() -> None:
    service = ConfigurationService(_config())
    assert service.get("postgres.nonexistent", "fallback") == "fallback"


def test_get_returns_default_for_malformed_key_without_a_dot() -> None:
    service = ConfigurationService(_config())
    assert service.get("postgres", "fallback") == "fallback"


def test_get_returns_none_default_when_omitted() -> None:
    service = ConfigurationService(_config())
    assert service.get("nonexistent.field") is None


def test_get_returns_actual_none_field_value_not_default() -> None:
    service = ConfigurationService(_config())
    assert service.get("redis.password", "fallback") is None


# --- Dependency injection -----------------------------------------------------------


def test_configuration_service_satisfies_configuration_interface() -> None:
    service = ConfigurationService(_config())
    assert isinstance(service, ConfigurationInterface)


def test_configuration_service_injects_into_agent_runtime() -> None:
    service = ConfigurationService(_config(postgres=PostgreSQLSettings(_env_file=None, host="rt-host")))

    runtime = AgentRuntime(
        logger=_LOGGER,
        configuration=service,
        knowledge_hub=EmptyKnowledgeHub(),
        memory=InProcessMemory(),
        tool_registry=EmptyToolRegistry(),
        event_bus=NoOpEventBus(),
    )

    assert runtime.configuration is service
    assert runtime.configuration.get("postgres.host") == "rt-host"
